import re
import time
import unicodedata
from dataclasses import dataclass, field

FLAGS = re.IGNORECASE

ENGLISH = {
    "wh": (re.compile(r"\b(what|what's|which|who|whose|whom|when|where|why|how|how's)\b", FLAGS), 3),
    "wh_inversion": (
        re.compile(
            r"^(?:(?:so|and|but|ok|okay|well|now|then|alright|all right|yeah|yes|um|uh)[\s,]+)*"
            r"(what|which|who|when|where|why|how)(?:'s)?\s+(do|does|did|is|are|was|were|can|could|will|would|should|shall|have|has|had|am|may|might)\b",
            FLAGS,
        ),
        3,
    ),
    "auxiliary": (
        re.compile(
            r"^(?:(do|have)\s+(you|we|i|they|he|she|it|there|any|anyone|anybody|someone|everyone)"
            r"|(does|did|is|are|was|were|am|can|could|will|would|should|shall|has|had|may|might)\s+"
            r"(you|we|i|they|he|she|it|there|that|this|any|anyone|anybody|someone|everyone|the|my|your|our))\b",
            FLAGS,
        ),
        4,
    ),
    "tag": (re.compile(r"\b(does that make sense|make sense|any questions|any doubts|is that clear)\s*\??$", FLAGS), 4),
    "invite": (re.compile(r"\b(any questions|anyone have|does anyone|any thoughts|what do you (think|guys think)|feel free to ask|questions so far)\b", FLAGS), 4),
    "request": (
        re.compile(
            r"^(?:(?:so|ok|okay|now|and|alright|well|please|just)[\s,]+)*"
            r"(tell\s+(me|us)|give\s+(me|us)|show\s+(me|us)|walk\s+(me|us)|talk\s+to\s+(me|us)|let\s+(me|us)\s+know|share\s+your|explain|describe|elaborate|clarify|expand\s+on)\b",
            FLAGS,
        ),
        4,
    ),
    "soft_invite": (re.compile(r"\b(your thoughts|i'd like to hear|i would like to hear|i'm curious|i was wondering|feel free to (ask|share)|go ahead)\b", FLAGS), 4),
    "filler": (re.compile(r"^(i (don't )?know|you know|so like|i mean|that's how|this is how|let me show|here's how|the way)\b", FLAGS), -4),
}

SPANISH = {
    "accented": (re.compile(r"\b(qué|quién|quiénes|cuál|cuáles|cómo|cuándo|dónde|adónde|cuánto|cuánta|cuántos|cuántas|por qué|para qué)\b", FLAGS), 3),
    "unaccented_opener": (re.compile(r"^(que|quien|quienes|cual|cuales|como|cuando|donde|cuanto|cuantos|por que)\b", FLAGS), 2),
    "opener": (
        re.compile(
            r"^(me\s+)?(puede[sn]?|podría[sn]?|podemos|sabe[sn]?|tiene[sn]?|hay|existe[n]?|es|son|está[n]?|conoce[sn]?|alguien|alguna|será|sería|debería|se puede|te parece|les parece)\b",
            FLAGS,
        ),
        2,
    ),
    "tag": (re.compile(r"\b(verdad|cierto|no es así|o no|me explico|se entiende|quedó claro|está claro)\s*\??$", FLAGS), 2),
    "invite": (re.compile(r"\b(alguna (pregunta|duda|inquietud)|alguien (tiene|sabe|quiere)|hay preguntas|qué opinan|se les ocurre)\b", FLAGS), 4),
    "request": (
        re.compile(
            r"^(?:(?:bueno|ok|entonces|y|por favor)[\s,]+)*"
            r"(dame|danos|dime|dinos|cuéntame|cuentame|cuéntanos|cuentanos|explícame|explicame|explícanos|explicanos|muéstrame|muestrame|muéstranos|compárteme|comparteme|descríbeme|describeme|háblame|hablame|háblanos)\b",
            FLAGS,
        ),
        4,
    ),
    "filler": (re.compile(r"^(no sé|no se|o sea|es que|digamos)\b", FLAGS), -4),
}

FILLER_TAG = re.compile(r"[,\s¿]*\b(right|you know|i mean|correct|okay|ok|yeah|no|verdad|cierto|me entiendes|sabes)\s*\?$", FLAGS)
CLAUSE_END = re.compile(r"(?<=[.?!])\s+")
QUESTION_MARK_WEIGHT = 5
SHORT_PENALTY = -2
THRESHOLD = 4


def question_score(text):
    stripped = FILLER_TAG.sub(".", (text or "").strip())
    score = QUESTION_MARK_WEIGHT if re.search(r"[?¿]", stripped) else 0
    for pattern, weight in (*ENGLISH.values(), *SPANISH.values()):
        if pattern.search(stripped):
            score += weight
    if len(stripped.split()) < 3:
        score += SHORT_PENALTY
    return score


def is_question(text):
    return any(question_score(clause) >= THRESHOLD for clause in CLAUSE_END.split((text or "").strip()))


def normalize(text):
    plain = unicodedata.normalize("NFD", text.lower())
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn")
    plain = re.sub(r"[^a-z0-9\s]", "", plain)
    return re.sub(r"\s+", " ", plain).strip()


def similar(first, second):
    a, b = normalize(first), normalize(second)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    words_a, words_b = set(a.split()), b.split()
    shared = sum(1 for word in words_b if word in words_a)
    return shared / max(len(words_a), len(words_b)) > 0.7


@dataclass
class Sentence:
    text: str
    line_ids: list
    started_at: float


@dataclass
class SentenceBuffer:
    max_words: int = 40
    max_age_seconds: float = 9.0
    pause_seconds: float = 2.5
    clock: callable = time.time
    parts: list = field(default_factory=list)
    line_ids: list = field(default_factory=list)
    started_at: float = 0.0
    last_added: float = 0.0

    def add(self, line_id, text, started_at):
        if not self.parts:
            self.started_at = started_at
        self.parts.append(text.strip())
        self.line_ids.append(line_id)
        self.last_added = self.clock()
        joined = " ".join(self.parts)
        asks = joined.rstrip().endswith("?")
        too_long = len(joined.split()) >= self.max_words
        too_old = self.last_added - self.started_at >= self.max_age_seconds
        return self.flush() if asks or too_long or too_old else None

    def flush_if_paused(self):
        if self.parts and self.clock() - self.last_added >= self.pause_seconds:
            return self.flush()
        return None

    def flush(self):
        if not self.parts:
            return None
        sentence = Sentence(" ".join(self.parts), list(self.line_ids), self.started_at)
        self.parts, self.line_ids = [], []
        return sentence
