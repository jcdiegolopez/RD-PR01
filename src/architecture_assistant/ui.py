"""Rich-based terminal presentation helpers."""

from rich.console import Console
from rich.panel import Panel


console = Console()


def show_welcome(model: str, configured: bool) -> None:
    """Render the initial terminal banner and the available local commands."""
    status = "[green]ready[/green]" if configured else "[yellow]API key missing[/yellow]"
    console.print(
        Panel.fit(
            "[bold cyan]Architecture Assistant[/bold cyan]\n"
            "Networks Project - MCP Host (Phase 1)\n\n"
            f"Gemini model: [bold]{model}[/bold]\n"
            f"Connection status: {status}\n\n"
            "Commands: [bold]/help[/bold], [bold]/clear[/bold], [bold]/exit[/bold]",
            border_style="cyan",
        )
    )


def show_help() -> None:
    """Display commands available before MCP tools are added."""
    console.print(
        Panel(
            "[bold]/help[/bold]  Show this help.\n"
            "[bold]/clear[/bold] Start a new conversation.\n"
            "[bold]/exit[/bold]  Close the chatbot.\n\n"
            "Write any other message to send it to Gemini.",
            title="Help",
            border_style="blue",
        )
    )


def show_error(message: str) -> None:
    """Render a concise, user-safe error message."""
    console.print(Panel(message, title="[red]Error[/red]", border_style="red"))
