"""Utilidades de presentación para terminal basadas en Rich."""

from rich.console import Console
from rich.panel import Panel


console = Console()


def show_welcome(model: str, configured: bool) -> None:
    """Muestra el encabezado inicial y los comandos disponibles."""
    status = "[green]listo[/green]" if configured else "[yellow]falta la clave de API[/yellow]"
    console.print(
        Panel.fit(
            "[bold cyan]Asistente de Arquitectura[/bold cyan]\n"
            "Proyecto de Redes - Anfitrión MCP (Fase 1)\n\n"
            f"Modelo Gemini: [bold]{model}[/bold]\n"
            f"Estado de conexión: {status}\n\n"
            "Comandos: [bold]/ayuda[/bold], [bold]/limpiar[/bold], [bold]/salir[/bold]",
            border_style="cyan",
        )
    )


def show_help() -> None:
    """Muestra los comandos disponibles antes de agregar herramientas MCP."""
    console.print(
        Panel(
            "[bold]/ayuda[/bold]    Muestra esta ayuda.\n"
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
