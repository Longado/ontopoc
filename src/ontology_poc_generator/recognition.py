"""Model gateway contract shared by every model call: one JSON completion in, one JSON completion out."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RecognitionError(ValueError):
    """A model response cannot enter the deterministic boundary."""


@dataclass(frozen=True)
class ModelCompletion:
    provider: str
    model: str
    content: str

    def __post_init__(self) -> None:
        for field in ("provider", "model", "content"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise RecognitionError(f"model completion {field} is required")
            object.__setattr__(self, field, value.strip())


class RecognitionGateway(Protocol):
    def complete_json(self, *, system_prompt: str, user_prompt: str) -> ModelCompletion: ...
