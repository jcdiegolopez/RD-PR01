"""Cliente MCP nativo que descubre herramientas y ejecuta llamadas locales y remotas
mediante intercambio directo de mensajes JSON-RPC 2.0 sin utilizar el SDK de MCP.
"""

import asyncio
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

import httpx

from architecture_assistant.mcp_log import McpInteractionLog


class JsonRpcError(Exception):
    """Error devuelto por un servidor JSON-RPC 2.0."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data


@dataclass
class StdioServerParameters:
    """Parámetros de proceso para un servidor MCP basado en stdio."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | Path | None = None


@dataclass(frozen=True)
class McpTool:
    """Herramienta MCP con un nombre único para el anfitrión."""

    public_name: str
    server_name: str
    server_tool_name: str
    description: str
    input_schema: dict[str, Any]
    requires_confirmation: bool


class NativeJsonRpcStdioClient:
    """Cliente JSON-RPC 2.0 asíncrono sobre stdio sin librerías externas."""

    def __init__(self, parameters: StdioServerParameters) -> None:
        self.parameters = parameters
        self.process: asyncio.subprocess.Process | None = None
        self._pending_requests: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id: int = 1
        self._read_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._closed: bool = False

    async def start(self) -> None:
        """Inicia el subproceso del servidor MCP y sus bucles de lectura."""
        cmd = self.parameters.command
        args = list(self.parameters.args)
        cwd = str(self.parameters.cwd) if self.parameters.cwd else None
        env = self.parameters.env

        self.process = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        self._read_task = asyncio.create_task(self._stdout_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())

    async def _stdout_loop(self) -> None:
        """Lee mensajes JSON-RPC 2.0 delimitados por saltos de línea desde stdout."""
        assert self.process is not None and self.process.stdout is not None
        while not self._closed:
            try:
                line_bytes = await self.process.stdout.readline()
            except Exception:
                break

            if not line_bytes:
                break

            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                msg = json.loads(line)
            except Exception:
                continue

            req_id = msg.get("id")
            if req_id is not None and req_id in self._pending_requests:
                fut = self._pending_requests.pop(req_id)
                if not fut.done():
                    fut.set_result(msg)
            elif req_id is not None and "method" in msg:
                # El servidor solicita una acción al cliente (ej. ping)
                reply = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                try:
                    await self._write_raw(reply)
                except Exception:
                    pass

        # Si el subproceso finaliza, rechazar solicitudes pendientes
        for fut in list(self._pending_requests.values()):
            if not fut.done():
                fut.set_exception(
                    ConnectionError("El proceso del servidor MCP terminó inesperadamente.")
                )
        self._pending_requests.clear()

    async def _stderr_loop(self) -> None:
        """Drena stderr en segundo plano para evitar bloqueos del búfer del SO."""
        assert self.process is not None and self.process.stderr is not None
        while not self._closed:
            try:
                line = await self.process.stderr.readline()
                if not line:
                    break
            except Exception:
                break

    async def _write_raw(self, payload: dict[str, Any]) -> None:
        """Escribe un mensaje JSON-RPC en el stdin del subproceso."""
        if self.process is None or self.process.stdin is None or self._closed:
            raise ConnectionError("El cliente MCP no está conectado.")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        self.process.stdin.write(data)
        await self.process.stdin.drain()

    async def send_request(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 60.0
    ) -> dict[str, Any]:
        """Envía una solicitud JSON-RPC 2.0 y espera la respuesta correspondiente."""
        req_id = self._next_id
        self._next_id += 1

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending_requests[req_id] = fut

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params if params is not None else {},
        }
        await self._write_raw(payload)

        try:
            resp = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise TimeoutError(
                f"Tiempo de espera agotado ({timeout}s) esperando respuesta para '{method}'."
            )

        if "error" in resp:
            err = resp["error"]
            raise JsonRpcError(
                code=err.get("code", -32603),
                message=err.get("message", "Error en servidor JSON-RPC"),
                data=err.get("data"),
            )

        return resp.get("result", {})

    async def send_notification(
        self, method: str, params: dict[str, Any] | None = None
    ) -> None:
        """Envía una notificación JSON-RPC 2.0 sin esperar respuesta."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params if params is not None else {},
        }
        await self._write_raw(payload)

    async def initialize(self) -> dict[str, Any]:
        """Ejecuta el protocolo de inicialización estándar MCP."""
        res = await self.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "RD-PR01", "version": "1.0.0"},
            },
        )
        await self.send_notification("notifications/initialized")
        return res

    async def list_tools(self) -> list[dict[str, Any]]:
        """Descubre las herramientas expuestas por el servidor."""
        res = await self.send_request("tools/list", {})
        return res.get("tools", [])

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Ejecuta una herramienta remota y devuelve el resultado MCP."""
        return await self.send_request(
            "tools/call", {"name": name, "arguments": arguments}
        )

    async def close(self) -> None:
        """Finaliza el subproceso y libera recursos asociados."""
        self._closed = True
        for fut in list(self._pending_requests.values()):
            if not fut.done():
                fut.cancel()
        self._pending_requests.clear()

        if self.process is not None:
            try:
                if self.process.stdin and not self.process.stdin.is_closing():
                    self.process.stdin.close()
            except Exception:
                pass

            try:
                self.process.terminate()
            except Exception:
                pass

            try:
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

        if self._read_task is not None:
            self._read_task.cancel()
        if self._stderr_task is not None:
            self._stderr_task.cancel()


