"""Gemini adapter used by the console host.

Keeping the provider behind this small class will let us add NVIDIA NIM as a
fallback later without changing the terminal UI or MCP orchestration logic.
"""

from google import genai


class GeminiProvider:
    """A stateful Gemini chat session that preserves conversation context."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._chat = self._client.chats.create(model=model)
        self.model = model

    def ask(self, message: str) -> str:
        """Send one user message and return Gemini's text response."""
        response = self._chat.send_message(message)
        return response.text or "The model returned an empty response."

    def reset_context(self) -> None:
        """Start a fresh session while keeping the configured model."""
        self._chat = self._client.chats.create(model=self.model)
