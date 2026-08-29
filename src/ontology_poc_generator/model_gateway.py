from __future__ import annotations

import json
from typing import Callable
from urllib.request import Request, urlopen

from ontology_poc_generator.recognition import ModelCompletion, RecognitionError


class OpenAICompatibleGateway:
    """Minimal JSON-mode adapter for an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60,
        opener: Callable[..., object] = urlopen,
    ) -> None:
        for field, value in (
            ("api_base", api_base),
            ("api_key", api_key),
            ("model", model),
        ):
            if not isinstance(value, str) or not value.strip():
                raise RecognitionError(f"{field} is required")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise RecognitionError("timeout_seconds must be positive")
        self._api_base = api_base.strip().rstrip("/")
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> ModelCompletion:
        body = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            f"{self._api_base}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            served_model = payload.get("model", self._model)
            if not isinstance(content, str) or not content.strip():
                raise TypeError("content")
            if not isinstance(served_model, str) or not served_model.strip():
                served_model = self._model
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RecognitionError(f"model request failed: {exc}") from exc
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise RecognitionError("invalid model response") from exc
        return ModelCompletion(
            provider="openai_compatible",
            model=served_model,
            content=content,
        )
