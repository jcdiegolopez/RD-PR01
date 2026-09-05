"""Configuración de la aplicación cargada desde variables de entorno."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_MODEL = "gemini-3.5-flash-lite"
LEGACY_MODELS = {"gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"}


@dataclass(frozen=True)
class Settings:
    """Configuración de ejecución que no expone secretos en los registros."""

    gemini_api_key: str | None
    gemini_model: str
    mcp_demo_workspace: Path
    arch_server_path: Path | None

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

        workspace_value = os.getenv("MCP_DEMO_WORKSPACE", "data/mcp-demo-workspace")
        workspace = Path(workspace_value)
        if not workspace.is_absolute():
            workspace = Path.cwd() / workspace

        arch_value = os.getenv("ARCH_SERVER_PATH", "")
        arch_server_path: Path | None = None
        if arch_value:
            p = Path(arch_value)
            if not p.is_absolute():
                p = Path.cwd() / p
            arch_server_path = p.resolve()

        return cls(
            gemini_api_key=api_key,
            gemini_model=configured_model,
            mcp_demo_workspace=workspace.resolve(),
            arch_server_path=arch_server_path,
        )
