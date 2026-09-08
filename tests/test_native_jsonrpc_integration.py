"""Pruebas de integración para la arquitectura MCP con JSON-RPC 2.0 nativo sin SDK."""

import json
from pathlib import Path
import re
import sys
import unittest

from architecture_assistant.mcp_manager import McpManager, McpTool


class NativeJsonRpcIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Pruebas exhaustivas de integración del protocolo MCP implementado de forma nativa."""

    def test_zero_mcp_sdk_imports_in_codebase(self) -> None:
        """Verifica que ni el anfitrión ni el servidor de arquitectura importen el SDK de MCP."""
        # 1. Verificar mcp_manager.py
        mcp_manager_path = Path(__file__).parent.parent / "src" / "architecture_assistant" / "mcp_manager.py"
        content_manager = mcp_manager_path.read_text(encoding="utf-8")
        self.assertNotRegex(content_manager, r"^\s*(from|import)\s+mcp(\.|\s)", "mcp_manager.py no debe importar el SDK mcp")

        # 2. Verificar demo_server.py
        demo_server_path = Path(__file__).parent.parent / "src" / "architecture_assistant" / "demo_server.py"
        content_demo = demo_server_path.read_text(encoding="utf-8")
        self.assertNotRegex(content_demo, r"^\s*(from|import)\s+mcp(\.|\s)", "demo_server.py no debe importar el SDK mcp")

        # 3. Verificar spring-architecture-analyzer-mcp/server.py
        analyzer_server_path = Path(__file__).parent.parent.parent / "spring-architecture-analyzer-mcp" / "server.py"
        if analyzer_server_path.exists():
            content_analyzer = analyzer_server_path.read_text(encoding="utf-8")
            self.assertNotRegex(content_analyzer, r"^\s*(from|import)\s+mcp(\.|\s)", "server.py del analizador no debe importar el SDK mcp")

        # 4. Verificar que las clases del cliente nativo estén disponibles
        self.assertTrue(hasattr(McpManager, "connect_stdio"))
        self.assertTrue(hasattr(McpManager, "connect_http"))

    async def test_demo_server_native_jsonrpc(self) -> None:
        """Verifica handshake, tools/list, tools/call y telemetría de red en servidor de demostración."""
        manager = McpManager()
        try:
            tools = await manager.connect_demo_server()
            self.assertEqual(len(tools), 1)
            tool = tools[0]
            self.assertEqual(tool.public_name, "demostracion__sumar")
            self.assertEqual(tool.server_name, "demostracion")
            self.assertFalse(tool.requires_confirmation)

            # Ejecución de llamada RPC
            result = await manager.call_tool("demostracion__sumar", {"a": 25.5, "b": 16.5})
            self.assertFalse(result["is_error"])
            self.assertIsNotNone(result["structured_content"])
            self.assertEqual(result["structured_content"]["resultado"], 42.0)
            self.assertIn("42.0", result["text"])

            # Verificación de telemetría de red registrada
            self.assertEqual(len(manager.log.entries), 1)
            entry = manager.log.entries[0]
            self.assertEqual(entry.server_name, "demostracion")
            self.assertEqual(entry.tool_name, "sumar")
            self.assertIn("Stdio", entry.transport)
            self.assertIn("JSON-RPC 2.0", entry.protocol)
            self.assertEqual(entry.status_code, "200 OK")
            self.assertGreater(entry.latency_ms, 0)
            self.assertGreater(entry.request_size, 0)
            self.assertGreater(entry.response_size, 0)
        finally:
            await manager.close()

    async def test_spring_architecture_analyzer_native_jsonrpc(self) -> None:
        """Verifica la integración completa con el servidor local de análisis Spring Boot."""
        config_path = Path(__file__).parent.parent / "mcp_servers.json"
        configs = McpManager.load_server_configs(config_path)
        arch_config = configs.get("architecture")
        if not arch_config:
            self.skipTest("Configuración de 'architecture' no encontrada en mcp_servers.json")

        manager = McpManager()
        try:
            tools = await manager.connect_from_config("architecture", arch_config)
            tool_names = [t.server_tool_name for t in tools]
            expected_tools = [
                "index_repository",
                "get_architecture_overview",
                "get_change_impact",
                "find_dependency_cycles",
                "validate_architecture_rules",
                "rank_refactoring_targets",
                "generate_dependency_graph",
            ]
            for exp in expected_tools:
                self.assertIn(exp, tool_names, f"Herramienta esperada '{exp}' no encontrada en el servidor de arquitectura")

            # 1. Llamar herramienta antes de indexar para validar manejo de respuestas de estado
            res_cycles = await manager.call_tool("architecture__find_dependency_cycles", {})
            self.assertIn("No repository has been indexed yet", res_cycles["text"])

            # 2. Si existe el repo de prueba C:\temp\spring-petclinic, indexarlo y analizarlo
            test_repo = Path("C:/temp/spring-petclinic")
            if test_repo.is_dir():
                idx_res = await manager.call_tool("architecture__index_repository", {"repo_path": str(test_repo)})
                self.assertFalse(idx_res["is_error"])
                self.assertIn("indexed_repo", idx_res["text"])

                overview = await manager.call_tool("architecture__get_architecture_overview", {})
                self.assertFalse(overview["is_error"])
                self.assertIn("classes", overview["text"])

                ranked = await manager.call_tool("architecture__rank_refactoring_targets", {"top_n": 3})
                self.assertFalse(ranked["is_error"])

            # 3. Comprobar que todas las interacciones generaron telemetría de red correcta
            self.assertGreaterEqual(len(manager.log.entries), 1)
            for entry in manager.log.entries:
                self.assertEqual(entry.server_name, "architecture")
                self.assertIn("Stdio", entry.transport)
                self.assertEqual(entry.status_code, "200 OK")
        finally:
            await manager.close()

    async def test_github_profiler_native_http_jsonrpc(self) -> None:
        """Verifica la integración con el servidor remoto Cloudflare Worker sobre JSON-RPC HTTP POST."""
        config_path = Path(__file__).parent.parent / "mcp_servers.json"
        configs = McpManager.load_server_configs(config_path)
        profiler_config = configs.get("github-profiler")
        if not profiler_config:
            self.skipTest("Configuración de 'github-profiler' no encontrada en mcp_servers.json")

        manager = McpManager()
        try:
            tools = await manager.connect_from_config("github-profiler", profiler_config)
            self.assertEqual(len(tools), 1)
            self.assertEqual(tools[0].public_name, "github-profiler__profile_github_repository")

            # Llamar la herramienta remota sobre HTTP POST
            result = await manager.call_tool(
                "github-profiler__profile_github_repository",
                {"repo_url": "https://github.com/spring-projects/spring-petclinic"},
            )
            self.assertFalse(result["is_error"])
            self.assertIn("spring-petclinic", result["text"])
            if result["structured_content"]:
                self.assertTrue(result["structured_content"].get("is_suitable_for_local_analysis"))

            # Verificación de métricas de red HTTP
            entry = manager.log.entries[-1]
            self.assertEqual(entry.server_name, "github-profiler")
            self.assertIn("HTTP", entry.transport)
            self.assertIn("HTTPS", entry.protocol)
            self.assertEqual(entry.status_code, "200 OK")
            self.assertGreater(entry.latency_ms, 0)
        finally:
            await manager.close()

    async def test_peer_servers_cross_compatibility(self) -> None:
        """Verifica que el cliente nativo se comunique limpiamente con servidores en Go (brewops) y Python (hotel)."""
        config_path = Path(__file__).parent.parent / "mcp_servers.json"
        configs = McpManager.load_server_configs(config_path)

        manager = McpManager()
        try:
            # 1. Probar servidor Go: brewops
            brew_cfg = configs.get("brewops")
            if brew_cfg and Path(brew_cfg["command"]).exists():
                b_tools = await manager.connect_from_config("brewops", brew_cfg)
                self.assertGreater(len(b_tools), 0)
                b_res = await manager.call_tool("brewops__list_coffees", {})
                self.assertFalse(b_res["is_error"])

            # 2. Probar servidor Python: hotel
            hotel_cfg = configs.get("hotel")
            if hotel_cfg:
                h_tools = await manager.connect_from_config("hotel", hotel_cfg)
                self.assertGreater(len(h_tools), 0)
                h_res = await manager.call_tool("hotel__consultar_disponibilidad", {"fecha": "2026-10-01"})
                self.assertFalse(h_res["is_error"])
        finally:
            await manager.close()

    def test_record_cancelled_call_and_security(self) -> None:
        """Verifica el rechazo explícito y políticas de confirmación para herramientas sensibles."""
        manager = McpManager()
        mock_tool = McpTool(
            public_name="filesystem__write_file",
            server_name="filesystem",
            server_tool_name="write_file",
            description="Escribe un archivo",
            input_schema={"type": "object"},
            requires_confirmation=True,
        )
        manager._tools["filesystem__write_file"] = mock_tool

        cancelled = manager.record_cancelled_call("filesystem__write_file", {"path": "test.txt"})
        self.assertTrue(cancelled["is_error"])
        self.assertIn("cancelada", cancelled["text"])
        self.assertEqual(len(manager.log.entries), 1)
        self.assertTrue(manager.log.entries[0].is_error)
