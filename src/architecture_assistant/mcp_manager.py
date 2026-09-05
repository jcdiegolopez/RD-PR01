"""Cliente MCP que descubre herramientas y ejecuta llamadas locales."""

from contextlib import AsyncExitStack
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from architecture_assistant.mcp_log import McpInteractionLog


@dataclass(frozen=True)
class McpTool:
    """Herramienta MCP con un nombre único para el anfitrión."""

    public_name: str
    server_name: str
    server_tool_name: str
    description: str
    input_schema: dict[str, Any]
    requires_confirmation: bool


class McpManager:
    """Mantiene clientes MCP conectados durante la sesión del chatbot."""

    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self._clients: dict[str, ClientSession] = {}
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
            cwd=str(Path.cwd()),
            env=dict(os.environ),
        )
        return await self.connect_stdio("demostracion", parameters)

    # ── config-based connection ──────────────────────────────────────────────

    @staticmethod
    def load_server_configs(config_path: Path) -> dict[str, dict[str, Any]]:
        """Lee mcp_servers.json y devuelve el dict de 'mcpServers'."""
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("mcpServers", {})

    @staticmethod
    def _resolve(value: str, env: dict[str, str]) -> str:
        """Sustituye ${VAR} con variables de entorno y __python__ con sys.executable."""
        if value == "__python__":
            return sys.executable
        return re.sub(
            r"\$\{([^}]+)\}",
            lambda m: env.get(m.group(1), m.group(0)),
            value,
        )

    async def connect_from_config(
        self, server_name: str, server_config: dict[str, Any]
    ) -> tuple[McpTool, ...]:
        """Conecta un servidor MCP usando la definición del archivo de configuración.

        Soporta los mismos campos que Claude Desktop:
          command, args, cwd, env
        Tokens especiales en command/args/cwd:
          __python__   → sys.executable actual
          ${VAR}       → variable de entorno VAR
        """
        env_snapshot = dict(os.environ)
        # Merge server-specific env vars (también con interpolación)
        for key, val in server_config.get("env", {}).items():
            env_snapshot[key] = self._resolve(val, env_snapshot)

        command = self._resolve(server_config["command"], env_snapshot)
        args = [self._resolve(a, env_snapshot) for a in server_config.get("args", [])]
        raw_cwd = server_config.get("cwd", str(Path.cwd()))
        cwd = self._resolve(raw_cwd, env_snapshot)

        parameters = StdioServerParameters(
            command=command,
            args=args,
            cwd=cwd,
            env=env_snapshot,
        )
        return await self.connect_stdio(server_name, parameters)

    @staticmethod
    def is_git_repository(workspace: Path) -> bool:
        """Indica si el espacio aislado ya contiene su propio repositorio Git."""
        return (workspace / ".git").is_dir()

    @staticmethod
    def initialize_demo_repository(workspace: Path) -> None:
        """Inicializa Git solo dentro del espacio aislado tras autorización explícita."""
        completed = subprocess.run(
            ["git", "init", str(workspace)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"No fue posible inicializar Git: {detail}")

    async def connect_stdio(
        self, server_name: str, parameters: StdioServerParameters
    ) -> tuple[McpTool, ...]:
        """Conecta un servidor stdio y registra todas sus herramientas."""
        if server_name in self._clients:
            raise ValueError(f"El servidor MCP '{server_name}' ya está conectado.")

        read_stream, write_stream = await self._stack.enter_async_context(
            stdio_client(parameters)
        )
        client = await self._stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await client.initialize()
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
                input_schema=tool.inputSchema,
                requires_confirmation=self._requires_confirmation(
                    server_name, tool.name, getattr(tool, "annotations", None)
                ),
            )
            self._tools[public_name] = registered
            server_tools.append(registered)

        self._clients[server_name] = client
        return tuple(server_tools)

    def get_tool(self, public_name: str) -> McpTool:
        """Obtiene una herramienta registrada o indica claramente si no existe."""
        tool = self._tools.get(public_name)
        if tool is None:
            raise ValueError(f"La herramienta MCP '{public_name}' no existe.")
        return tool

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

    def record_cancelled_call(
        self, public_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Registra una operación rechazada sin enviarla al servidor MCP."""
        tool = self.get_tool(public_name)
        result = {
            "text": "La operación fue cancelada por la persona usuaria.",
            "structured_content": None,
            "is_error": True,
        }
        self.log.add(
            server_name=tool.server_name,
            tool_name=tool.server_tool_name,
            arguments=arguments,
            result=result,
            is_error=True,
        )
        return result

    async def call_tool(
        self, public_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Ejecuta una herramienta descubierta y registra el resultado."""
        tool = self.get_tool(public_name)
        client = self._clients[tool.server_name]
        response = await client.call_tool(tool.server_tool_name, arguments)
        text_parts = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        result = {
            "text": "\n".join(text_parts),
            "structured_content": getattr(response, "structuredContent", None),
            "is_error": bool(getattr(response, "isError", False)),
        }
        self.log.add(
            server_name=tool.server_name,
            tool_name=tool.server_tool_name,
            arguments=arguments,
            result=result,
            is_error=result["is_error"],
        )
        return result

    async def close(self) -> None:
        """Cierra ordenadamente todos los procesos y conexiones MCP."""
        await self._stack.aclose()

    @staticmethod
    def _requires_confirmation(
        server_name: str, tool_name: str, annotations: Any
    ) -> bool:
        """Aplica una política conservadora: ante duda, solicita confirmación."""
        # El servidor de arquitectura es completamente de solo lectura
        if server_name == "architecture":
            return False

        if server_name not in {"filesystem", "git"}:
            return False

        if annotations is not None and getattr(annotations, "readOnlyHint", None) is True:
            return False

        read_only_prefixes = (
            "read_",
            "list_",
            "search_",
            "get_",
            "directory_tree",
            "git_status",
            "git_diff",
            "git_log",
            "git_show",
            "git_branch",
            "git_remote",
            "git_tag",
        )
        return not tool_name.lower().startswith(read_only_prefixes)
