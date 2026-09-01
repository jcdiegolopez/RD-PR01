"""Configuración de la aplicación cargada desde variables de entorno."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


DEFAULT_MODEL = "gemini-3.5-flash-lite"
LEGACY_MODELS = {"gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"}


@dataclass(frozen=True)
class Settings:
    """Configuración de ejecución que no expone secretos en los registros."""

    gemini_api_key: str | None
    gemini_model: str

    @classmethod
    def load(cls) -> "Settings":
        """Carga los valores de .env y devuelve una configuración validada."""
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key == "reemplaza_con_tu_clave_de_google_ai_studio":
            api_key = None

        configured_model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        if configured_model in LEGACY_MODELS:
            configured_model = DEFAULT_MODEL

        return cls(
            gemini_api_key=api_key,
            gemini_model=configured_model,
        )
