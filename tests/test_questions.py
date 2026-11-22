import pytest

from meet_copilot.questions import SentenceBuffer, is_question, normalize, similar


@pytest.mark.parametrize(
    "text",
    [
        "What do you think about the timeline?",
        "Could you share the deck",
        "Do you support SSO",
        "Is the API stable",
        "How are you doing",
        "Can you hear me",
        "Does that make sense",
        "So tell me about your setup",
        "Okay, walk us through the flow",
        "Any questions so far",
        "I'd like to hear your thoughts on this",
        "¿Cómo manejan los reembolsos",
        "Alguna duda hasta aquí",
        "Bueno, cuéntame cómo lo hacen hoy",
        "How is the flow? The agent sends the chargeback notification.",
        "So, what do you think about the rollout",
        "Okay and how would you handle partial refunds",
        "Thank you, Gusto. Does anyone have any questions or any suggestions?",
    ],
)
def test_detects_questions_and_requests(text):
    assert is_question(text)


@pytest.mark.parametrize(
    "text",
    [
        "We shipped the release yesterday.",
        "What we do here is reconcile the ledger.",
        "Do that first and then deploy.",
        "Let me show you the dashboard.",
        "They will give us their services next month.",
        "Okay.",
        "O sea, lo hacemos por lotes.",
        "So October was our sales month, right?",
        "And that is net of churn, you know? We keep growing.",
        "Calendar, you block it, and you follow through, right? And of course we will support you.",
        "Lo cerramos el viernes, ¿verdad?",
        "About 21.9K a month of added MRR, which is great as well.",
        "For me, what was happening in the last two months was the phone.",
    ],
)
def test_ignores_statements(text):
    assert not is_question(text)


def test_normalize_strips_accents_punctuation_and_case():
    assert normalize("¿Qué  tal, Ñandú?") == "que tal nandu"


def test_similar_tolerates_small_transcription_differences():
    assert similar("We use Stripe for payments today.", "we use stripe for payment today")
    assert similar("Hello", "Hello everyone, welcome")
    assert not similar("We use Stripe for payments today.", "Let's review the roadmap next week.")
    assert not similar("", "Hello")


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_sentence_split_across_segments_is_evaluated_whole():
    clock = FakeClock()
    buffer = SentenceBuffer(clock=clock)
    assert buffer.add(1, "Do you have any questions about the", 0.0) is None
    clock.now = 1.0
    sentence = buffer.add(2, "functioning of the platform?", 1.0)
    assert sentence.text == "Do you have any questions about the functioning of the platform?"
    assert sentence.line_ids == [1, 2]
    assert sentence.started_at == 0.0
    assert buffer.flush() is None


def test_sentence_flushes_after_a_pause():
    clock = FakeClock()
    buffer = SentenceBuffer(clock=clock, pause_seconds=2.5)
    buffer.add(1, "Tell me about your setup", 0.0)
    clock.now = 2.0
    assert buffer.flush_if_paused() is None
    clock.now = 2.6
    assert buffer.flush_if_paused().text == "Tell me about your setup"


def test_sentence_flushes_when_too_long_or_too_old():
    clock = FakeClock()
    assert SentenceBuffer(clock=clock, max_words=5).add(1, "one two three four five", 0.0) is not None
    old = SentenceBuffer(clock=clock, max_age_seconds=9)
    old.add(1, "first part", 0.0)
    clock.now = 9.5
    assert old.add(2, "second part", 9.5).line_ids == [1, 2]
