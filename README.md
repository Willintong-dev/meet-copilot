# Meet Copilot

Traductor y copiloto en vivo para llamadas en inglés (Google Meet, Zoom o cualquier app que suene en el Mac), pensado para hispanohablantes que no dominan del todo el idioma.

- **Oye** el audio del sistema (lo que dicen los demás) y tu micrófono por separado, sin drivers virtuales como BlackHole.
- **Transcribe en tu Mac** con [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper): el audio nunca sale del equipo.
- **Traduce** cada frase al español con Claude Haiku (~1 s).
- **Te contesta las preguntas al instante**: cuando alguien pregunta algo, aparece arriba una franja con la respuesta lista para decir en inglés y su versión en español. Lo que Claude tuvo que suponer va subrayado para que lo revises.
- **Te da la visión de conjunto** con Claude Sonnet cada ~20 s: de qué se habla, qué podrías aportar y qué quedó pendiente. También puedes hacerle preguntas privadas.
- **Guarda la llamada**: transcripción, preguntas con sus respuestas y un resumen final, reutilizables como contexto en la siguiente llamada.

## Requisitos

- Mac con Apple Silicon (M1 o posterior) y macOS 13 Ventura o superior.
- [uv](https://docs.astral.sh/uv/) (`brew install uv`).
- [Claude Code](https://docs.claude.com/en/docs/claude-code) con la sesión iniciada. La app usa Claude a través de [`claude-agent-sdk`](https://github.com/anthropics/claude-agent-sdk-python) con esa misma sesión, así que no necesitas una API key aparte; el consumo cuenta contra tu plan de Claude.
- ~2 GB libres para el modelo de whisper.
- Audífonos (muy recomendado, ver más abajo).

## Instalación

```bash
git clone https://github.com/Willintong-dev/meet-copilot.git
cd meet-copilot
./scripts/install.sh
```

El script:

1. Instala Python y las dependencias en `.venv` con `uv sync`.
2. Descarga el modelo `whisper-large-v3-turbo` (solo la primera vez, ~1.6 GB).
3. Crea el lanzador **`~/Applications/Meet Copilot.app`**.

Para usar otro puerto que el 8777: `MEET_COPILOT_PORT=8790 ./scripts/install.sh`.

### Permisos de macOS

La primera vez que empiezas a escuchar, macOS pide dos permisos para "Meet Copilot":

- **Micrófono**.
- **Grabación de pantalla y audio del sistema** (solo se usa el audio).

Si no aparece el aviso o la app no capta nada, revísalos en *Ajustes del Sistema → Privacidad y seguridad*. Al reinstalar la app es posible que macOS los vuelva a pedir.

## Uso

1. Abre **Meet Copilot** desde `~/Applications` (o corre `uv run meet-copilot`). Se abre http://127.0.0.1:8777 en el navegador.
2. Prepara la llamada:
   - **Nombre de la llamada**.
   - **Brief** (opcional): cualquier archivo `.md` que dejes en `data/briefs/` aparece en la lista. Ponle agenda, participantes, datos que necesitas tener a mano y lo que no debes comprometer.
   - **Mis notas**: el objetivo de la llamada y cualquier contexto rápido.
   - **Extensión de las respuestas**: *desarrollada* (2-3 frases) o *breve* (una frase).
   - **Llamadas anteriores**: marca las que quieras usar como contexto; se incluye su resumen.
3. Pulsa **Empezar a escuchar** y entra a tu llamada.
4. Durante la llamada:
   - **Izquierda**: la transcripción traducida. Las preguntas quedan marcadas con una franja ámbar.
   - **Arriba**: la respuesta sugerida a la última pregunta. Clic en el texto en inglés para copiarlo. Se oculta sola a los 90 s o con la ×.
   - **Barra del encabezado**: una marca por pregunta; clic para saltar a ella.
   - **Derecha**: el copiloto, con la visión de conjunto y una caja para consultarle en privado.
5. **Terminar llamada** genera el resumen.

La primera respuesta tarda unos segundos más porque abre la conexión con Claude; las siguientes salen en 1-2 s.

### Audífonos

Con parlantes, tu micrófono también capta a los demás. La app descarta esos ecos (por coincidencia de voz y de texto), pero con audífonos la transcripción de lo que tú dices sale mucho más limpia.

## Configuración

Opcional. Copia el ejemplo y edítalo:

```bash
cp config.example.toml config.toml
```

| Clave | Por defecto | Qué hace |
|---|---|---|
| `user_name` | tu nombre de la cuenta de macOS | Cómo te llama el copiloto; sirve para saber si la pregunta va para ti |
| `call_language` | `en` | Idioma de los demás en la llamada |
| `my_language` | `es` | Tu idioma; lo que dices en él no se traduce |
| `translator_model` | `haiku` | Modelo para traducir |
| `answer_model` | `haiku` | Modelo para responder preguntas al instante |
| `copilot_model` | `sonnet` | Modelo para la visión de conjunto y el resumen |
| `answer_length` | `desarrollada` | `desarrollada` o `breve` |
| `copilot_interval_seconds` | `20` | Cada cuánto se actualiza el panel del copiloto |
| `silence_ms` | `500` | Silencio que corta una frase |
| `max_segment_seconds` | `12` | Largo máximo de un fragmento de audio |
| `capture_microphone` | `true` | Transcribir también tu micrófono |
| `whisper_model` | `mlx-community/whisper-large-v3-turbo` | Modelo de transcripción |
| `home` | `./data` | Dónde se guardan briefs y llamadas |

## Qué se guarda y dónde

Todo queda en `data/` (excluida de git):

```
data/
├── briefs/                     # tus briefs .md
├── sessions/<fecha>-<nombre>/
│   ├── meta.json
│   ├── context.md              # brief + notas usados en la llamada
│   ├── transcript.jsonl / .md  # transcripción con traducción y preguntas respondidas
│   ├── answers.jsonl           # respuestas sugeridas
│   ├── copilot.jsonl           # consejos del copiloto
│   └── summary.md              # resumen final
└── meet-copilot.log
```

Solo el texto transcrito (no el audio) se envía a Claude.

## Cómo funciona

```
SystemAudioSource ─┐                                    ┌─ Translator (Haiku) ──────┐
MicrophoneSource ──┴─ VAD + Segmenter ─ Transcriber ────┼─ detector de preguntas ── Responder (Haiku) ─┼─ EventBus ─ SSE ─ UI
                      (filtro de eco)   (mlx-whisper)   └─ Copilot (Sonnet) ────────┘
                                                          SessionStore (data/sessions)
```

- El audio del sistema llega por ScreenCaptureKit y el micrófono por `sounddevice`. Un VAD (webrtcvad) corta la voz en frases.
- Las frases de tu micrófono que coinciden con lo que estaba diciendo otra persona, o que whisper detecta en un idioma inesperado, se descartan.
- El detector de preguntas une los fragmentos de una misma frase y la evalúa por cláusulas, en inglés y español: inversión sujeto-auxiliar, saludos, verificaciones ("can you hear me?"), peticiones ("walk me through it") e invitaciones ("any questions?"). Ignora muletillas como "…, right?". Claude hace de segundo filtro y descarta las preguntas retóricas.

## Desarrollo

```bash
uv run pytest
uv run meet-copilot --no-browser --port 8790
```

## Problemas comunes

- **La app abre el navegador pero sigue la versión vieja**: había una instancia corriendo. Pulsa *Salir* en la página y vuelve a abrir la app.
- **No transcribe a los demás**: falta el permiso de grabación de pantalla y audio del sistema.
- **"No pude conectar con Claude"**: abre `claude` en una terminal y verifica que la sesión está iniciada.
- **Logs**: `data/meet-copilot.log` y `data/stdout.log`.

## Aviso

Avisa a los participantes cuando transcribas una llamada; en varias jurisdicciones es obligatorio.
