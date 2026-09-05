"""Pruebas de integración entre el anfitrión y el servidor MCP de demostración."""

import unittest

from architecture_assistant.mcp_manager import McpManager


class McpManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovers_and_calls_demo_tool(self) -> None:
        manager = McpManager()
        try:
            tools = await manager.connect_demo_server()
            self.assertEqual(tools[0].public_name, "demostracion__sumar")
            self.assertEqual(tools[0].server_name, "demostracion")
            self.assertFalse(tools[0].requires_confirmation)

            result = await manager.call_tool(
                "demostracion__sumar", {"a": 4, "b": 8}
            )

            self.assertFalse(result["is_error"])
            self.assertEqual(result["structured_content"]["resultado"], 12.0)
            self.assertEqual(len(manager.log.entries), 1)
        finally:
            await manager.close()

    def test_requires_confirmation_for_unsafe_servers_and_tools(self) -> None:
        self.assertFalse(
            McpManager._requires_confirmation("filesystem", "read_text_file", None)
        )
        self.assertTrue(
            McpManager._requires_confirmation("filesystem", "write_file", None)
        )
        self.assertFalse(McpManager._requires_confirmation("git", "git_status", None))
        self.assertTrue(McpManager._requires_confirmation("git", "git_commit", None))

    async def test_exports_mcp_schema_for_gemini(self) -> None:
        manager = McpManager()
        try:
            await manager.connect_demo_server()
            tool = manager.gemini_tools()[0]

            self.assertEqual(tool["type"], "function")
            self.assertEqual(tool["name"], "demostracion__sumar")
            self.assertIn("properties", tool["parameters"])
        finally:
            await manager.close()
