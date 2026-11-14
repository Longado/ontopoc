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
    ('GET', r'/api/workspace/(datasets|types|relations)(/.+)?', 'viewer'),   # what a person sees of types and relations is filtered by who they are (type_access)
    ('GET', r'/api/workspace/(tasks|relation-form|queue)', 'builder'),   # the task list quotes keys and the reasons the model's suggestions were dropped, which carry values
    ('GET', r'/api/workspace/actions(/.+)?', 'builder'),   # actions are for builders: a viewer runs and reads none (object_actions.action_visible)
    ('GET', r'/api/workspace/pipelines(/.+)?', 'builder'),   # pipelines are for builders: their steps and previews quote the data (workspace_pipelines.pipeline_visible)
    ('GET', r'/api/workspace/ask(/.+)?', 'viewer'),   # a person's own questions and answers, within what they may see (workspace_questions)
    ('GET', _RUNS, 'viewer'),
    ('GET', r'/api/ontology/jobs/[^/]+', 'viewer'),
    ('GET', r'/api/ontology/library(/.+)?', 'viewer'),
    ('POST', r'/api/ontology/ask', 'viewer'),
    ('POST', r'/api/workspace/ask', 'viewer'),
    # change data, start model work, write definitions
    ('POST', _UPLOAD_AND_DELETE, 'builder'),
    ('POST', r'/api/workspace/types(/(update|meanings|confirm|key-check|suggest|privacy|views(/(update|confirm))?))?', 'builder'),
    ('POST', r'/api/workspace/relations(/(update|confirm))?', 'builder'),
    ('POST', r'/api/workspace/queue/(confirm|send-back)', 'builder'),
    ('POST', r'/api/workspace/actions(/(update|confirm|submit|decide|withdraw))?', 'builder'),   # a person may not approve their own submission (object_actions.decide)
    ('POST', r'/api/workspace/pipelines(/(update|confirm|preview|summary|columns|review|run|format-guess|expression/(check|trial)))?', 'builder'),   # confirming needs a second person who did not edit it (workspace_pipelines.confirm_pipeline)
    ('POST', r'/api/workspace/row-rules', 'admin'),   # who sees which rows of a type: the admin's, with the permissions page
    ('POST', r'/api/ontology/(build|jobs|preview|compare|variants|requery|library/import)', 'builder'),
    ('POST', r'/api/ontology/reference/(preview|confirm)', 'builder'),
    ('POST', r'/api/ontology/(confirm|acceptance|card|derived|bulk-approve|repeat-rules|views|rules|form|pipelines/run)', 'builder'),
    ('POST', r'/api/ontology/(form|code-meanings)/draft', 'builder'),
    ('POST', r'/api/ontology/code-meanings(/(dismiss|withdraw))?', 'builder'),
    ('POST', r'/api/ontology/review/confirm', 'builder'),
    # people and settings
    ('GET', r'/api/users', 'admin'),
    ('POST', r'/api/users(/(update|disable|reset-password))?', 'admin'),
    ('GET', r'/api/settings', 'admin'),
    ('POST', r'/api/settings', 'admin'),
    ('GET', r'/api/workspace/permissions', 'admin'),   # who sees which type: only an admin reads or changes it
    ('POST', r'/api/workspace/permissions', 'admin'),
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
