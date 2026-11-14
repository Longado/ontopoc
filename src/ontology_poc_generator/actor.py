"""Who is acting in this thread. The HTTP gate sets it for each request; the store reads it when it writes a name, to keep the account's id
beside the name that was written (the name is a snapshot, so renaming a person does not rewrite history). A name that is not the actor's
(an old free-text signature, a signature typed under --no-auth) gets no id."""
from __future__ import annotations

from contextvars import ContextVar

_actor: ContextVar[dict | None] = ContextVar('actor', default=None)


def set_actor(user: dict | None) -> None:
    """The signed-in person for this request, or None (nobody, or the built-in local admin, who has no account)."""
    _actor.set(user if user and user.get('id') is not None else None)


def current_actor() -> dict | None:
    return _actor.get()


def actor_id_for(name: str | None) -> int | None:
    """The actor's account id when `name` is the actor's own display name."""
    user = _actor.get()
    return user['id'] if user and name is not None and user['display_name'] == name else None
