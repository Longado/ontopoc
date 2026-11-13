"""Which role a route needs. One table, default deny: a route that is not in it needs an admin, and tests/test_access.py fails when the
server has a route the table does not list. Row and field rules (a later round) hang off the same lookup."""
from __future__ import annotations

import re

from ontology_poc_generator.accounts import RANK

PUBLIC = 'public'    # no sign-in needed
SESSION = 'session'  # any signed-in person, whatever the role

_RUNS = r'/api/ontology/runs(/.+)?'
_UPLOAD_AND_DELETE = r'/api/workspace/datasets/(upload|delete)'

ROUTES: list[tuple[str, str, str]] = [
    ('GET', r'/api/ontology/health', PUBLIC),   # the service answers {ok} to a stranger and the code fingerprint only to a signed-in person
    ('POST', r'/api/auth/login', PUBLIC),
    ('GET', r'/api/auth/me', SESSION),
    ('POST', r'/api/auth/(logout|password)', SESSION),
    ('GET', r'/api/auth/tokens', SESSION),
    ('POST', r'/api/auth/tokens(/revoke)?', SESSION),
    # read
    ('GET', r'/api/workspace/(datasets|tasks)(/.+)?', 'viewer'),
    ('GET', _RUNS, 'viewer'),
    ('GET', r'/api/ontology/jobs/[^/]+', 'viewer'),
    ('GET', r'/api/ontology/library(/.+)?', 'viewer'),
    ('POST', r'/api/ontology/ask', 'viewer'),
    # change data, start model work, write definitions
    ('POST', _UPLOAD_AND_DELETE, 'builder'),
    ('POST', r'/api/ontology/(build|jobs|preview|compare|variants|requery|library/import)', 'builder'),
    ('POST', r'/api/ontology/reference/(preview|confirm)', 'builder'),
    ('POST', r'/api/ontology/(confirm|acceptance|card|derived|bulk-approve|repeat-rules|views|rules|form|pipelines/run)', 'builder'),
    ('POST', r'/api/ontology/(form|code-meanings)/draft', 'builder'),
    ('POST', r'/api/ontology/code-meanings(/(dismiss|withdraw))?', 'builder'),
    ('POST', r'/api/ontology/review/confirm', 'builder'),
    # people and settings
    ('GET', r'/api/users', 'admin'),
    ('POST', r'/api/users(/(update|disable|reset-password))?', 'admin'),
]
_COMPILED = [(method, re.compile(pattern), role) for method, pattern, role in ROUTES]


def route_role(method: str, path: str) -> str | None:
    """The role the table names for this route; None when the table does not list it."""
    for m, pattern, role in _COMPILED:
        if m == method and pattern.fullmatch(path):
            return role
    return None


def required_role(method: str, path: str) -> str:
    """Role (or PUBLIC / SESSION) needed for a request; a route not in the table needs an admin."""
    return route_role(method, path) or 'admin'


def allows(role: str, needed: str) -> bool:
    return needed in (PUBLIC, SESSION) or RANK[role] >= RANK[needed]
