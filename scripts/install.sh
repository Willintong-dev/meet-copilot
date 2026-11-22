#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HOME/Applications/Meet Copilot.app"
PORT="${MEET_COPILOT_PORT:-8777}"

cd "$ROOT"
uv sync --python-preference only-managed --quiet
uv run --quiet python -c "from huggingface_hub import snapshot_download; from meet_copilot.config import load_settings; snapshot_download(load_settings().whisper_model)"
mkdir -p "$ROOT/data" "$APP/Contents/MacOS"
cat >"$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>io.github.willintong-dev.meet-copilot</string>
  <key>CFBundleName</key><string>Meet Copilot</string>
  <key>CFBundleExecutable</key><string>meet-copilot</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>LSUIElement</key><true/>
  <key>LSArchitecturePriority</key><array><string>arm64</string></array>
  <key>NSMicrophoneUsageDescription</key><string>Meet Copilot transcribe lo que dices en tus llamadas.</string>
  <key>NSAudioCaptureUsageDescription</key><string>Meet Copilot escucha el audio de tus llamadas para traducirlo.</string>
</dict>
</plist>
PLIST
cat >"$APP/Contents/MacOS/meet-copilot" <<LAUNCHER
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HF_HUB_OFFLINE=1
if /usr/bin/curl -sf "http://127.0.0.1:$PORT/api/state" | /usr/bin/grep -q briefs; then
  exec /usr/bin/open "http://127.0.0.1:$PORT"
fi
cd "$ROOT"
exec /usr/bin/arch -arm64 "$ROOT/.venv/bin/python" -m meet_copilot --port $PORT >>"$ROOT/data/stdout.log" 2>&1
LAUNCHER
chmod +x "$APP/Contents/MacOS/meet-copilot"
codesign --force --deep -s - "$APP"
echo "installed $APP"
