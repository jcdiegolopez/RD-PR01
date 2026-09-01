"""Punto de entrada del chatbot de consola de la Fase 1."""

from architecture_assistant.config import Settings
from architecture_assistant.llm import GeminiProvider, ProviderUnavailableError
from architecture_assistant.ui import console, show_error, show_help, show_welcome
from rich.panel import Panel


def run() -> None:
    """Ejecuta la sesión interactiva hasta que el usuario salga."""
    settings = Settings.load()
    show_welcome(settings.gemini_model, configured=bool(settings.gemini_api_key))

    if not settings.gemini_api_key:
        show_error(
            "Crea un archivo .env desde .env.example y configura GEMINI_API_KEY "
            "antes de iniciar una sesión de chat."
        )
        return

    provider = GeminiProvider(settings.gemini_api_key, settings.gemini_model)

    while True:
        try:
            message = console.input("\n[bold green]Tú[/bold green] > ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Sesión cerrada.[/dim]")
            return

        if not message:
            continue
        if message in {"/salir", "/exit"}:
            console.print("[dim]Sesión cerrada.[/dim]")
            return
        if message in {"/ayuda", "/help"}:
            show_help()
            continue
        if message in {"/limpiar", "/clear"}:
            provider.reset_context()
            console.print("[dim]Se limpió el contexto de la conversación.[/dim]")
            continue
        if message.startswith("/"):
            show_error("Comando desconocido. Usa /ayuda para ver los comandos disponibles.")
            continue

        try:
            with console.status("[cyan]Gemini está pensando...[/cyan]"):
                answer = provider.ask(message)
            console.print(Panel(answer, title="[bold cyan]Asistente[/bold cyan]", border_style="cyan"))
        except ProviderUnavailableError as error:
            show_error(str(error))
        except Exception as error:  # Los errores de red no deben cerrar el chat.
            show_error(f"Falló la solicitud a Gemini: {error}")


if __name__ == "__main__":
    run()
