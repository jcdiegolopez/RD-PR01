"""Servidor MCP local de demostración para validar el flujo del anfitrión sin SDK."""

import json
import sys

SERVER_NAME = "Servidor de demostración"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"

TOOLS_METADATA = [
    {
        "name": "sumar",
        "title": "Sumar dos números",
        "description": "Suma dos números y devuelve la operación junto con el resultado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "Primer número"},
                "b": {"type": "number", "description": "Segundo número"},
            },
            "required": ["a", "b"],
        },
    }
]


def handle_request(msg: dict) -> dict | None:
    method = msg.get("method")
    req_id = msg.get("id")

    if req_id is None:
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "Expone operaciones matemáticas simples para probar una conexión MCP.",
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_METADATA}}

    if method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "sumar":
            a = float(args.get("a", 0))
            b = float(args.get("b", 0))
            res = {
                "operacion": f"{a} + {b}",
                "resultado": a + b,
            }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(res, indent=2, ensure_ascii=False),
                        }
                    ],
                    "structuredContent": res,
                    "isError": False,
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Tool '{tool_name}' not found."},
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method '{method}' not found."},
    }


def main():
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        resp = handle_request(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
