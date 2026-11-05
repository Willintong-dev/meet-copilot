from meet_copilot.audio import FRAME_SAMPLES
from meet_copilot.segmenter import ActivityLog, Segmenter
from tests.fakes import frame


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def feed(segmenter, pattern):
    return [segment for loud in pattern if (segment := segmenter.feed(frame(loud), loud)) is not None]


def test_emits_segment_after_trailing_silence_with_pre_roll():
    segmenter = Segmenter(silence_ms=90, max_seconds=12, clock=Clock())
    segments = feed(segmenter, [False] * 5 + [True] * 10 + [False] * 3)
    assert len(segments) == 1
    assert len(segments[0].audio) == (5 + 10 + 3) * FRAME_SAMPLES


def test_ignores_short_noise():
    segmenter = Segmenter(silence_ms=90, max_seconds=12)
    assert feed(segmenter, [True] * 3 + [False] * 5) == []


def test_cuts_long_monologue_at_max_length():
    segmenter = Segmenter(silence_ms=90, max_seconds=1)
    segments = feed(segmenter, [True] * 80)
    assert len(segments) == 2


def test_activity_log_speech_ratio():
    log = ActivityLog()
    for index in range(10):
        log.record(float(index), index < 5)
    assert log.speech_ratio(0, 4) == 1.0
    assert log.speech_ratio(5, 9) == 0.0
    assert log.speech_ratio(0, 9) == 0.5
    assert log.speech_ratio(50, 60) == 0.0
