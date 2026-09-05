"""Servidor MCP local de demostración para validar el flujo del anfitrión."""

from mcp.server.fastmcp import FastMCP


mcp = FastMCP(
    "Servidor de demostración",
    instructions="Expone operaciones matemáticas simples para probar una conexión MCP.",
)


@mcp.tool(title="Sumar dos números")
def sumar(a: float, b: float) -> dict[str, float | str]:
    """Suma dos números y devuelve la operación junto con el resultado."""
    return {
        "operacion": f"{a} + {b}",
        "resultado": a + b,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
