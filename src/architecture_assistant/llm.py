"""Gemini adapter used by the console host.

Keeping the provider behind this small class will let us add NVIDIA NIM as a
fallback later without changing the terminal UI or MCP orchestration logic.
"""

from google import genai
from google.genai import errors
import time


MAX_SERVER_RETRIES = 2


class ProviderUnavailableError(RuntimeError):
    """Raised after temporary provider failures have been retried."""


class GeminiProvider:
    """A stateful Gemini Interactions API session."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self._previous_interaction_id: str | None = None

    def ask(self, message: str) -> str:
        """Send one user message and return Gemini's text response."""
        request: dict[str, str] = {"model": self.model, "input": message}
        if self._previous_interaction_id:
            request["previous_interaction_id"] = self._previous_interaction_id

        interaction = self._request_with_retry(request)
        self._previous_interaction_id = interaction.id
        return interaction.output_text or "The model returned an empty response."

    def reset_context(self) -> None:
        """Start a fresh session while keeping the configured model."""
        self._previous_interaction_id = None

    def _request_with_retry(self, request: dict[str, str]):
        """Retry short-lived 5xx provider errors with a small backoff."""
        for attempt in range(MAX_SERVER_RETRIES + 1):
            try:
                return self._client.interactions.create(**request)
            except errors.ServerError as error:
                if attempt == MAX_SERVER_RETRIES:
                    raise ProviderUnavailableError(
                        "Gemini is temporarily unavailable after several attempts. "
                        "Please try again in a moment."
                    ) from error
                time.sleep(2**attempt)

        raise AssertionError("Retry loop should always return or raise.")
