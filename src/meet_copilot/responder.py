import logging

from meet_copilot.claude import extract_json
from meet_copilot.copilot import render_lines

log = logging.getLogger(__name__)

CONTEXT_CHARS = 4000
RECENT_LINES = 20
CONFIDENCE_LEVELS = {"alta", "media", "baja"}
LENGTHS = {
    "breve": "Extensión pedida: UNA frase, máximo 25 palabras.",
    "desarrollada": "Extensión pedida: 2 o 3 frases, entre 40 y 70 palabras.",
}

SYSTEM_PROMPT = """Ayudas a {user}, hispanohablante, que está en una llamada de trabajo en {call_language} y no domina del todo el idioma. Un detector automático marcó algo que podría ser una pregunta.

ACEPTA (es_pregunta = true) cualquier cosa que un participante podría tener que responder en voz alta:
- Saludos y cortesías dirigidas a alguien: "how are you?", "how's it going?", "did you have a good weekend?". Un saludo cuenta: justo ahí se traba quien no domina el idioma.
- Verificaciones: "can you hear me?", "can you see my screen?", "are you there?".
- Preguntas de comprensión que invitan a contestar: "any questions?", "does that make sense?".
- Cualquier pregunta técnica o de opinión abierta al grupo.
- Peticiones que esperan que alguien hable aunque no sean preguntas gramaticales: "give me an example", "walk me through it", "share your thoughts", "let me know".

RECHAZA (es_pregunta = false) solo estos casos:
- Quien habla se responde solo de inmediato: "why does this matter? Well, because…".
- Muletillas pegadas a media frase: "…you know?", "…right?", "…I mean?".
- Preguntas dirigidas por nombre a otra persona que no es {user}.

Si es pregunta, redacta una respuesta que {user} pueda decir en voz alta, en {call_language} claro y pronunciable: frases cortas, sin vocabulario rebuscado ni modismos difíciles.

Para preguntas abiertas o técnicas:
1. Responde de frente en la primera frase. Nada de rodeos ni "that's a great question".
2. Añade una razón concreta, un ejemplo o un matiz que sostenga lo dicho.
3. Si encaja, cierra devolviendo la palabra: "does that answer it?", "happy to go deeper".
Para saludos y verificaciones basta una frase natural.

Usa primero el contexto preparado de la llamada: si la respuesta está ahí, dila tal cual.

Da siempre una respuesta completa y usable sin editar: en vivo no hay tiempo de rellenar huecos. Si falta un dato que no está en el contexto ni en la conversación, propón la opción más común y segura y envuelve ese supuesto entre corchetes, en el mismo punto de las dos versiones. Se le mostrará subrayado para que sepa qué revisar.
Así NO:  "We use [tu herramienta] for that."
Así SÍ:  "We use [Git and GitHub] for that, mainly because [it keeps the history clean]."
Si no supones nada, no pongas corchetes.

Excepción: nunca inventes cifras de la empresa, precios, fechas ni compromisos. Ahí la respuesta es una salida honesta: confirmar después, pedir que lo repitan o redirigir a quien sabe.

Responde SOLO con este JSON, sin markdown:
{{"es_pregunta": true|false, "dirigida_a_mi": true|false, "pregunta_es": "la pregunta en español", "respuesta_en": "la respuesta en {call_language}", "respuesta_es": "la misma respuesta en español", "confianza": "alta"|"media"|"baja"}}

Contexto preparado antes de la llamada:
<contexto>
{context}
</contexto>"""


def responder_prompt(settings, context):
    return SYSTEM_PROMPT.format(
        user=settings.user_name,
        call_language="inglés" if settings.call_language == "en" else settings.call_language,
        context=(context or "No hay contexto previo.")[:CONTEXT_CHARS],
    )


def normalize_answer(data):
    if not isinstance(data, dict):
        raise ValueError("el respondedor no devolvió un objeto")
    if not data.get("es_pregunta") or not data.get("respuesta_en"):
        return None
    confidence = str(data.get("confianza") or "").lower()
    return {
        "dirigida_a_mi": bool(data.get("dirigida_a_mi")),
        "pregunta_es": str(data.get("pregunta_es") or "").strip(),
        "respuesta_en": str(data["respuesta_en"]).strip(),
        "respuesta_es": str(data.get("respuesta_es") or "").strip(),
        "confianza": confidence if confidence in CONFIDENCE_LEVELS else None,
    }


class Responder:
    def __init__(self, chat, settings):
        self.chat = chat
        self.settings = settings

    def answer(self, question, recent_lines):
        prompt = "\n".join(
            [
                LENGTHS.get(self.settings.answer_length, LENGTHS["desarrollada"]),
                f"Mi nombre en la llamada: {self.settings.user_name}",
                "",
                "Últimas líneas:",
                render_lines(recent_lines[-RECENT_LINES:]),
                "",
                f'Posible pregunta a evaluar: "{question}"',
            ]
        )
        return normalize_answer(extract_json(self.chat.ask(prompt, timeout=45)))
