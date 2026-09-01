"""Cliente MCP que descubre herramientas y ejecuta llamadas locales."""

from contextlib import AsyncExitStack
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any

from mcp import Client, StdioServerParameters

from architecture_assistant.mcp_log import McpInteractionLog


@dataclass(frozen=True)
class McpTool:
    """Herramienta MCP con un nombre único para el anfitrión."""

    public_name: str
    server_name: str
    server_tool_name: str
    description: str
    input_schema: dict[str, Any]


class McpManager:
    """Mantiene clientes MCP conectados durante la sesión del chatbot."""

    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self._clients: dict[str, Client] = {}
        self._tools: dict[str, McpTool] = {}
        self.log = McpInteractionLog()

    @property
    def tools(self) -> tuple[McpTool, ...]:
        """Devuelve las herramientas descubiertas de todos los servidores."""
        return tuple(self._tools.values())

    async def connect_demo_server(self) -> tuple[McpTool, ...]:
        """Inicia el servidor local de prueba y descubre sus herramientas."""
        server_file = Path(__file__).with_name("demo_server.py")
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(server_file)],
            cwd=Path.cwd(),
            env=dict(os.environ),
        )
        return await self.connect_stdio("demostracion", parameters)

    async def connect_stdio(
        self, server_name: str, parameters: StdioServerParameters
    ) -> tuple[McpTool, ...]:
        """Conecta un servidor stdio y registra todas sus herramientas."""
        if server_name in self._clients:
            raise ValueError(f"El servidor MCP '{server_name}' ya está conectado.")

        client = Client(parameters)
        await self._stack.enter_async_context(client)
        discovered = await client.list_tools()
        server_tools: list[McpTool] = []

        for tool in discovered.tools:
            public_name = f"{server_name}__{tool.name}"
            if public_name in self._tools:
                raise ValueError(f"La herramienta MCP '{public_name}' ya existe.")

            registered = McpTool(
                public_name=public_name,
                server_name=server_name,
                server_tool_name=tool.name,
                description=tool.description or "Herramienta MCP sin descripción.",
                input_schema=tool.input_schema,
            )
            self._tools[public_name] = registered
            server_tools.append(registered)

        self._clients[server_name] = client
        return tuple(server_tools)

    def gemini_tools(self) -> list[dict[str, Any]]:
        """Convierte los esquemas MCP al formato de funciones de Gemini."""
        return [
            {
                "type": "function",
                "name": tool.public_name,
                "description": (
                    f"Herramienta del servidor MCP '{tool.server_name}'. "
                    f"{tool.description}"
                ),
                "parameters": tool.input_schema,
            }
            for tool in self.tools
        ]

    async def call_tool(self, public_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta una herramienta descubierta y registra el resultado."""
        tool = self._tools.get(public_name)
        if tool is None:
            raise ValueError(f"La herramienta MCP '{public_name}' no existe.")

        client = self._clients[tool.server_name]
        response = await client.call_tool(tool.server_tool_name, arguments)
        text_parts = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        result = {
            "text": "\n".join(text_parts),
            "structured_content": response.structured_content,
            "is_error": response.is_error,
        }
        self.log.add(
            server_name=tool.server_name,
            tool_name=tool.server_tool_name,
            arguments=arguments,
            result=result,
            is_error=response.is_error,
        )
        return result

    async def close(self) -> None:
        """Cierra ordenadamente todos los procesos y conexiones MCP."""
        await self._stack.aclose()

    def describe_tools(self) -> str:
        """Crea una descripción breve de las herramientas para el estado visual."""
        return json.dumps([tool.public_name for tool in self.tools], ensure_ascii=False)
