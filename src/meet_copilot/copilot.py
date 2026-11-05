import logging
import re

from meet_copilot.claude import extract_json

log = logging.getLogger(__name__)

QUESTION_OPENERS = {
    "what", "how", "why", "when", "where", "who", "which", "whose",
    "can", "could", "would", "will", "should", "shall",
    "do", "does", "did", "is", "are", "was", "were", "have", "has",
    "any", "anything",
}
BATCH_LINES = 6
RECENT_LINES_ON_RESET = 25

SYSTEM_PROMPT = """Eres el copiloto en vivo de {user} durante una llamada de Google Meet.
{user} habla español nativo y la llamada es en {call_language}. Necesita entender rápido qué pasa y tener a mano qué decir.

Te iré mandando fragmentos nuevos de la transcripción automática (puede tener errores), marcados:
[ELLOS] lo que dicen los demás participantes
[YO] lo que dice {user}

Cada vez responde SOLO un objeto JSON con esta forma:
{{
  "resumen": "1-2 frases en español: de qué se está hablando ahora mismo",
  "pregunta": "si le preguntaron o esperan algo de {user}, qué es (en español); si no, null",
  "sugerencias": [
    {{"en": "frase corta y natural que {user} podría decir en {call_language}", "es": "traducción al español"}}
  ],
  "pendientes": ["compromisos, datos pedidos y temas abiertos acumulados de toda la llamada"],
  "nota": "dato del contexto previo que sirve justo ahora, o una alerta; si no hay, null"
}}

Reglas para las sugerencias:
- De 2 a 3, de la más útil a la menos. Si hay una pregunta pendiente, la primera la responde.
- Fáciles de leer en voz alta: oraciones cortas y vocabulario simple, en tono profesional y cercano.
- Básalas en el contexto previo y en lo dicho en la llamada. Nunca inventes cifras, fechas, precios ni compromisos que no estén en el contexto: si falta el dato, sugiere una frase para confirmarlo después o para pedir aclaración.
- Si no hace falta que {user} hable, sugiere una pregunta inteligente para aportar o profundizar.

Cuando el mensaje empiece con [CONSULTA DE {user_upper}], es una pregunta privada de {user} para ti: respóndela en "nota" (en español, directo) y pon en "sugerencias" frases para usar en la llamada.

Contexto preparado antes de la llamada:
<contexto>
{context}
</contexto>"""

RESUME_NOTE = """

Ya llevamos un rato en la llamada. Estado hasta ahora:
Resumen: {summary}
Pendientes: {pending}"""

SUMMARY_SYSTEM = """Resumes llamadas de trabajo de {user}. Contexto preparado antes de la llamada:
<contexto>
{context}
</contexto>"""

SUMMARY_PROMPT = """Transcripción completa de la llamada ([ELLOS] los demás, [YO] {user}):
<transcripcion>
{transcript}
</transcripcion>

Escribe en español, en markdown:
## Resumen
## Decisiones
## Pendientes
(separa los míos de los de ellos, con responsable y fecha si se mencionó)
## Personas y datos a recordar
## Para la próxima llamada
Sé concreto y no inventes nada que no se haya dicho o que no esté en el contexto."""


def looks_like_question(text):
    stripped = text.strip()
    if "?" in stripped:
        return True
    words = re.findall(r"[a-z']+", stripped.lower())
    return bool(words) and words[0] in QUESTION_OPENERS and "you" in words


def should_consult(pending, seconds_since_last, interval):
    if not pending:
        return False
    if any(line.speaker == "them" and looks_like_question(line.text) for line in pending):
        return True
    return len(pending) >= BATCH_LINES or seconds_since_last >= interval


def render_lines(lines):
    return "\n".join(f"[{'YO' if line.speaker == 'me' else 'ELLOS'}] {line.text}" for line in lines)


def normalize_advice(data):
    if not isinstance(data, dict):
        raise ValueError("el copiloto no devolvió un objeto")
    suggestions = [
        {"en": str(item.get("en", "")).strip(), "es": str(item.get("es", "")).strip()}
        for item in data.get("sugerencias") or []
        if isinstance(item, dict) and item.get("en")
    ]
    return {
        "resumen": data.get("resumen") or "",
        "pregunta": data.get("pregunta") or None,
        "sugerencias": suggestions,
        "pendientes": [str(item) for item in data.get("pendientes") or []],
        "nota": data.get("nota") or None,
    }


class Copilot:
    def __init__(self, chat, settings, context):
        self.chat = chat
        self.settings = settings
        self.context = context
        self.turns = 0
        self.last_advice = None
        chat.system_prompt = self.system_prompt()

    def system_prompt(self, resume=""):
        user = self.settings.user_name
        return SYSTEM_PROMPT.format(
            user=user,
            user_upper=user.upper(),
            call_language="inglés" if self.settings.call_language == "en" else self.settings.call_language,
            context=self.context or "No hay contexto previo.",
        ) + resume

    def consult(self, new_lines, transcript):
        return self._ask(render_lines(new_lines), transcript)

    def ask(self, question, new_lines, transcript):
        consult = f"[CONSULTA DE {self.settings.user_name.upper()}] {question}"
        return self._ask(f"{render_lines(new_lines)}\n{consult}" if new_lines else consult, transcript)

    def summarize(self, transcript):
        user = self.settings.user_name
        self.chat.reset(SUMMARY_SYSTEM.format(user=user, context=self.context or "No hay contexto previo."))
        prompt = SUMMARY_PROMPT.format(user=user, transcript=render_lines(transcript))
        return self.chat.ask(prompt, timeout=300)

    def _ask(self, message, transcript):
        if self.turns >= self.settings.copilot_max_turns:
            self._compact(transcript)
            message = render_lines(transcript[-RECENT_LINES_ON_RESET:]) + "\n" + message
        advice = normalize_advice(extract_json(self.chat.ask(message)))
        self.turns += 1
        self.last_advice = advice
        return advice

    def _compact(self, transcript):
        previous = self.last_advice or {"resumen": "", "pendientes": []}
        resume = RESUME_NOTE.format(summary=previous["resumen"], pending="; ".join(previous["pendientes"]) or "ninguno")
        self.chat.reset(self.system_prompt(resume))
        self.turns = 0
        log.info("copilot context compacted after %s lines", len(transcript))
