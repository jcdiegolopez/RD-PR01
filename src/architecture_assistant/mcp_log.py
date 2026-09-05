"""Registro en memoria de las llamadas realizadas a servidores MCP."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class McpLogEntry:
    """Representa una solicitud y su respuesta dentro de una sesión, con métricas de red."""

    timestamp: datetime
    server_name: str
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    is_error: bool
    transport: str = "stdio"
    latency_ms: float = 0.0
    request_size: int = 0
    response_size: int = 0
    protocol: str = "JSON-RPC 2.0"
    status_code: str = "200 OK"


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
        transport: str = "stdio",
        latency_ms: float = 0.0,
        request_size: int = 0,
        response_size: int = 0,
        protocol: str = "JSON-RPC 2.0",
        status_code: str = "200 OK",
    ) -> McpLogEntry:
        """Guarda y devuelve una nueva interacción MCP con métricas de protocolo."""
        entry = McpLogEntry(
            timestamp=datetime.now(),
            server_name=server_name,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            is_error=is_error,
            transport=transport,
            latency_ms=latency_ms,
            request_size=request_size,
            response_size=response_size,
            protocol=protocol,
            status_code=status_code,
        )
        self._entries.append(entry)
        return entry

