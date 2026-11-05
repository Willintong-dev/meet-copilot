import logging
import queue
import threading
import time

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000

log = logging.getLogger(__name__)


def resample(samples, source_rate):
    if source_rate == SAMPLE_RATE:
        return samples
    target_length = int(len(samples) * SAMPLE_RATE / source_rate)
    positions = np.linspace(0, len(samples) - 1, target_length)
    return np.interp(positions, np.arange(len(samples)), samples).astype(samples.dtype)


def float_to_int16(samples):
    return (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)


class FrameBuffer:
    def __init__(self):
        self.pending = np.zeros(0, dtype=np.int16)

    def push(self, samples):
        self.pending = np.concatenate([self.pending, samples])
        frames = []
        while len(self.pending) >= FRAME_SAMPLES:
            frames.append(self.pending[:FRAME_SAMPLES])
            self.pending = self.pending[FRAME_SAMPLES:]
        return frames


class MicrophoneSource:
    name = "me"

    def __init__(self):
        self.stopped = threading.Event()

    def stop(self):
        self.stopped.set()

    def frames(self):
        import sounddevice as sd

        while not self.stopped.is_set():
            try:
                yield from self._stream(sd)
            except sd.PortAudioError as error:
                log.warning("microphone error: %s", error)
                time.sleep(1)

    def _stream(self, sd):
        sd._terminate()
        sd._initialize()
        device = sd.query_devices(kind="input")
        rate = int(device["default_samplerate"])
        log.info("microphone: %s @ %s Hz", device["name"], rate)
        chunks = queue.Queue()
        buffer = FrameBuffer()
        with sd.InputStream(
            device=device["index"],
            samplerate=rate,
            channels=1,
            dtype="int16",
            blocksize=rate * FRAME_MS // 1000,
            callback=lambda data, frames, info, status: chunks.put(data[:, 0].copy()),
        ):
            while not self.stopped.is_set():
                try:
                    chunk = chunks.get(timeout=2)
                except queue.Empty:
                    log.warning("microphone stalled")
                    return
                yield from buffer.push(resample(chunk, rate))


class SystemAudioSource:
    name = "them"

    def __init__(self):
        self.stopped = threading.Event()
        self.chunks = queue.Queue()
        self.stream = None
        self.output = None

    def stop(self):
        self.stopped.set()
        if self.stream is not None:
            self.stream.stopCaptureWithCompletionHandler_(lambda error: None)

    def frames(self):
        self._start()
        buffer = FrameBuffer()
        while not self.stopped.is_set():
            try:
                chunk = self.chunks.get(timeout=1)
            except queue.Empty:
                continue
            yield from buffer.push(float_to_int16(chunk))

    def _start(self):
        import CoreMedia
        import ScreenCaptureKit as SCK

        content = _wait(
            lambda done: SCK.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
                True, True, lambda content, error: done((content, error))
            )
        )
        shareable, error = content
        if shareable is None:
            raise PermissionError(
                f"No hay permiso de 'Grabación de pantalla y audio del sistema': {error}"
            )
        display = shareable.displays()[0]
        content_filter = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(display, [])
        config = SCK.SCStreamConfiguration.alloc().init()
        config.setCapturesAudio_(True)
        config.setExcludesCurrentProcessAudio_(True)
        config.setSampleRate_(SAMPLE_RATE)
        config.setChannelCount_(1)
        config.setWidth_(2)
        config.setHeight_(2)
        config.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1, 1))
        self.output = _stream_output_class().alloc().init()
        self.output.sink = self.chunks.put
        self.stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(content_filter, config, None)
        for kind in (SCK.SCStreamOutputTypeScreen, SCK.SCStreamOutputTypeAudio):
            ok, error = self.stream.addStreamOutput_type_sampleHandlerQueue_error_(self.output, kind, None, None)
            if not ok:
                raise RuntimeError(f"addStreamOutput failed: {error}")
        error = _wait(lambda done: self.stream.startCaptureWithCompletionHandler_(done))
        if error is not None:
            raise PermissionError(f"No se pudo iniciar la captura del audio del sistema: {error}")
        log.info("system audio capture started")


def _wait(start, timeout=10):
    result = {}
    finished = threading.Event()

    def done(value):
        result["value"] = value
        finished.set()

    start(done)
    if not finished.wait(timeout):
        raise TimeoutError("ScreenCaptureKit no respondió")
    return result["value"]


_OUTPUT_CLASS = None


def _stream_output_class():
    global _OUTPUT_CLASS
    if _OUTPUT_CLASS is not None:
        return _OUTPUT_CLASS
    import CoreMedia
    import objc
    import ScreenCaptureKit as SCK
    from Foundation import NSObject

    class AudioStreamOutput(NSObject, protocols=[objc.protocolNamed("SCStreamOutput")]):
        def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buffer, kind):
            if kind != SCK.SCStreamOutputTypeAudio:
                return
            block = CoreMedia.CMSampleBufferGetDataBuffer(sample_buffer)
            if block is None:
                return
            length = CoreMedia.CMBlockBufferGetDataLength(block)
            status, data = CoreMedia.CMBlockBufferCopyDataBytes(block, 0, length, None)
            if status == 0:
                self.sink(np.frombuffer(bytes(data), dtype=np.float32).copy())

    _OUTPUT_CLASS = AudioStreamOutput
    return _OUTPUT_CLASS
