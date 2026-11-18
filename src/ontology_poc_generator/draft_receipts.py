"""Receipts for what the assistant drafted: the server, not the page, decides whether a saved object counts as "drafted by the assistant".

When the server hands back a pipeline draft or a suggested type it also issues a `draft_receipt`: a random id kept in the workspace database (table draft_receipt),
bound to the person who was given the draft, the kind ('pipeline' or 'type'), the target (the pipeline's or type's English name when known, else None) and a
fingerprint of the drafted content. It lasts 24 hours and is used once. A save that carries a valid receipt is marked (see assistant_checks.drafted_mark); a forged,
expired, reused or someone else's receipt is ignored without refusing the save."""
from __future__ import annotations

import hashlib
import json
import secrets
import time

TTL_SECONDS = 24 * 3600

_TABLE = 'CREATE TABLE IF NOT EXISTS draft_receipt (id TEXT PRIMARY KEY, who TEXT NOT NULL, kind TEXT NOT NULL, target TEXT, fingerprint_json TEXT NOT NULL, expires REAL NOT NULL)'


def _who(user: dict | None) -> str:
    return f'user:{user["id"]}' if user and user.get('id') is not None else 'local'


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def pipeline_fingerprint(steps: list[dict]) -> dict:
    """{step id: hash of the step as drafted}."""
    return {s['id']: _hash(s) for s in steps if isinstance(s, dict) and isinstance(s.get('id'), str)}


def type_fingerprint(content: dict) -> dict:
    """The fields a type's draft stands on: its dataset, its key and the columns it reads."""
    return {'dataset': content.get('dataset'), 'key': list(content.get('key') or []),
            'columns': sorted(p['column'] for p in content.get('properties') or [] if isinstance(p, dict) and 'column' in p)}


def issue(conn, user: dict | None, kind: str, target: str | None, fingerprint: dict, now: float | None = None) -> str:
    now = time.time() if now is None else now
    conn.execute(_TABLE)
    conn.execute('DELETE FROM draft_receipt WHERE expires <= ?', (now,))
    receipt = secrets.token_urlsafe(18)
    conn.execute('INSERT INTO draft_receipt(id, who, kind, target, fingerprint_json, expires) VALUES (?, ?, ?, ?, ?, ?)',
                 (receipt, _who(user), kind, target, json.dumps(fingerprint, sort_keys=True), now + TTL_SECONDS))
    return receipt


def redeem(conn, receipt, user: dict | None, kind: str, now: float | None = None) -> tuple[str | None, dict] | None:
    """(target, fingerprint) when `receipt` is live and was issued to this person for this kind; it is used up. None otherwise, silently."""
    if not isinstance(receipt, str) or not receipt:
        return None
    now = time.time() if now is None else now
    conn.execute(_TABLE)
    row = conn.execute('SELECT who, kind, target, fingerprint_json, expires FROM draft_receipt WHERE id = ?', (receipt,)).fetchone()
    if row is None or row[0] != _who(user) or row[1] != kind or row[4] <= now:
        return None
    if conn.execute('DELETE FROM draft_receipt WHERE id = ?', (receipt,)).rowcount != 1:   # used by someone in the meantime
        return None
    return row[2], json.loads(row[3])
