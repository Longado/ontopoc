"""The one door every model call in the product goes through.

An agent here is one bounded judgement that code checks afterwards: it never calls another agent, and it never decides
what happens next. The definitions — what each one sees, what it hands back, how code checks it, what it may not do —
are in docs/AGENTS.md; this module keeps the part code has to enforce: the name a call goes out under, one record per
call, and telling a failed request from a reply that is not JSON.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ontology_poc_generator.recognition import RecognitionError

AGENTS = {
    'table_modeller': '表格建模员',
    'document_modeller': '文档建模员',
    'question_writer': '出题员',
    'variant_matcher': '名称对应员',
    'field_describer': '字段释义员',
}


@dataclass(frozen=True)
class Judgement:
    reply: object | None   # the parsed JSON; None when the request failed or the reply was not JSON
    model: str | None
    failure: str | None    # None, 'request' or 'not_json'
    message: str = ''

    @property
    def account_empty(self) -> bool:
        """The one failure where trying again cannot help."""
        return self.failure == 'request' and 'HTTP Error 402' in self.message


def ask_model(gateway, agent: str, prompt_version: str, system_prompt: str, request: dict) -> Judgement:
    label = AGENTS[agent]   # a call under a name nobody defined does not go out
    started = time.monotonic()
    try:
        completion = gateway.complete_json(system_prompt=system_prompt, user_prompt=json.dumps(request, ensure_ascii=False))
    except RecognitionError as exc:
        judgement = Judgement(None, None, 'request', str(exc))
    else:
        try:
            judgement = Judgement(json.loads(completion.content), completion.model, None)
        except ValueError:
            judgement = Judgement(None, completion.model, 'not_json', 'model response is not JSON')
    log = getattr(gateway, 'log_call', None)
    if log:
        log({'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'agent': agent, 'label': label,
             'prompt_version': prompt_version, 'model': judgement.model, 'ms': int((time.monotonic() - started) * 1000),
             'outcome': judgement.failure or 'ok', 'error': judgement.message[:200]})
    return judgement


class LoggedGateway:
    """The service's gateway: the same calls, each one appended as a line to a local file."""

    def __init__(self, gateway, path: Path):
        self._gateway, self._path, self._lock = gateway, path, threading.Lock()

    def complete_json(self, *, system_prompt: str, user_prompt: str):
        return self._gateway.complete_json(system_prompt=system_prompt, user_prompt=user_prompt)

    def log_call(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False) + '\n'
        with self._lock:   # three builds run side by side; their lines must not interleave
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open('a', encoding='utf-8') as f:
                f.write(line)