class NativeJsonRpcHttpClient:
    """Cliente JSON-RPC 2.0 sobre HTTP POST sin librerías externas de MCP."""

    def __init__(self, url: str) -> None:
        self.url = url
        self._client = httpx.AsyncClient(timeout=60.0)
        self._next_id: int = 1

    async def send_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Envía una solicitud JSON-RPC 2.0 por POST y parsea el resultado."""
        req_id = self._next_id
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params if params is not None else {},
        }
        resp = await self._client.post(
            self.url,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            err = data["error"]
            raise JsonRpcError(
                code=err.get("code", -32603),
                message=err.get("message", "Error en servidor JSON-RPC HTTP"),
                data=err.get("data"),
            )
        return data.get("result", {})

    async def send_notification(
        self, method: str, params: dict[str, Any] | None = None
    ) -> None:
        """Envía una notificación JSON-RPC 2.0 por POST."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params if params is not None else {},
        }
        try:
            await self._client.post(
                self.url,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
        except Exception:
            pass

    async def initialize(self) -> dict[str, Any]:
        """Ejecuta el protocolo de inicialización estándar MCP sobre HTTP."""
        res = await self.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "RD-PR01", "version": "1.0.0"},
            },
        )
        await self.send_notification("notifications/initialized")
        return res

    async def list_tools(self) -> list[dict[str, Any]]:
        """Descubre las herramientas expuestas por el servidor HTTP."""
        res = await self.send_request("tools/list", {})
        return res.get("tools", [])

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Ejecuta una herramienta remota sobre HTTP y devuelve el resultado MCP."""
        return await self.send_request(
            "tools/call", {"name": name, "arguments": arguments}
        )

    async def close(self) -> None:
        """Cierra el cliente HTTP subyacente."""
        await self._client.aclose()


class McpManager:
    """Mantiene clientes MCP conectados durante la sesión del chatbot mediante JSON-RPC nativo."""

    def __init__(self) -> None:
        self._clients: dict[str, NativeJsonRpcStdioClient | NativeJsonRpcHttpClient] = {}
        self._server_transports: dict[str, str] = {}
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

    async def _connect_stdio_from_config(
        self, server_name: str, server_config: dict[str, Any]
    ) -> tuple[McpTool, ...]:
        """Conecta un servidor stdio usando campos command/args/cwd/env del config JSON."""
        env_snapshot = dict(os.environ)
        for key, val in server_config.get("env", {}).items():
            env_snapshot[key] = self._resolve(val, env_snapshot)

        command = self._resolve(server_config["command"], env_snapshot)
        args = [self._resolve(a, env_snapshot) for a in server_config.get("args", [])]
        raw_cwd = server_config.get("cwd", str(Path.cwd()))
        cwd = self._resolve(raw_cwd, env_snapshot)

        cwd = str(Path(cwd).resolve())
        args = [
            str(Path(a).resolve())
            if (Path(a).suffix or Path(a).is_dir() or Path(a).is_file()) and not a.startswith("-")
            else a
            for a in args
        ]

        parameters = StdioServerParameters(
            command=command,
            args=args,
            cwd=cwd,
            env=env_snapshot,
        )
        return await self.connect_stdio(server_name, parameters)

    async def connect_from_config(
        self, server_name: str, server_config: dict[str, Any]
    ) -> tuple[McpTool, ...]:
        """Detecta el transport del config y delega al método correspondiente."""
        transport = server_config.get("transport", "stdio")
        if transport == "http":
            url = server_config["url"]
            return await self.connect_http(server_name, url)
        return await self._connect_stdio_from_config(server_name, server_config)

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

        client = NativeJsonRpcStdioClient(parameters)
        await client.start()
        await client.initialize()
        discovered = await client.list_tools()
        server_tools: list[McpTool] = []

        for tool in discovered:
            tool_name = tool.get("name", "")
            public_name = f"{server_name}__{tool_name}"
            if public_name in self._tools:
                raise ValueError(f"La herramienta MCP '{public_name}' ya existe.")

            registered = McpTool(
                public_name=public_name,
                server_name=server_name,
                server_tool_name=tool_name,
                description=tool.get("description") or "Herramienta MCP sin descripción.",
                input_schema=tool.get("inputSchema", {}),
                requires_confirmation=self._requires_confirmation(
                    server_name, tool_name, tool.get("annotations")
                ),
            )
            self._tools[public_name] = registered
            server_tools.append(registered)

        self._clients[server_name] = client
        self._server_transports[server_name] = "stdio"
        return tuple(server_tools)

    async def connect_http(
        self, server_name: str, url: str
    ) -> tuple[McpTool, ...]:
        """Conecta un servidor MCP remoto vía JSON-RPC sobre HTTP POST."""
        if server_name in self._clients:
            raise ValueError(f"El servidor MCP '{server_name}' ya está conectado.")

        client = NativeJsonRpcHttpClient(url)
        await client.initialize()
        discovered = await client.list_tools()
        server_tools: list[McpTool] = []

        for tool in discovered:
            tool_name = tool.get("name", "")
            public_name = f"{server_name}__{tool_name}"
            if public_name in self._tools:
                raise ValueError(f"La herramienta MCP '{public_name}' ya existe.")

            registered = McpTool(
                public_name=public_name,
                server_name=server_name,
                server_tool_name=tool_name,
                description=tool.get("description") or "Herramienta MCP sin descripción.",
                input_schema=tool.get("inputSchema", {}),
                requires_confirmation=False,  # Servidores remotos de lectura
            )
            self._tools[public_name] = registered
            server_tools.append(registered)

        self._clients[server_name] = client
        self._server_transports[server_name] = "http"
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
            if tool.server_tool_name != "list_allowed_directories"
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
        """Ejecuta una herramienta descubierta y registra el resultado con métricas de red."""
        tool = self.get_tool(public_name)
        client = self._clients[tool.server_name]
        transport_kind = self._server_transports.get(tool.server_name, "stdio")

        if transport_kind == "http":
            transport_desc = "HTTP / POST (Remote Cloudflare Edge)"
            protocol_desc = "JSON-RPC 2.0 (Native HTTPS Wire)"
        else:
            transport_desc = "Stdio Pipe (Local Process IPC)"
            protocol_desc = "JSON-RPC 2.0 (Native Stdio Wire)"

        start_time = time.perf_counter()
        req_payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool.server_tool_name, "arguments": arguments},
                "id": 1,
            },
            ensure_ascii=False,
        )
        req_bytes = len(req_payload.encode("utf-8"))

        try:
            response = await client.call_tool(tool.server_tool_name, arguments)
            duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

            content_blocks = response.get("content", [])
            text_parts = [
                b.get("text", "")
                for b in content_blocks
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            result_text = "\n".join(text_parts)

            structured = response.get("structuredContent")
            if structured is None and result_text:
                try:
                    structured = json.loads(result_text)
                except Exception:
                    structured = None

            is_error = bool(response.get("isError", False))

            result = {
                "text": result_text,
                "structured_content": structured,
                "is_error": is_error,
            }
        except Exception as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            result = {
                "text": f"Error al ejecutar herramienta: {e}",
                "structured_content": {"error": str(e)},
                "is_error": True,
            }
            result_text = result["text"]

        resp_bytes = len(result_text.encode("utf-8"))

        self.log.add(
            server_name=tool.server_name,
            tool_name=tool.server_tool_name,
            arguments=arguments,
            result=result,
            is_error=result["is_error"],
            transport=transport_desc,
            latency_ms=duration_ms,
            request_size=req_bytes,
            response_size=resp_bytes,
            protocol=protocol_desc,
            status_code="500 Internal Error" if result["is_error"] else "200 OK",
        )
        return result

    async def close(self) -> None:
        """Cierra ordenadamente todos los procesos y conexiones MCP."""
        for client in list(self._clients.values()):
            try:
                await client.close()
            except Exception:
                pass
        self._clients.clear()
        self._tools.clear()
        self._server_transports.clear()

    @staticmethod
    def _requires_confirmation(
        server_name: str, tool_name: str, annotations: Any
    ) -> bool:
        """Aplica una política conservadora: ante duda, solicita confirmación."""
        if server_name == "architecture":
            return False

        if server_name not in {"filesystem", "git"}:
            return False

        if annotations is not None:
            if isinstance(annotations, dict) and annotations.get("readOnlyHint") is True:
                return False
            if getattr(annotations, "readOnlyHint", None) is True:
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
