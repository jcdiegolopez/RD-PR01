import asyncio
from pathlib import Path
import sys

SOURCE_DIRECTORY = Path(__file__).parent / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from architecture_assistant.main import run as run_cli
from architecture_assistant.tui_app import run_tui


if __name__ == "__main__":
    if "--cli" in sys.argv or "-c" in sys.argv:
        run_cli()
    else:
        try:
            asyncio.run(run_tui())
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

