from app.core.config import Settings
from app.core.errors import LLMError
from app.llm.base import LLMClient


def create_llm_client(settings: Settings) -> LLMClient:
    model = settings.resolved_llm_model
    match settings.llm_provider:
        case "gemini":
            if not settings.gemini_api_key:
                raise LLMError(
                    "GEMINI_API_KEY is not set (or use LLM_PROVIDER=fake for offline mode)"
                )
            from app.llm.gemini import GeminiClient

            return GeminiClient(
                api_key=settings.gemini_api_key.get_secret_value(),
                model=model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                timeout_s=settings.llm_timeout_seconds,
            )
        case "anthropic":
            if not settings.anthropic_api_key:
                raise LLMError(
                    "ANTHROPIC_API_KEY is not set (or use LLM_PROVIDER=fake for offline mode)"
                )
            from app.llm.anthropic import AnthropicClient

            return AnthropicClient(
                api_key=settings.anthropic_api_key.get_secret_value(),
                model=model,
                max_tokens=settings.llm_max_tokens,
                timeout_s=settings.llm_timeout_seconds,
            )
        case "fake":
            from app.llm.fake import FakeLLMClient

            return FakeLLMClient()
