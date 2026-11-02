"""Google Gemini adapter (google-genai SDK)."""

from collections.abc import AsyncIterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.errors import LLMError
from app.domain.chat import ChatMessage


class GeminiClient:
    def __init__(
        self, api_key: str, model: str, temperature: float, max_tokens: int, timeout_s: float
    ) -> None:
        self.model = model
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000))
        )
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _config(self, system: str) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._temperature,
            max_output_tokens=self._max_tokens,
        )

    @staticmethod
    def _contents(messages: list[ChatMessage]) -> list[types.Content]:
        # Gemini calls the assistant role "model".
        return [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in messages
        ]

    async def generate(self, system: str, messages: list[ChatMessage]) -> str:
        try:
            resp = await self._client.aio.models.generate_content(
                model=self.model, contents=self._contents(messages), config=self._config(system)
            )
        except genai_errors.APIError as exc:
            raise LLMError(f"Gemini request failed: {exc.message or exc}") from exc
        return resp.text or ""

    async def stream(self, system: str, messages: list[ChatMessage]) -> AsyncIterator[str]:
        try:
            chunks = await self._client.aio.models.generate_content_stream(
                model=self.model, contents=self._contents(messages), config=self._config(system)
            )
            async for chunk in chunks:
                if chunk.text:
                    yield chunk.text
        except genai_errors.APIError as exc:
            raise LLMError(f"Gemini request failed: {exc.message or exc}") from exc
