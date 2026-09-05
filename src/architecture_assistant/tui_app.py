"""Textual TUI para el Asistente de Arquitectura e Inspector de Protocolos MCP."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.syntax import Syntax
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    Static,
)

from architecture_assistant.config import Settings
from architecture_assistant.llm import GeminiProvider
from architecture_assistant.mcp_log import McpLogEntry
from architecture_assistant.mcp_manager import McpManager
from architecture_assistant.ui import make_clickable


class PacketDetailModal(ModalScreen):
    """Modal emergente para inspeccionar en detalle el paquete JSON-RPC seleccionado."""

    DEFAULT_CSS = """
    PacketDetailModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.8);
    }
    #modal-container {
        width: 85%;
        height: 85%;
        background: #0D1117;
        border: solid #58A6FF;
        padding: 1 2;
    }
    #modal-title {
        text-style: bold;
        color: #58A6FF;
        margin-bottom: 1;
        border-bottom: solid #30363D;
        padding-bottom: 1;
    }
    #modal-scroll {
        height: 1fr;
    }
    #modal-close-btn {
        margin-top: 1;
        dock: bottom;
        width: 100%;
    }
    .section-label {
        margin-top: 1;
        text-style: bold;
        color: #E6EDF3;
    }
    """

    def __init__(self, entry: McpLogEntry) -> None:
        super().__init__()
        self.entry = entry

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label(
                f"📡 Inspección de Trama JSON-RPC 2.0  ·  {self.entry.tool_name}",
                id="modal-title",
            )
            with VerticalScroll(id="modal-scroll"):
                info_text = (
                    f"**Hora:** `{self.entry.timestamp.strftime('%H:%M:%S.%f')[:-3]}`  |  "
                    f"**Servidor:** `{self.entry.server_name}`  |  "
                    f"**Herramienta:** `{self.entry.tool_name}`\n\n"
                    f"**Canal de Transporte:** `{self.entry.transport}`\n\n"
                    f"**Protocolo:** `{self.entry.protocol}`  |  "
                    f"**Estado:** `{self.entry.status_code}`  |  "
                    f"**Latencia RTT:** `{self.entry.latency_ms} ms`\n\n"
                    f"**Tamaño Paquete:** Petición ~{self.entry.request_size} B  |  "
                    f"Respuesta ~{self.entry.response_size} B\n\n"
                    f"---"
                )
                yield Markdown(info_text)

                req_obj = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": self.entry.tool_name,
                        "arguments": self.entry.arguments,
                    },
                    "id": 1,
                }
                yield Label("📦 Petición JSON-RPC enviada al canal (Request):", classes="section-label")
                yield Static(
                    Syntax(
                        json.dumps(req_obj, indent=2, ensure_ascii=False),
                        "json",
                        theme="monokai",
                    )
                )

                resp_obj = {
                    "jsonrpc": "2.0",
                    "result": self.entry.result,
                    "id": 1,
                }
                yield Label("📥 Respuesta JSON-RPC recibida del canal (Response):", classes="section-label")
                yield Static(
                    Syntax(
                        json.dumps(resp_obj, indent=2, ensure_ascii=False),
                        "json",
                        theme="monokai",
                    )
                )

            yield Button("Cerrar Detalle [Esc]", id="modal-close-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-close-btn":
            self.dismiss()

    def key_escape(self) -> None:
        self.dismiss()


class ConfirmationModal(ModalScreen[bool]):
    """Modal de confirmación para herramientas MCP de escritura (Filesystem / Git)."""

    DEFAULT_CSS = """
    ConfirmationModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.75);
    }
    #confirm-box {
        width: 60%;
        height: auto;
        background: #161B22;
        border: solid #D29922;
        padding: 1 2;
    }
    #confirm-title {
        color: #D29922;
        text-style: bold;
        margin-bottom: 1;
    }
    #confirm-buttons {
        margin-top: 1;
        height: auto;
    }
    #btn-yes {
        margin-right: 2;
    }
    """

    def __init__(self, tool_name: str, args: dict[str, Any]) -> None:
        super().__init__()
        self.tool_name = tool_name
        self.args = args

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label("⚠️ Confirmación Requerida", id="confirm-title")
            yield Label(
                f"La herramienta [bold]{self.tool_name}[/bold] puede modificar archivos.\n"
                f"Argumentos: {self.args}\n\n"
                "¿Autorizar la ejecución?"
            )
            with Horizontal(id="confirm-buttons"):
                yield Button("Sí, autorizar", id="btn-yes", variant="success")
                yield Button("No, cancelar", id="btn-no", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")


class ArchitectureInspectorApp(App):
    """Aplicación TUI de Terminal dividida con Chat y Protocol Inspector."""

    TITLE = "Asistente de Arquitectura · Protocol & Network Inspector"
    SUB_TITLE = "Redes (Fase 3) · Model Context Protocol (MCP) Multi-Transport Host"

    BINDINGS = [
        Binding("tab", "focus_next", "Cambiar Panel", show=True),
        Binding("ctrl+l", "clear_chat", "Limpiar Chat", show=True),
        Binding("ctrl+q", "quit", "Salir", show=True),
    ]

    CSS = """
    Screen {
        background: #0A0E17;
    }

    #main-layout {
        height: 1fr;
    }

    /* ── Panel Izquierdo: Chat ── */
    #chat-pane {
        width: 56%;
        border-right: solid #30363D;
        padding: 0 1;
        background: #0D1117;
    }

    #chat-header-bar {
        dock: top;
        padding: 1 0;
        border-bottom: solid #21262D;
        color: #58A6FF;
        text-style: bold;
    }

    #chat-scroll {
        height: 1fr;
        padding: 1 0;
    }

    .user-bubble {
        background: #1F3A24;
        border: solid #238636;
        padding: 1;
        margin: 1 0;
        color: #E6EDF3;
    }

    .assistant-bubble {
        background: #161B22;
        border: solid #1F6FEB;
        padding: 1;
        margin: 1 0;
        color: #E6EDF3;
    }

    .system-bubble {
        background: #1C1917;
        border: solid #D97706;
        padding: 0 1;
        margin: 0 0 1 0;
        color: #F59E0B;
    }

    #chat-input-bar {
        dock: bottom;
        height: auto;
        padding-top: 1;
        border-top: solid #21262D;
    }

    #user-input {
        width: 1fr;
        border: solid #30363D;
    }

    #user-input:focus {
        border: solid #58A6FF;
    }

    #send-btn {
        margin-left: 1;
    }

    /* ── Panel Derecho: Inspector de Red ── */
    #inspector-pane {
        width: 44%;
        padding: 0 1;
        background: #0A0E17;
    }

    #traffic-header {
        dock: top;
        padding: 1 0;
        border-bottom: solid #21262D;
        color: #2DD4BF;
        text-style: bold;
    }

    #traffic-table-container {
        height: 44%;
        border: solid #21262D;
        margin-top: 1;
        background: #0D1117;
    }

    #traffic-table {
        height: 100%;
    }

    #packet-pane {
        height: 54%;
        border: solid #21262D;
        margin-top: 1;
        padding: 1;
        background: #0D1117;
    }

    #packet-pane-title {
        dock: top;
        text-style: bold;
        color: #A78BFA;
        padding-bottom: 1;
        border-bottom: solid #21262D;
    }

    #packet-scroll {
        height: 1fr;
    }

    #inspect-full-btn {
        dock: bottom;
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        provider: GeminiProvider,
        mcp_manager: McpManager,
        settings: Settings,
    ) -> None:
        super().__init__()
        self.provider = provider
        self.mcp_manager = mcp_manager
        self.settings = settings
        self.entries: list[McpLogEntry] = []
        self.selected_entry: McpLogEntry | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="main-layout"):
            # Columna izquierda: Chat
            with Vertical(id="chat-pane"):
                yield Label("💬 Chat con Asistente de Arquitectura (Gemini)", id="chat-header-bar")
                with VerticalScroll(id="chat-scroll"):
                    yield Static(
                        "👋 ¡Bienvenido! Puedes pedir análisis de arquitectura, violaciones de capas, "
                        "o generar el grafo de dependencias.\n"
                        "Cada interacción de red se registra en vivo en el panel derecho.",
                        classes="assistant-bubble",
                    )
                with Horizontal(id="chat-input-bar"):
                    yield Input(
                        placeholder="Escribe tu consulta o comando (ej. 'Genera el grafo de dependencias')...",
                        id="user-input",
                    )
                    yield Button("Enviar", id="send-btn", variant="primary")

            # Columna derecha: Inspector de Red
            with Vertical(id="inspector-pane"):
                yield Label("🌐 Inspector de Protocolos & Tráfico de Red (JSON-RPC)", id="traffic-header")

                with Container(id="traffic-table-container"):
                    table = DataTable(id="traffic-table")
                    table.cursor_type = "row"
                    yield table

                with Vertical(id="packet-pane"):
                    yield Label("🔍 Detalle del Paquete Seleccionado", id="packet-pane-title")
                    with VerticalScroll(id="packet-scroll"):
                        yield Static(
                            "Haz clic o navega con las flechas en la tabla de arriba "
                            "para inspeccionar el paquete JSON-RPC 2.0 y su transporte.",
                            id="packet-detail-view",
                        )
                    yield Button("🔍 Ver Trama Completa [Enter]", id="inspect-full-btn", variant="default")

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#traffic-table", DataTable)
        table.add_columns("#", "Hora", "Canal", "Herramienta", "RTT", "Estado")

        tools_count = len(self.mcp_manager.tools)
        servers = set(t.server_name for t in self.mcp_manager.tools)
        welcome_note = (
            f"**Servidores MCP conectados:** `{', '.join(servers)}`\n\n"
            f"**Herramientas disponibles:** `{tools_count}` registradas.\n\n"
            f"- **Local IPC:** `architecture` (Stdio Pipes)\n"
            f"- **Remote Edge:** `github-profiler` (Cloudflare Workers HTTP/SSE)\n\n"
            f"*Navega con [Tab] al panel de tráfico y usa las flechas para inspeccionar tramas.*"
        )
        self.add_assistant_message(welcome_note)

    def add_user_message(self, text: str) -> None:
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        chat_scroll.mount(Static(f"**Tú:** {text}", classes="user-bubble"))
        chat_scroll.scroll_end(animate=False)

    def add_assistant_message(self, text: str) -> None:
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        chat_scroll.mount(Markdown(text, classes="assistant-bubble"))
        chat_scroll.scroll_end(animate=False)

    def add_system_event(self, text: str) -> None:
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        chat_scroll.mount(Static(text, classes="system-bubble"))
        chat_scroll.scroll_end(animate=False)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            await self.handle_submit()
        elif event.button.id == "inspect-full-btn":
            if self.selected_entry:
                self.app.push_screen(PacketDetailModal(self.selected_entry))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "user-input":
            await self.handle_submit()

    async def handle_submit(self) -> None:
        input_widget = self.query_one("#user-input", Input)
        message = input_widget.value.strip()
        if not message:
            return

        input_widget.value = ""
        self.add_user_message(message)

        if message in {"/salir", "/exit"}:
            self.exit()
            return
        if message in {"/limpiar", "/clear"}:
            self.action_clear_chat()
            return

        input_widget.disabled = True
        self.add_system_event("⏳ Consultando a Gemini...")

        asyncio.create_task(self.process_message_turn(message))

    async def process_message_turn(self, message: str) -> None:
        input_widget = self.query_one("#user-input", Input)
        try:
            loop = asyncio.get_running_loop()
            turn = await loop.run_in_executor(
                None,
                lambda: self.provider.start_turn(message, self.mcp_manager.gemini_tools()),
            )

            while turn.function_calls:
                function_results: list[dict[str, object]] = []
                for function_call in turn.function_calls:
                    tool = self.mcp_manager.get_tool(function_call.name)

                    if tool.requires_confirmation:
                        confirmed = await self.push_screen_wait(
                            ConfirmationModal(function_call.name, function_call.arguments)
                        )
                        if not confirmed:
                            result = self.mcp_manager.record_cancelled_call(
                                function_call.name, function_call.arguments
                            )
                            self.add_system_event(f"🚫 Operación cancelada: `{function_call.name}`")
                            continue

                    self.add_system_event(f"⚡ Ejecutando llamada MCP: `{function_call.name}`...")
                    result = await self.mcp_manager.call_tool(
                        function_call.name, function_call.arguments
                    )

                    latest_entry = self.mcp_manager.log.entries[-1]
                    self.record_network_event(latest_entry)

                    function_results.append(
                        {
                            "type": "function_result",
                            "name": function_call.name,
                            "call_id": function_call.call_id,
                            "result": [
                                {
                                    "type": "text",
                                    "text": json.dumps(result, ensure_ascii=False),
                                }
                            ],
                        }
                    )

                self.add_system_event("⏳ Gemini procesando respuesta final...")
                turn = await loop.run_in_executor(
                    None,
                    lambda: self.provider.submit_function_results(
                        turn.interaction_id,
                        function_results,
                        self.mcp_manager.gemini_tools(),
                    ),
                )

            answer = turn.text or "La interacción terminó sin respuesta."
            self.add_assistant_message(answer)

        except Exception as err:
            self.add_assistant_message(f"❌ **Error:** {err}")
        finally:
            input_widget.disabled = False
            input_widget.focus()

    def record_network_event(self, entry: McpLogEntry) -> None:
        self.entries.append(entry)
        table = self.query_one("#traffic-table", DataTable)

        row_idx = len(self.entries)
        time_str = entry.timestamp.strftime("%H:%M:%S")

        if "HTTP" in entry.transport:
            trans_styled = Text("HTTP/SSE", style="bold cyan")
        else:
            trans_styled = Text("STDIO", style="bold magenta")

        status_styled = Text("200 OK", style="bold green") if not entry.is_error else Text("ERR", style="bold red")
        latency_str = f"{entry.latency_ms} ms"

        table.add_row(
            str(row_idx),
            time_str,
            trans_styled,
            entry.tool_name,
            latency_str,
            status_styled,
        )

        table.move_cursor(row=len(self.entries) - 1)
        self.update_packet_detail(entry)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.cursor_row is not None and 0 <= event.cursor_row < len(self.entries):
            entry = self.entries[event.cursor_row]
            self.selected_entry = entry
            self.update_packet_detail(entry)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.cursor_row is not None and 0 <= event.cursor_row < len(self.entries):
            entry = self.entries[event.cursor_row]
            self.selected_entry = entry
            self.app.push_screen(PacketDetailModal(entry))

    def update_packet_detail(self, entry: McpLogEntry) -> None:
        detail_view = self.query_one("#packet-detail-view", Static)
        self.selected_entry = entry

        req_preview = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": entry.tool_name, "args": entry.arguments},
                "id": 1,
            },
            indent=2,
            ensure_ascii=False,
        )

        resp_preview = json.dumps(
            {
                "jsonrpc": "2.0",
                "result": entry.result,
                "id": 1,
            },
            indent=2,
            ensure_ascii=False,
        )
        if len(resp_preview) > 500:
            resp_preview = resp_preview[:500] + "\n... [truncado en vista previa]"

        info_header = (
            f"[bold cyan]Transporte:[/bold cyan] {entry.transport}\n"
            f"[bold magenta]Protocolo:[/bold magenta] {entry.protocol}  |  "
            f"[bold yellow]Latencia RTT:[/bold yellow] [bold]{entry.latency_ms} ms[/bold]\n"
            f"[bold green]Paquete:[/bold green] Req: {entry.request_size} B  |  Resp: {entry.response_size} B\n"
            f"[bold blue]Estado:[/bold blue] {entry.status_code}\n\n"
            f"[bold]Petición JSON-RPC:[/bold]\n{req_preview}\n\n"
            f"[bold]Respuesta JSON-RPC:[/bold]\n{resp_preview}"
        )
        detail_view.update(info_header)

    def action_clear_chat(self) -> None:
        chat_scroll = self.query_one("#chat-scroll", VerticalScroll)
        chat_scroll.remove_children()
        self.provider.reset_context()
        self.add_assistant_message("Se limpió el contexto de la conversación.")


async def run_tui() -> None:
    """Inicia la interfaz TUI con el inspector de protocolos MCP."""
    settings = Settings.load()

    if not settings.gemini_api_key:
        print("Error: GEMINI_API_KEY no encontrada en .env")
        return

    if not settings.mcp_config_path.exists():
        print(f"Error: No se encontró {settings.mcp_config_path}")
        return

    provider = GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    mcp_manager = McpManager()

    server_configs = McpManager.load_server_configs(settings.mcp_config_path)
    for server_name, server_config in server_configs.items():
        if server_name == "filesystem":
            settings.mcp_demo_workspace.mkdir(parents=True, exist_ok=True)
        try:
            await mcp_manager.connect_from_config(server_name, server_config)
        except Exception as e:
            print(f"Error conectando {server_name}: {e}")

    app = ArchitectureInspectorApp(provider, mcp_manager, settings)
    try:
        await app.run_async()
    finally:
        await mcp_manager.close()
