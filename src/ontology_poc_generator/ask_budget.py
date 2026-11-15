"""How much a token and a person may ask. Each question can cost a model call and leaves a saved answer, and an outside agent can ask without anyone watching, so a
token may ask TOKEN_LIMIT questions in any hour and a person (all their tokens and the page together) PERSON_LIMIT. The asks are kept in the workspace file, so a
restart does not give the hour back. A refusal is a 429 that says when the oldest ask leaves the hour; it is not counted itself."""
from __future__ import annotations

import math
import time

from ontology_poc_generator.accounts import transaction
from ontology_poc_generator.workspace_questions import QaRefused

TOKEN_LIMIT = 60
PERSON_LIMIT = 60
WINDOW = 3600   # seconds


class AskBudgetSpent(QaRefused):
    def __init__(self, limit: int, whose: str, wait: int):
        super().__init__(f'提问太频繁：{whose}每小时最多 {limit} 个问题，现在用完了。约 {max(1, math.ceil(wait / 60))} 分钟后再问。', 429)
        self.wait = wait


def take(conn, user: dict | None, now: float | None = None) -> None:
    """Counts one ask for this person (and the token they come with, if any), or raises AskBudgetSpent."""
    if user is None or user.get('id') is None:   # the local session of a service with no sign-in: nobody to count
        return
    now = time.time() if now is None else now
    conn.execute('CREATE TABLE IF NOT EXISTS ask_budget (who TEXT NOT NULL, at REAL NOT NULL)')
    conn.execute('CREATE INDEX IF NOT EXISTS ask_budget_who ON ask_budget(who, at)')
    counted = [(f'user:{user["id"]}', PERSON_LIMIT, '你')]
    if user.get('token_id') is not None:
        counted.insert(0, (f'token:{user["token_id"]}', TOKEN_LIMIT, '这个令牌'))
    with transaction(conn):
        conn.execute('DELETE FROM ask_budget WHERE at <= ?', (now - WINDOW,))
        for who, limit, whose in counted:
            used, oldest = conn.execute('SELECT COUNT(*), MIN(at) FROM ask_budget WHERE who = ?', (who,)).fetchone()
            if used >= limit:
                raise AskBudgetSpent(limit, whose, max(1, math.ceil(oldest + WINDOW - now)))
        conn.executemany('INSERT INTO ask_budget(who, at) VALUES (?, ?)', [(who, now) for who, _, _ in counted])
