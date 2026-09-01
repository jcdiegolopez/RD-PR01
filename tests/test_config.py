"""Tests for safe local configuration handling."""

import os
import unittest
from unittest.mock import patch

from architecture_assistant.config import DEFAULT_MODEL, Settings


class SettingsTests(unittest.TestCase):
    def test_uses_default_model_when_no_model_is_configured(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.load()

        self.assertIsNone(settings.gemini_api_key)
        self.assertEqual(settings.gemini_model, DEFAULT_MODEL)

    def test_reads_configured_values(self) -> None:
        values = {
            "GEMINI_API_KEY": "test-key",
            "GEMINI_MODEL": "test-model",
        }
        with patch.dict(os.environ, values, clear=True):
            settings = Settings.load()

        self.assertEqual(settings.gemini_api_key, "test-key")
        self.assertEqual(settings.gemini_model, "test-model")
