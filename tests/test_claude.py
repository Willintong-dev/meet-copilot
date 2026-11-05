import pytest

from meet_copilot.claude import extract_json


def test_extracts_fenced_object():
    assert extract_json('Aquí va:\n```json\n{"a": 1}\n```') == {"a": 1}


def test_extracts_bare_array_of_objects():
    assert extract_json('[{"en": "hi"}, {"en": "bye"}]') == [{"en": "hi"}, {"en": "bye"}]


def test_extracts_object_with_surrounding_text():
    assert extract_json('ok {"resumen": "x", "lista": [1, 2]} listo') == {"resumen": "x", "lista": [1, 2]}


def test_raises_without_json():
    with pytest.raises(ValueError):
        extract_json("no hay nada")
