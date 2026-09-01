"""Adaptador de Gemini utilizado por el anfitrión de consola.

Mantener el proveedor detrás de esta clase permitirá agregar NVIDIA NIM como
alternativa sin cambiar la interfaz de terminal ni la lógica de MCP.
"""

from google import genai
from google.genai import errors
import time


MAX_SERVER_RETRIES = 2


class ProviderUnavailableError(RuntimeError):
    """Se lanza después de reintentar errores temporales del proveedor."""


class GeminiProvider:
    """Sesión con estado de Gemini mediante Interactions API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self._previous_interaction_id: str | None = None

    def ask(self, message: str) -> str:
        """Envía un mensaje del usuario y devuelve la respuesta de Gemini."""
        request: dict[str, str] = {"model": self.model, "input": message}
        if self._previous_interaction_id:
            request["previous_interaction_id"] = self._previous_interaction_id

        interaction = self._request_with_retry(request)
        self._previous_interaction_id = interaction.id
        return interaction.output_text or "El modelo devolvió una respuesta vacía."

    def reset_context(self) -> None:
        """Inicia una sesión nueva y conserva el modelo configurado."""
        self._previous_interaction_id = None

    def _request_with_retry(self, request: dict[str, str]):
        """Reintenta errores 5xx temporales con una espera breve."""
        for attempt in range(MAX_SERVER_RETRIES + 1):
            try:
                return self._client.interactions.create(**request)
            except errors.ServerError as error:
                if attempt == MAX_SERVER_RETRIES:
                    raise ProviderUnavailableError(
                        "Gemini no está disponible temporalmente después de varios intentos. "
                        "Intenta de nuevo en un momento."
                    ) from error
                time.sleep(2**attempt)

        raise AssertionError("El ciclo de reintentos debe devolver o lanzar un error.")
