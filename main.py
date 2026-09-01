"""Convenient local entry point for the console chatbot.

Run with: .\\.venv\\Scripts\\python.exe main.py
"""

from pathlib import Path
import sys


SOURCE_DIRECTORY = Path(__file__).parent / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from architecture_assistant.main import run


if __name__ == "__main__":
    run()
