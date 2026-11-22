import json
import logging

from meet_copilot.claude import extract_json

log = logging.getLogger(__name__)

GLOSSARY_CHARS = 1500

SYSTEM_PROMPT = """Eres intérprete simultáneo en una llamada de trabajo por Google Meet.
Recibes un arreglo JSON con frases en inglés salidas de un reconocedor de voz: pueden venir cortadas o con palabras mal reconocidas.
Responde SOLO con un arreglo JSON del mismo largo y en el mismo orden, con cada frase traducida a español latinoamericano natural y conversacional.
Corrige errores obvios del reconocedor usando el contexto: traduce lo que evidentemente quiso decir. Conserva nombres propios, productos, siglas y los términos técnicos que la industria no traduce (deploy, endpoint, commit, dashboard, chargeback).
Si una frase ya viene en español, devuélvela igual.
No agregues explicaciones ni notas.

Contexto de la llamada (úsalo solo para acertar términos y nombres):
{context}"""


def translator_prompt(context):
    return SYSTEM_PROMPT.format(context=(context or "sin contexto")[:GLOSSARY_CHARS])


class Translator:
    def __init__(self, chat):
        self.chat = chat

    def translate(self, texts):
        if not texts:
            return []
        try:
            result = extract_json(self.chat.ask(json.dumps(texts, ensure_ascii=False)))
        except Exception as error:
            log.warning("translation failed: %s", error)
            result = None
        if isinstance(result, list) and len(result) == len(texts):
            return [str(item) for item in result]
        if len(texts) == 1:
            return [None]
        return [value for text in texts for value in self.translate([text])]
