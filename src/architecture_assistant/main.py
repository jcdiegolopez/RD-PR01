"""Entry point for the Phase 1 console chatbot."""

from architecture_assistant.config import Settings
from architecture_assistant.llm import GeminiProvider
from architecture_assistant.ui import console, show_error, show_help, show_welcome


def run() -> None:
    """Run the interactive console session until the user exits."""
    settings = Settings.load()
    show_welcome(settings.gemini_model, configured=bool(settings.gemini_api_key))

    if not settings.gemini_api_key:
        show_error(
            "Create a local .env file from .env.example and set GEMINI_API_KEY "
            "before starting a chat session."
        )
        return

    provider = GeminiProvider(settings.gemini_api_key, settings.gemini_model)

    while True:
        try:
            message = console.input("\n[bold green]You[/bold green] > ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Session closed.[/dim]")
            return

        if not message:
            continue
        if message == "/exit":
            console.print("[dim]Session closed.[/dim]")
            return
        if message == "/help":
            show_help()
            continue
        if message == "/clear":
            provider.reset_context()
            console.print("[dim]Conversation context cleared.[/dim]")
            continue
        if message.startswith("/"):
            show_error("Unknown command. Use /help to see the available commands.")
            continue

        try:
            with console.status("[cyan]Gemini is thinking...[/cyan]"):
                answer = provider.ask(message)
            console.print(Panel(answer, title="[bold cyan]Assistant[/bold cyan]", border_style="cyan"))
        except Exception as error:  # Provider/network errors must not terminate the chat loop.
            show_error(f"The Gemini request failed: {error}")


if __name__ == "__main__":
    run()
