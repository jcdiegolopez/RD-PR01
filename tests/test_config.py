"""Pruebas para el manejo seguro de la configuración local."""

import os
import unittest
from unittest.mock import MagicMock, patch

from architecture_assistant.config import DEFAULT_MODEL, Settings
from architecture_assistant.llm import GeminiProvider, ProviderUnavailableError
from google.genai import errors


class SettingsTests(unittest.TestCase):
    @patch("architecture_assistant.config.load_dotenv")
    def test_uses_default_model_when_no_model_is_configured(self, _: MagicMock) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.load()

        self.assertIsNone(settings.gemini_api_key)
        self.assertEqual(settings.gemini_model, DEFAULT_MODEL)
        self.assertEqual(settings.mcp_demo_workspace.name, "mcp-demo-workspace")

    @patch("architecture_assistant.config.load_dotenv")
    def test_reads_configured_values(self, _: MagicMock) -> None:
        values = {
            "GEMINI_API_KEY": "test-key",
            "GEMINI_MODEL": "test-model",
        }
        with patch.dict(os.environ, values, clear=True):
            settings = Settings.load()

        self.assertEqual(settings.gemini_api_key, "test-key")
        self.assertEqual(settings.gemini_model, "test-model")

    @patch("architecture_assistant.config.load_dotenv")
    def test_resolves_custom_workspace(self, _: MagicMock) -> None:
        with patch.dict(os.environ, {"MCP_DEMO_WORKSPACE": "demo"}, clear=True):
            settings = Settings.load()

        self.assertEqual(settings.mcp_demo_workspace.name, "demo")

    @patch("architecture_assistant.config.load_dotenv")
    def test_replaces_legacy_model_with_current_default(self, _: MagicMock) -> None:
        values = {"GEMINI_MODEL": "gemini-2.5-flash"}
        with patch.dict(os.environ, values, clear=True):
            settings = Settings.load()

        self.assertEqual(settings.gemini_model, DEFAULT_MODEL)


class GeminiProviderTests(unittest.TestCase):
    @patch("architecture_assistant.llm.genai.Client")
    def test_preserves_previous_interaction_id_between_messages(self, client_factory: MagicMock) -> None:
        client = client_factory.return_value
        first = MagicMock(id="interaction-1", output_text="First response")
        second = MagicMock(id="interaction-2", output_text="Second response")
        client.interactions.create.side_effect = [first, second]
        provider = GeminiProvider("test-key", "gemini-3.7-flash")

        self.assertEqual(provider.ask("first"), "First response")
        self.assertEqual(provider.ask("second"), "Second response")

        self.assertEqual(
            client.interactions.create.call_args_list[0].kwargs,
            {"model": "gemini-3.7-flash", "input": "first"},
        )
        self.assertEqual(
            client.interactions.create.call_args_list[1].kwargs,
            {
                "model": "gemini-3.7-flash",
                "input": "second",
                "previous_interaction_id": "interaction-1",
            },
        )

    @patch("architecture_assistant.llm.genai.Client")
    def test_reset_removes_conversation_context(self, client_factory: MagicMock) -> None:
        client = client_factory.return_value
        client.interactions.create.return_value = MagicMock(id="interaction-1", output_text="Response")
        provider = GeminiProvider("test-key", "gemini-3.7-flash")

        provider.ask("first")
        provider.reset_context()
        provider.ask("second")

        self.assertNotIn(
            "previous_interaction_id",
            client.interactions.create.call_args_list[1].kwargs,
        )

    @patch("architecture_assistant.llm.time.sleep")
    @patch("architecture_assistant.llm.genai.Client")
    def test_retries_temporary_server_errors(
        self, client_factory: MagicMock, sleep: MagicMock
    ) -> None:
        client = client_factory.return_value
        temporary_error = errors.ServerError(503, {"error": {"status": "UNAVAILABLE"}})
        client.interactions.create.side_effect = [
            temporary_error,
            MagicMock(id="interaction-1", output_text="Recovered"),
        ]
        provider = GeminiProvider("test-key", "gemini-3.5-flash-lite")

        self.assertEqual(provider.ask("hello"), "Recovered")
        sleep.assert_called_once_with(1)

    @patch("architecture_assistant.llm.time.sleep")
    @patch("architecture_assistant.llm.genai.Client")
    def test_reports_unavailability_after_retry_limit(
        self, client_factory: MagicMock, _: MagicMock
    ) -> None:
        client = client_factory.return_value
        client.interactions.create.side_effect = errors.ServerError(
            503, {"error": {"status": "UNAVAILABLE"}}
        )
        provider = GeminiProvider("test-key", "gemini-3.5-flash-lite")

        with self.assertRaises(ProviderUnavailableError):
            provider.ask("hello")
