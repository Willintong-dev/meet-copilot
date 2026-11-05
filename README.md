# Meet Copilot

Traductor y copiloto en vivo para llamadas de Google Meet, 100% local salvo las llamadas a Claude.

- **Oye** el audio del Mac (lo que dicen los demás, vía ScreenCaptureKit, sin drivers virtuales) y tu micrófono, por separado.
- **Transcribe** en el Mac con mlx-whisper (`whisper-large-v3-turbo`, ~0.7 s por frase).
- **Traduce** al español con Claude Haiku (~1 s por frase).
- **Te sopla** con Claude Sonnet: de qué se habla, si te hicieron una pregunta, 2-3 frases en inglés para responder (clic = copiar) y pendientes. Puedes hacerle consultas privadas.
- **Recuerda**: al terminar guarda transcripción y resumen en `data/sessions/`, reutilizables como contexto en la próxima llamada.

## Uso

1. (Opcional) En Claude Code: `/meet-prep` (o "prepara la llamada con Acme"). Arma un brief desde Calendar, Gmail, Drive, Glean, Slack, web y llamadas previas en `data/briefs/`.
2. Abre **Meet Copilot** (`~/Applications/Meet Copilot.app`) o corre `uv run meet-copilot`. Se abre http://127.0.0.1:8777.
3. Elige el brief, escribe tus notas, marca llamadas previas y dale **Empezar a escuchar**.
4. Entra a Meet. Usa audífonos: si los demás salen por parlantes, el micrófono los oye y esas frases se descartan como eco.
5. **Terminar llamada** genera el resumen.

La primera vez macOS pide permiso de **Micrófono** y de **Grabación de pantalla y audio del sistema** para "Meet Copilot".

## Instalación

```bash
./scripts/install.sh          # uv sync + crea ~/Applications/Meet Copilot.app
cp config.example.toml config.toml   # opcional
uv run pytest
```

Claude se usa vía `claude-agent-sdk` con la sesión de Claude Code del Mac (sin API key aparte).

## Arquitectura

```
SystemAudioSource ─┐                                   ┌─ Translator (Haiku) ─┐
MicrophoneSource ──┴─ VAD + Segmenter ─ Transcriber ───┤                      ├─ EventBus ─ SSE ─ UI
                       (eco: ActivityLog)  (mlx-whisper)└─ Copilot (Sonnet) ───┘
                                                         SessionStore (data/sessions)
```

## Aviso

Avisa a los participantes cuando transcribas una llamada; en varias jurisdicciones es obligatorio.
