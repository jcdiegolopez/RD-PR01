from pathlib import Path
import re
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from architecture_assistant.mcp_log import McpLogEntry
from architecture_assistant.mcp_manager import McpTool


console = Console()


def make_clickable(text: str) -> str:
    """Convierte URLs y rutas de archivos de Windows en enlaces clicables con Ctrl+Clic."""
    # 1. URLs web
    text = re.sub(
        r'(https?://[^\s)\]\'",]+)',
        r'[link=\1][underline cyan]\1[/underline cyan][/link]',
        text,
    )

    # 2. Rutas locales de Windows
    def _replace_path(match: re.Match) -> str:
        raw_path = match.group(0)
        try:
            norm_path = raw_path.replace('\\\\', '\\')
            p = Path(norm_path)
            uri = p.resolve().as_uri()
            return f"[link={uri}][bold underline cyan]{raw_path}[/bold underline cyan][/link]"
        except Exception:
            return raw_path

    text = re.sub(
        r'[A-Za-z]:(?:\\\\|\\)[^\\/:*?"<>|\r\n\t]+(?:(?:\\\\|\\)[^\\/:*?"<>|\r\n\t]+)*',
        _replace_path,
        text,
    )
    return text


def ask_for_confirmation(question: str) -> bool:
    """Solicita una respuesta breve en español y acepta sí o no."""
    answer = console.input(f"[bold yellow]{question} [s/N][/bold yellow] ").strip().lower()
    return answer in {"s", "si", "sí", "y", "yes"}


def show_welcome(
    model: str, configured: bool, mcp_tool_count: int, workspace: str | None = None
) -> None:
    """Muestra el encabezado inicial y los comandos disponibles."""
    status = "[green]listo[/green]" if configured else "[yellow]falta la clave de API[/yellow]"
    workspace_line = f"Espacio aislado: [dim]{workspace}[/dim]\n\n" if workspace else ""
    console.print(
        Panel.fit(
            "[bold cyan]Asistente de Arquitectura[/bold cyan]\n"
            "Proyecto de Redes - Anfitrión MCP (Fase 3)\n\n"
            f"Modelo Gemini: [bold]{model}[/bold]\n"
            f"Estado de conexión: {status}\n\n"
            f"Herramientas MCP disponibles: [bold]{mcp_tool_count}[/bold]\n\n"
            f"{workspace_line}"
            "Comandos: [bold]/ayuda[/bold], [bold]/herramientas[/bold], "
            "[bold]/registro[/bold], [bold]/limpiar[/bold], [bold]/salir[/bold]",
            border_style="cyan",
        )
    )


def show_help() -> None:
    """Muestra los comandos disponibles durante la sesión."""
    console.print(
        Panel(
            "[bold]/ayuda[/bold]        Muestra esta ayuda.\n"
            "[bold]/herramientas[/bold] Muestra las herramientas MCP disponibles.\n"
            "[bold]/registro[/bold]     Muestra las llamadas MCP de esta sesión.\n"
            "[bold]/limpiar[/bold]      Inicia una conversación nueva.\n"
            "[bold]/salir[/bold]        Cierra el chatbot.\n\n"
            "Las operaciones que puedan escribir archivos o cambiar Git pedirán confirmación. "
            "Escribe cualquier otro mensaje para enviarlo a Gemini.",
            title="Ayuda",
            border_style="blue",
        )
    )


def show_error(message: str) -> None:
    """Muestra un mensaje de error breve y seguro para el usuario."""
    console.print(Panel(message, title="[red]Error[/red]", border_style="red"))


def show_tools(tools: tuple[McpTool, ...]) -> None:
    """Muestra las herramientas MCP descubiertas en una tabla."""
    table = Table(title="Herramientas MCP disponibles", border_style="blue")
    table.add_column("Servidor", style="cyan")
    table.add_column("Herramienta", style="green")
    table.add_column("Descripción")
    table.add_column("Confirmación")
    for tool in tools:
        confirmation = "Sí" if tool.requires_confirmation else "No"
        table.add_row(tool.server_name, tool.public_name, tool.description, confirmation)
    console.print(table)


def confirm_mcp_call(tool: McpTool, arguments: dict[str, Any]) -> bool:
    """Pide autorización antes de ejecutar una operación que puede modificar datos."""
    console.print(
        Panel(
            f"Servidor: [bold]{tool.server_name}[/bold]\n"
            f"Herramienta: [bold]{tool.server_tool_name}[/bold]\n"
            f"Argumentos: {arguments}\n\n"
            "Esta operación puede modificar archivos o el repositorio de demostración.",
            title="Confirmación requerida",
            border_style="yellow",
        )
    )
    return ask_for_confirmation("¿Autorizar esta operación?")


def confirm_demo_repository_initialization(workspace: str) -> bool:
    """Solicita permiso para crear el repositorio Git aislado la primera vez."""
    console.print(
        Panel(
            f"Se necesita inicializar un repositorio Git vacío en:\n[dim]{workspace}[/dim]\n\n"
            "Este directorio está separado del proyecto y se usa únicamente para la demostración.",
            title="Preparación inicial",
            border_style="yellow",
        )
    )
    return ask_for_confirmation("¿Inicializar este repositorio de demostración?")


def show_mcp_call(entry: McpLogEntry) -> None:
    """Muestra una llamada MCP recién ejecutada."""
    state = "[red]error[/red]" if entry.is_error else "[green]correcta[/green]"
    raw_text = entry.result.get("text", "")
    if len(raw_text) > 600:
        display_text = raw_text[:600] + f"\n... [salida truncada para la consola, {len(raw_text)} caracteres en total]"
    else:
        display_text = raw_text

    clickable_text = make_clickable(display_text)
    console.print(
        Panel(
            f"Servidor: [bold]{entry.server_name}[/bold]\n"
            f"Herramienta: [bold]{entry.tool_name}[/bold]\n"
            f"Argumentos: {entry.arguments}\n"
            f"Resultado: {clickable_text}\n"
            f"Estado: {state}",
            title="Llamada MCP",
            border_style="magenta",
        )
    )




def show_mcp_log(entries: tuple[McpLogEntry, ...]) -> None:
    """Muestra todas las llamadas MCP registradas en la sesión."""
    if not entries:
        console.print("[dim]Aún no hay llamadas MCP registradas.[/dim]")
        return

    table = Table(title="Registro MCP", border_style="magenta")
    table.add_column("Hora")
    table.add_column("Servidor")
    table.add_column("Herramienta")
    table.add_column("Estado")
    for entry in entries:
        state = "Error" if entry.is_error else "Correcta"
        table.add_row(
            entry.timestamp.strftime("%H:%M:%S"),
            entry.server_name,
            entry.tool_name,
            state,
        )
    console.print(table)
