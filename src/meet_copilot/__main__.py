import argparse
import logging
import threading
import webbrowser

from meet_copilot.claude import EventLoopThread
from meet_copilot.config import load_settings
from meet_copilot.events import EventBus
from meet_copilot.server import Controller, serve
from meet_copilot.transcriber import Transcriber

log = logging.getLogger("meet_copilot")


def main():
    parser = argparse.ArgumentParser(prog="meet-copilot", description="Traductor y copiloto en vivo para Google Meet")
    parser.add_argument("--no-browser", action="store_true", help="no abrir el navegador al arrancar")
    parser.add_argument("--port", type=int, help="puerto local (por defecto 8777)")
    args = parser.parse_args()
    settings = load_settings()
    if args.port:
        settings.port = args.port
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(settings.home / "meet-copilot.log")],
    )
    transcriber = Transcriber(settings.whisper_model)
    threading.Thread(target=transcriber.warmup, daemon=True, name="whisper-warmup").start()
    controller = Controller(settings, EventBus(), transcriber, EventLoopThread())
    server = serve(controller, settings.host, settings.port)
    url = f"http://{settings.host}:{settings.port}"
    log.info("meet-copilot listo en %s", url)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if controller.session is not None:
            controller.session.stop()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
