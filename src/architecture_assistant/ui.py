"""Utilidades de presentación para terminal basadas en Rich."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from architecture_assistant.mcp_log import McpLogEntry
from architecture_assistant.mcp_manager import McpTool


console = Console()


def show_welcome(model: str, configured: bool, mcp_tool_count: int) -> None:
    """Muestra el encabezado inicial y los comandos disponibles."""
    status = "[green]listo[/green]" if configured else "[yellow]falta la clave de API[/yellow]"
    console.print(
        Panel.fit(
            "[bold cyan]Asistente de Arquitectura[/bold cyan]\n"
            "Proyecto de Redes - Anfitrión MCP (Fase 2)\n\n"
            f"Modelo Gemini: [bold]{model}[/bold]\n"
            f"Estado de conexión: {status}\n\n"
            f"Herramientas MCP disponibles: [bold]{mcp_tool_count}[/bold]\n\n"
            "Comandos: [bold]/ayuda[/bold], [bold]/herramientas[/bold], "
            "[bold]/registro[/bold], [bold]/limpiar[/bold], [bold]/salir[/bold]",
            border_style="cyan",
        )
    )


def show_help() -> None:
    """Muestra los comandos disponibles antes de agregar herramientas MCP."""
    console.print(
        Panel(
            "[bold]/ayuda[/bold]    Muestra esta ayuda.\n"
            "[bold]/herramientas[/bold] Muestra las herramientas MCP disponibles.\n"
            "[bold]/registro[/bold] Muestra las llamadas MCP de esta sesión.\n"
            "[bold]/limpiar[/bold]  Inicia una conversación nueva.\n"
            "[bold]/salir[/bold]    Cierra el chatbot.\n\n"
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
    for tool in tools:
        table.add_row(tool.server_name, tool.public_name, tool.description)
    console.print(table)


def show_mcp_call(entry: McpLogEntry) -> None:
    """Muestra una llamada MCP recién ejecutada."""
    state = "[red]error[/red]" if entry.is_error else "[green]correcta[/green]"
    console.print(
        Panel(
            f"Servidor: [bold]{entry.server_name}[/bold]\n"
            f"Herramienta: [bold]{entry.tool_name}[/bold]\n"
            f"Argumentos: {entry.arguments}\n"
            f"Resultado: {entry.result['text']}\n"
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
