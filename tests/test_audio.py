import numpy as np

from meet_copilot.audio import FRAME_SAMPLES, FrameBuffer, float_to_int16, resample


def test_frame_buffer_emits_full_frames_and_keeps_remainder():
    buffer = FrameBuffer()
    assert buffer.push(np.ones(FRAME_SAMPLES - 10, dtype=np.int16)) == []
    frames = buffer.push(np.ones(FRAME_SAMPLES + 20, dtype=np.int16))
    assert len(frames) == 2
    assert all(len(frame) == FRAME_SAMPLES for frame in frames)
    assert len(buffer.pending) == 10


def test_resample_from_48k_to_16k_keeps_dtype_and_duration():
    samples = np.arange(48000, dtype=np.int16)
    result = resample(samples, 48000)
    assert len(result) == 16000
    assert result.dtype == np.int16


def test_resample_is_noop_at_target_rate():
    samples = np.arange(10, dtype=np.int16)
    assert resample(samples, 16000) is samples


def test_float_to_int16_clips():
    result = float_to_int16(np.array([-2.0, 0.0, 0.5, 2.0], dtype=np.float32))
    assert result.tolist() == [-32767, 0, 16383, 32767]
