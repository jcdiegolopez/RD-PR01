"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


DEFAULT_MODEL = "gemini-3.5-flash-lite"
LEGACY_MODELS = {"gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"}


@dataclass(frozen=True)
class Settings:
    """Runtime settings that never expose secret values in logs."""

    gemini_api_key: str | None
    gemini_model: str

    @classmethod
    def load(cls) -> "Settings":
        """Load local .env values and return validated application settings."""
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key == "replace_with_your_google_ai_studio_key":
            api_key = None

        configured_model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        if configured_model in LEGACY_MODELS:
            configured_model = DEFAULT_MODEL

        return cls(
            gemini_api_key=api_key,
            gemini_model=configured_model,
        )
