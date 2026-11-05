import bisect
import threading
import time
from dataclasses import dataclass

import numpy as np

from meet_copilot.audio import FRAME_MS, SAMPLE_RATE

PRE_ROLL_MS = 300
MIN_SPEECH_MS = 250


@dataclass
class Segment:
    audio: np.ndarray
    started_at: float
    ended_at: float


def webrtc_vad(aggressiveness=2):
    import webrtcvad

    vad = webrtcvad.Vad(aggressiveness)
    return lambda frame: vad.is_speech(frame.tobytes(), SAMPLE_RATE)


class Segmenter:
    def __init__(self, silence_ms=500, max_seconds=12, clock=time.time):
        self.silence_frames = max(1, silence_ms // FRAME_MS)
        self.max_frames = max_seconds * 1000 // FRAME_MS
        self.pre_roll_frames = PRE_ROLL_MS // FRAME_MS
        self.min_speech_frames = MIN_SPEECH_MS // FRAME_MS
        self.clock = clock
        self.pre_roll = []
        self.current = None
        self.started_at = 0.0
        self.silence = 0
        self.speech = 0

    def feed(self, frame, is_speech):
        if self.current is None:
            self.pre_roll = (self.pre_roll + [frame])[-self.pre_roll_frames :]
            if is_speech:
                self.current = list(self.pre_roll)
                self.started_at = self.clock() - len(self.pre_roll) * FRAME_MS / 1000
                self.silence, self.speech = 0, 1
            return None
        self.current.append(frame)
        self.speech += int(is_speech)
        self.silence = 0 if is_speech else self.silence + 1
        if self.silence < self.silence_frames and len(self.current) < self.max_frames:
            return None
        segment = None
        if self.speech >= self.min_speech_frames:
            segment = Segment(np.concatenate(self.current), self.started_at, self.clock())
        self.current, self.pre_roll = None, []
        return segment


class ActivityLog:
    def __init__(self, keep_seconds=120):
        self.keep_seconds = keep_seconds
        self.times = []
        self.flags = []
        self.lock = threading.Lock()

    def record(self, timestamp, is_speech):
        with self.lock:
            self.times.append(timestamp)
            self.flags.append(is_speech)
            cutoff = bisect.bisect_left(self.times, timestamp - self.keep_seconds)
            if cutoff > 1000:
                del self.times[:cutoff]
                del self.flags[:cutoff]

    def speech_ratio(self, start, end):
        with self.lock:
            low = bisect.bisect_left(self.times, start)
            high = bisect.bisect_right(self.times, end)
            window = self.flags[low:high]
        return sum(window) / len(window) if window else 0.0
