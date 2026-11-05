import json

from meet_copilot.translator import Translator, translator_prompt
from tests.fakes import FakeChat, echo_translation


def test_translates_batch_in_one_call():
    chat = FakeChat("haiku", echo_translation)
    assert Translator(chat).translate(["Hello", "Bye"]) == ["ES: Hello", "ES: Bye"]
    assert len(chat.prompts) == 1


def test_falls_back_to_one_by_one_when_lengths_mismatch():
    def responder(prompt):
        texts = json.loads(prompt)
        return json.dumps(["solo una"]) if len(texts) > 1 else json.dumps([f"ES: {texts[0]}"])

    chat = FakeChat("haiku", responder)
    assert Translator(chat).translate(["Hello", "Bye"]) == ["ES: Hello", "ES: Bye"]
    assert len(chat.prompts) == 3


def test_returns_none_when_translation_fails():
    def broken(prompt):
        raise RuntimeError("sin red")

    assert Translator(FakeChat("haiku", broken)).translate(["Hello"]) == [None]


def test_prompt_truncates_long_context():
    prompt = translator_prompt("§" * 5000)
    assert prompt.count("§") == 1500
