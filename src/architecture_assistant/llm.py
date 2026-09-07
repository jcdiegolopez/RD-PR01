"""Adaptador de Gemini utilizado por el anfitrión de consola.

Mantener el proveedor detrás de esta clase permitirá agregar NVIDIA NIM como
alternativa sin cambiar la interfaz de terminal ni la lógica de MCP.
"""

from google import genai
from google.genai import errors
import time
from dataclasses import dataclass
from typing import Any


MAX_SERVER_RETRIES = 2


class ProviderUnavailableError(RuntimeError):
    """Se lanza después de reintentar errores temporales del proveedor."""


@dataclass(frozen=True)
class FunctionCall:
    """Solicitud de una herramienta emitida por Gemini."""

    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    """Respuesta textual y solicitudes de herramientas de una interacción."""

    interaction_id: str
    text: str | None
    function_calls: tuple[FunctionCall, ...]


SYSTEM_INSTRUCTION = (
    "Eres un asistente inteligente conectado a un anfitrión MCP (Model Context Protocol). "
    "Tienes acceso a diferentes herramientas y servidores MCP independientes.\n"
    "Cada servidor y herramienta tiene su propio alcance y parámetros; "
    "no asumas que las restricciones o límites de un servidor aplican a los demás. "
    "Cuando el usuario te pida una tarea, invoca directamente la herramienta MCP correspondiente "
    "sin asumir bloqueos cruzados entre servidores. "
    "Responde siempre en español de forma clara, directa y estructurada."
)


class GeminiProvider:
    """Sesión con estado de Gemini mediante Interactions API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        system_instruction: str | None = None,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.system_instruction = system_instruction
        self._previous_interaction_id: str | None = None

    def ask(self, message: str) -> str:
        """Envía un mensaje sin herramientas y devuelve el texto de Gemini."""
        turn = self.start_turn(message, tools=[])
        return turn.text or "El modelo devolvió una respuesta vacía."

    def start_turn(self, message: str, tools: list[dict[str, Any]]) -> ModelTurn:
        """Inicia un turno y devuelve el texto o las herramientas solicitadas."""
        request: dict[str, Any] = {"model": self.model, "input": message}
        if self.system_instruction:
            request["system_instruction"] = self.system_instruction
        if tools:
            request["tools"] = tools
        if self._previous_interaction_id:
            request["previous_interaction_id"] = self._previous_interaction_id

        interaction = self._request_with_retry(request)
        self._previous_interaction_id = interaction.id
        return self._to_model_turn(interaction)

    def submit_function_results(
        self,
        interaction_id: str,
        function_results: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelTurn:
        """Entrega resultados de herramientas a Gemini y continúa el turno."""
        request: dict[str, Any] = {
            "model": self.model,
            "input": function_results,
            "previous_interaction_id": interaction_id,
        }
        if self.system_instruction:
            request["system_instruction"] = self.system_instruction
        if tools:
            request["tools"] = tools

        interaction = self._request_with_retry(request)
        self._previous_interaction_id = interaction.id
        return self._to_model_turn(interaction)

    def reset_context(self) -> None:
        """Inicia una sesión nueva y conserva el modelo configurado."""
        self._previous_interaction_id = None

    def _request_with_retry(self, request: dict[str, Any]):
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

    @staticmethod
    def _to_model_turn(interaction: Any) -> ModelTurn:
        """Extrae llamadas de función del formato de pasos de Interactions API."""
        function_calls = tuple(
            FunctionCall(
                call_id=step.id,
                name=step.name,
                arguments=dict(step.arguments or {}),
            )
            for step in interaction.steps
            if step.type == "function_call"
        )
        return ModelTurn(
            interaction_id=interaction.id,
            text=interaction.output_text,
            function_calls=function_calls,
        )
