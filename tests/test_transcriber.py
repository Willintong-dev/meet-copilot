from meet_copilot.transcriber import confident_text, is_hallucination


def test_known_hallucinations_are_dropped():
    assert is_hallucination(" Thank you.")
    assert is_hallucination("Subtítulos realizados por la comunidad de Amara.org")
    assert is_hallucination("")


def test_repetitive_loops_are_dropped():
    assert is_hallucination("the the the the the the the")


def test_real_speech_is_kept():
    assert not is_hallucination("Thank you for the demo, can we talk about pricing?")
    assert not is_hallucination("Okay.")


def test_confident_text_drops_silent_low_confidence_segments():
    segments = [
        {"text": " Hello there.", "no_speech_prob": 0.1, "avg_logprob": -0.2},
        {"text": " Thanks for watching!", "no_speech_prob": 0.9, "avg_logprob": -1.5},
    ]
    assert confident_text(segments) == "Hello there."
