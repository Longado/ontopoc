"""How much a token and a person may ask. Each question can cost a model call and leaves a saved answer, and an outside agent can ask without anyone watching, so a
token may ask TOKEN_LIMIT questions in any hour and a person (all their tokens and the page together) PERSON_LIMIT. The asks are kept in the workspace file, so a
restart does not give the hour back. A refusal is a 429 that says when the oldest ask leaves the hour; it is not counted itself."""
from __future__ import annotations

import math
import os
import time

from ontology_poc_generator.accounts import transaction
from ontology_poc_generator.lang import tr
from ontology_poc_generator.workspace_questions import QaRefused

TOKEN_LIMIT = 60
PERSON_LIMIT = 60
WINDOW = 3600   # seconds
GUEST_LIMIT = 10   # what a demo guest may ask in an hour
DAY = 86400
DEMO_ALL = 'demo:all'   # the key all guests' asks are also counted under, for the demo's daily cap


def demo_daily_asks() -> int:
    try:
        return int(os.environ.get('ONTOPOC_DEMO_DAILY_ASKS', '200'))
    except ValueError:
        return 200


class AskBudgetSpent(QaRefused):
    def __init__(self, limit: int, whose: str, wait: int):
        minutes = max(1, math.ceil(wait / 60))
        super().__init__(tr(f'提问太频繁：{whose}每小时最多 {limit} 个问题，现在用完了。约 {minutes} 分钟后再问。',
                            f'Too many questions: {whose} can ask {limit} questions an hour, and that is used up. Ask again in about {minutes} {"minute" if minutes == 1 else "minutes"}.'), 429)
        self.wait = wait


class DemoSpent(AskBudgetSpent):
    def __init__(self, limit: int, wait: int):
        minutes = max(1, math.ceil(wait / 60))
        QaRefused.__init__(self, tr(f'演示今天的 {limit} 个提问已经用完，约 {minutes} 分钟后再来。',
                                    f'The demo has used today\'s questions ({limit}). Come back in about {minutes} {"minute" if minutes == 1 else "minutes"}.'), 429)
        self.wait = wait


def take(conn, user: dict | None, now: float | None = None) -> None:
    """Counts one ask for this person (and the token they come with, if any), or raises AskBudgetSpent."""
    if user is None or user.get('id') is None:   # the local session of a service with no sign-in: nobody to count
        return
    now = time.time() if now is None else now
    conn.execute('CREATE TABLE IF NOT EXISTS ask_budget (who TEXT NOT NULL, at REAL NOT NULL)')
    conn.execute('CREATE INDEX IF NOT EXISTS ask_budget_who ON ask_budget(who, at)')
    guest = user.get('provider') == 'demo'
    counted = [(f'user:{user["id"]}', GUEST_LIMIT if guest else PERSON_LIMIT, tr('你', 'You'))]
    if user.get('token_id') is not None:
        counted.insert(0, (f'token:{user["token_id"]}', TOKEN_LIMIT, tr('这个令牌', 'This token')))
    with transaction(conn):
        conn.execute('DELETE FROM ask_budget WHERE at <= ? AND who != ?', (now - WINDOW, DEMO_ALL))
        conn.execute('DELETE FROM ask_budget WHERE at <= ?', (now - DAY,))
        for who, limit, whose in counted:
            used, oldest = conn.execute('SELECT COUNT(*), MIN(at) FROM ask_budget WHERE who = ?', (who,)).fetchone()
            if used >= limit:
                raise AskBudgetSpent(limit, whose, max(1, math.ceil(oldest + WINDOW - now)))
        if guest:
            used, oldest = conn.execute('SELECT COUNT(*), MIN(at) FROM ask_budget WHERE who = ?', (DEMO_ALL,)).fetchone()
            if used >= demo_daily_asks():
                raise DemoSpent(demo_daily_asks(), max(1, math.ceil(oldest + DAY - now)))
            counted.append((DEMO_ALL, 0, ''))
        conn.executemany('INSERT INTO ask_budget(who, at) VALUES (?, ?)', [(who, now) for who, _, _ in counted])


def give_back(conn, user: dict | None) -> None:
    """Takes back the one ask just counted for this person: the service had no model, so nothing was asked and nothing was saved."""
    if user is None or user.get('id') is None:
        return
    keys = [f'user:{user["id"]}']
    if user.get('token_id') is not None:
        keys.append(f'token:{user["token_id"]}')
    if user.get('provider') == 'demo':
        keys.append(DEMO_ALL)
    with transaction(conn):
        for who in keys:
            conn.execute('DELETE FROM ask_budget WHERE rowid = (SELECT rowid FROM ask_budget WHERE who = ? ORDER BY at DESC, rowid DESC LIMIT 1)', (who,))
