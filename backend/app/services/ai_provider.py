"""Optional OpenAI-compatible chat provider; credentials stay out of logs."""

from __future__ import annotations

import json
import logging
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.core.config import Settings

log = logging.getLogger("aven.ai")


class AIProvider(Protocol):
    def generate(self, text: str, language: str) -> str: ...


class ProviderError(RuntimeError):
    """A provider failure with a safe, user-facing message."""


class OpenAICompatibleProvider:
    def __init__(self, api_key: str, model: str, base_url: str, timeout: int) -> None:
        parsed = urlparse(base_url)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or (parsed.scheme != "https" and parsed.hostname not in local_hosts)
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("AI_BASE_URL must use HTTPS except for a local provider")
        self._api_key = api_key
        self._model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._timeout = timeout

    def generate(self, text: str, language: str) -> str:
        language_names = {"en": "English", "hi": "Hindi", "mr": "Marathi"}
        prompt = (
            "You are Aven, a concise desktop assistant. Answer the user's request in "
            f"{language_names.get(language, 'the language they used')}. Keep the answer brief. "
            "Never claim to have performed a computer action."
        )
        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            "max_tokens": 350,
            "stream": False,
        }).encode("utf-8")
        request = Request(
            self._url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            result = data["choices"][0]["message"]["content"]
            if not isinstance(result, str) or not result.strip():
                raise ProviderError("The AI provider returned an empty response.")
            return result.strip()
        except ProviderError:
            raise
        except HTTPError as exc:
            log.warning("AI provider returned HTTP status %s", exc.code)
            raise ProviderError("Online AI is unavailable right now.") from exc
        except (URLError, TimeoutError, OSError):
            log.warning("AI provider request failed or timed out")
            raise ProviderError("Online AI could not be reached. Please try again.") from None
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            log.warning("AI provider returned an invalid response")
            raise ProviderError("Online AI returned an unreadable response.") from None


def configured_provider(settings: Settings) -> AIProvider | None:
    if settings.ai_provider != "openai" or not settings.ai_api_key:
        return None
    return OpenAICompatibleProvider(
        settings.ai_api_key,
        settings.ai_model,
        settings.ai_base_url,
        settings.ai_timeout_seconds,
    )


def provider_status(settings: Settings) -> str:
    if not settings.ai_provider:
        return "Offline fallback (AI_PROVIDER is not configured)"
    if settings.ai_provider != "openai":
        return f"Unsupported provider: {settings.ai_provider}"
    if not settings.ai_api_key:
        return "Not configured (AI_API_KEY is missing)"
    return f"Configured ({settings.ai_provider}, {settings.ai_model})"