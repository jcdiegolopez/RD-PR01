"""Punto de entrada del chatbot de consola de la Fase 1."""

import asyncio
import json

from architecture_assistant.config import Settings
from architecture_assistant.llm import GeminiProvider, ProviderUnavailableError
from architecture_assistant.mcp_manager import McpManager
from architecture_assistant.ui import (
    console,
    show_error,
    show_help,
    show_mcp_call,
    show_mcp_log,
    show_tools,
    show_welcome,
)
from rich.panel import Panel


def run() -> None:
    """Inicia el ciclo asíncrono de la sesión interactiva."""
    asyncio.run(run_async())


async def run_async() -> None:
    """Ejecuta la sesión del chatbot y mantiene las conexiones MCP activas."""
    settings = Settings.load()

    if not settings.gemini_api_key:
        show_welcome(settings.gemini_model, configured=False, mcp_tool_count=0)
        show_error(
            "Crea un archivo .env desde .env.example y configura GEMINI_API_KEY "
            "antes de iniciar una sesión de chat."
        )
        return

    provider = GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    mcp_manager = McpManager()

    try:
        await mcp_manager.connect_demo_server()
        show_welcome(
            settings.gemini_model,
            configured=True,
            mcp_tool_count=len(mcp_manager.tools),
        )
        await chat_loop(provider, mcp_manager)
    except Exception as error:
        show_error(f"No fue posible iniciar el servidor MCP de demostración: {error}")
    finally:
        await mcp_manager.close()


async def chat_loop(provider: GeminiProvider, mcp_manager: McpManager) -> None:
    """Procesa mensajes, herramientas MCP y comandos de la consola."""

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
        if message in {"/herramientas", "/tools"}:
            show_tools(mcp_manager.tools)
            continue
        if message in {"/registro", "/log"}:
            show_mcp_log(mcp_manager.log.entries)
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
                turn = provider.start_turn(message, mcp_manager.gemini_tools())

            while turn.function_calls:
                function_results: list[dict[str, object]] = []
                for function_call in turn.function_calls:
                    result = await mcp_manager.call_tool(
                        function_call.name, function_call.arguments
                    )
                    show_mcp_call(mcp_manager.log.entries[-1])
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

                with console.status("[cyan]Gemini está procesando el resultado MCP...[/cyan]"):
                    turn = provider.submit_function_results(
                        turn.interaction_id,
                        function_results,
                        mcp_manager.gemini_tools(),
                    )

            answer = turn.text or "La interacción terminó sin una respuesta textual."
            console.print(Panel(answer, title="[bold cyan]Asistente[/bold cyan]", border_style="cyan"))
        except ProviderUnavailableError as error:
            show_error(str(error))
        except Exception as error:  # Los errores de red no deben cerrar el chat.
            show_error(f"Falló la solicitud a Gemini: {error}")


if __name__ == "__main__":
    run()
