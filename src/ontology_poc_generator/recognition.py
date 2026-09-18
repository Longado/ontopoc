"""Model gateway contract shared by every model call: one JSON completion in, one JSON completion out."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RecognitionError(ValueError):
    """A model response cannot enter the deterministic boundary."""


def model_failure_text(message: str) -> str:
    """What to tell the person when the model could not be reached. An empty account is the one cause seen so far
    where "try again later" is wrong advice; it starts with the same words so callers can tell an outage from a bad reply."""
    detail = str(message)[:160]
    if 'HTTP Error 402' in detail:
        return f'模型请求失败：模型账户余额不足（{detail}）。这不是数据的问题，给账户充值后再试'
    return f'模型请求失败（{detail}），请稍后重试'


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
