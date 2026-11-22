import logging
import queue
import threading
import time
from dataclasses import asdict

from meet_copilot.claude import ClaudeChat
from meet_copilot.copilot import Copilot, should_consult
from meet_copilot.questions import SentenceBuffer, is_question, similar
from meet_copilot.responder import Responder, responder_prompt
from meet_copilot.segmenter import ActivityLog, Segmenter, webrtc_vad
from meet_copilot.store import Line, SessionStore
from meet_copilot.translator import Translator, translator_prompt

log = logging.getLogger(__name__)

TRANSLATION_BATCH = 5
MAX_PENDING_QUESTIONS = 2
SOURCE_LABELS = {"me": "micrófono", "them": "audio de la llamada"}


class LiveSession:
    def __init__(self, settings, bus, transcriber, runner, title, context, sources, vad_factory=webrtc_vad, chats=None):
        self.settings = settings
        self.bus = bus
        self.transcriber = transcriber
        self.sources = sources
        self.vad_factory = vad_factory
        self.title = title
        self.context = context
        self.store = SessionStore(settings.sessions_dir, title, context)
        translator_chat, copilot_chat, responder_chat = chats or (
            ClaudeChat(runner, settings.translator_model, translator_prompt(context)),
            ClaudeChat(runner, settings.copilot_model, "", max_turns=10**9),
            ClaudeChat(runner, settings.answer_model, responder_prompt(settings, context)),
        )
        self.translator = Translator(translator_chat)
        self.copilot = Copilot(copilot_chat, settings, context)
        self.responder = Responder(responder_chat, settings)
        self.chats = (translator_chat, copilot_chat, responder_chat)
        self.lines = []
        self.lines_lock = threading.Lock()
        self.segments = queue.Queue()
        self.to_translate = queue.Queue()
        self.activity = ActivityLog()
        self.copilot_signal = threading.Condition()
        self.pending_for_copilot = []
        self.questions = []
        self.sentence = SentenceBuffer()
        self.sentence_lock = threading.Lock()
        self.to_answer = queue.Queue()
        self.answers = []
        self.capturing = threading.Event()
        self.transcribing = threading.Event()
        self.running = threading.Event()
        self.capture_threads = []
        self.workers = []

    def start(self):
        self.running.set()
        self.capturing.set()
        self.transcribing.set()
        for chat in self.chats:
            threading.Thread(target=self._warm, args=(chat,), daemon=True).start()
        for source in self.sources:
            thread = threading.Thread(target=self._capture, args=(source,), daemon=True, name=f"capture-{source.name}")
            thread.start()
            self.capture_threads.append(thread)
        for target in (self._transcribe_loop, self._translate_loop, self._copilot_loop, self._answer_loop):
            thread = threading.Thread(target=target, daemon=True, name=target.__name__)
            thread.start()
            self.workers.append(thread)
        self.bus.publish("status", {"state": "listening", "session": self.store.id, "title": self.title})

    def ask(self, question):
        with self.copilot_signal:
            self.questions.append(question)
            self.copilot_signal.notify()

    def stop(self):
        self.bus.publish("status", {"state": "closing"})
        for source in self.sources:
            source.stop()
        self.capturing.clear()
        for thread in self.capture_threads:
            thread.join(timeout=5)
        self.transcribing.clear()
        for thread in self.workers[:2]:
            thread.join(timeout=60)
        self.running.clear()
        with self.copilot_signal:
            self.copilot_signal.notify()
        for thread in self.workers[2:]:
            thread.join(timeout=120)
        lines = self.snapshot()
        summary = ""
        if lines:
            self.bus.publish("status", {"state": "summarizing"})
            try:
                summary = self.copilot.summarize(lines)
            except Exception as error:
                log.exception("summary failed")
                self.bus.publish("error", {"message": f"No se pudo generar el resumen: {error}"})
        self.store.finish(lines, summary, self.answers)
        for chat in self.chats:
            chat.close()
        self.bus.publish("summary", {"session": self.store.id, "markdown": summary})
        self.bus.publish("status", {"state": "idle"})
        return summary

    def snapshot(self):
        with self.lines_lock:
            return list(self.lines)

    def _warm(self, chat):
        try:
            chat.warm()
        except Exception as error:
            log.warning("warming %s failed: %s", chat.model, error)
            self.bus.publish("error", {"message": f"No pude conectar con Claude ({chat.model}): {error}"})

    def _capture(self, source):
        vad = self.vad_factory()
        segmenter = Segmenter(self.settings.silence_ms, self.settings.max_segment_seconds)
        try:
            for frame in source.frames():
                if not self.capturing.is_set():
                    break
                is_speech = vad(frame)
                if source.name == "them":
                    self.activity.record(time.time(), is_speech)
                segment = segmenter.feed(frame, is_speech)
                if segment is not None:
                    self.segments.put((source.name, segment))
        except Exception as error:
            log.exception("capture %s failed", source.name)
            self.bus.publish("error", {"message": f"Falló la captura del {SOURCE_LABELS.get(source.name, source.name)}: {error}"})

    def _transcribe_loop(self):
        while self.transcribing.is_set() or not self.segments.empty():
            try:
                speaker, segment = self.segments.get(timeout=0.5)
            except queue.Empty:
                continue
            if speaker == "me" and self._is_echo(segment):
                continue
            language = self.settings.call_language if speaker == "them" else None
            try:
                text, detected = self.transcriber.transcribe(segment.audio, language)
            except Exception as error:
                log.exception("transcription failed")
                self.bus.publish("error", {"message": f"Falló la transcripción: {error}"})
                continue
            detected = detected or language or ""
            if text and self._expected_language(detected):
                self._add_line(speaker, text, detected, segment.started_at)

    def _is_echo(self, segment):
        return self.activity.speech_ratio(segment.started_at, segment.ended_at) >= self.settings.echo_overlap_ratio

    def _expected_language(self, language):
        return language in (self.settings.my_language, self.settings.call_language)

    def _repeats_them(self, text, started_at, lines):
        window = self.settings.echo_window_seconds
        return any(
            line.speaker == "them" and abs(started_at - line.started_at) <= window and similar(line.text, text)
            for line in reversed(lines[-10:])
        )

    def _add_line(self, speaker, text, language, started_at):
        with self.lines_lock:
            if speaker == "me" and self._repeats_them(text, started_at, self.lines):
                return None
            line = Line(len(self.lines), speaker, text, language, started_at)
            self.lines.append(line)
        self.bus.publish("line", asdict(line))
        if language == self.settings.my_language:
            self.store.record_line(line)
        else:
            self.to_translate.put(line)
        with self.copilot_signal:
            self.pending_for_copilot.append(line)
            self.copilot_signal.notify()
        if speaker == "them":
            with self.sentence_lock:
                sentence = self.sentence.add(line.id, text, started_at)
            self._evaluate(sentence)
        return line

    def _evaluate(self, sentence):
        if sentence is None or not is_question(sentence.text):
            return
        self.bus.publish("question", {"ids": sentence.line_ids, "text": sentence.text, "started_at": sentence.started_at})
        while self.to_answer.qsize() >= MAX_PENDING_QUESTIONS:
            try:
                stale = self.to_answer.get_nowait()
            except queue.Empty:
                break
            self.bus.publish("question_dismissed", {"ids": stale.line_ids})
        self.to_answer.put(sentence)

    def _answer_loop(self):
        while self.running.is_set():
            with self.sentence_lock:
                paused = self.sentence.flush_if_paused()
            self._evaluate(paused)
            try:
                sentence = self.to_answer.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                answer = self.responder.answer(sentence.text, self.snapshot())
            except Exception as error:
                log.exception("responder failed")
                self.bus.publish("error", {"message": f"No pude sugerir respuesta: {error}"})
                self.bus.publish("question_dismissed", {"ids": sentence.line_ids})
                continue
            if answer is None:
                self.bus.publish("question_dismissed", {"ids": sentence.line_ids})
                continue
            answer.update({"ids": sentence.line_ids, "original": sentence.text, "started_at": sentence.started_at})
            self.answers.append(answer)
            self.store.record_answer(answer)
            self.bus.publish("answer", answer)

    def _translate_loop(self):
        while self.transcribing.is_set() or any(t.is_alive() for t in self.workers[:1]) or not self.to_translate.empty():
            try:
                batch = [self.to_translate.get(timeout=0.5)]
            except queue.Empty:
                continue
            while len(batch) < TRANSLATION_BATCH and not self.to_translate.empty():
                batch.append(self.to_translate.get_nowait())
            translations = self.translator.translate([line.text for line in batch])
            for line, translation in zip(batch, translations):
                line.translation = translation
                if translation:
                    self.bus.publish("translation", {"id": line.id, "translation": translation})
                self.store.record_line(line)

    def _copilot_loop(self):
        last_run = time.time()
        while True:
            with self.copilot_signal:
                if self.running.is_set():
                    self.copilot_signal.wait(timeout=1)
                if not self.running.is_set():
                    return
                question = self.questions.pop(0) if self.questions else None
                ready = should_consult(
                    self.pending_for_copilot, time.time() - last_run, self.settings.copilot_interval_seconds
                )
                if question is None and not ready:
                    continue
                batch, self.pending_for_copilot = self.pending_for_copilot, []
            self.bus.publish("thinking", {"question": question})
            try:
                transcript = self.snapshot()
                if question is None:
                    advice = self.copilot.consult(batch, transcript)
                else:
                    advice = self.copilot.ask(question, batch, transcript)
                advice["consulta"] = question
                self.bus.publish("advice", advice)
                self.store.record_advice(advice)
            except Exception as error:
                log.exception("copilot failed")
                self.bus.publish("error", {"message": f"El copiloto falló: {error}"})
                with self.copilot_signal:
                    self.pending_for_copilot = batch + self.pending_for_copilot
            last_run = time.time()
