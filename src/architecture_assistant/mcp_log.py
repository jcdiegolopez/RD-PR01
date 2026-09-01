"""Registro en memoria de las llamadas realizadas a servidores MCP."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class McpLogEntry:
    """Representa una solicitud y su respuesta dentro de una sesión."""

    timestamp: datetime
    server_name: str
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    is_error: bool


class McpInteractionLog:
    """Almacena las interacciones MCP sin incluir secretos de configuración."""

    def __init__(self) -> None:
        self._entries: list[McpLogEntry] = []

    @property
    def entries(self) -> tuple[McpLogEntry, ...]:
        """Devuelve las interacciones registradas durante la sesión actual."""
        return tuple(self._entries)

    def add(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        is_error: bool,
    ) -> McpLogEntry:
        """Guarda y devuelve una nueva interacción MCP."""
        entry = McpLogEntry(
            timestamp=datetime.now(),
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            is_error=is_error,
        )
        self._entries.append(entry)
        return entry
