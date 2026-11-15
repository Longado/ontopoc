"""Which role a route needs. One table, default deny: a route that is not in it needs an admin, and tests/test_access.py fails when the
server has a route the table does not list. Row and field rules (a later round) hang off the same lookup."""
from __future__ import annotations

import re

from ontology_poc_generator.accounts import RANK

PUBLIC = 'public'    # no sign-in needed
SESSION = 'session'  # any signed-in person, whatever the role
UNLIMITED = 'unlimited'   # a builder or an admin whom no type list and no row rule limits (auth_http.limited_anywhere): the early screen's runs hold whole tables

_RUNS = r'/api/ontology/runs(/.+)?'
_UPLOAD_AND_DELETE = r'/api/workspace/datasets/(upload(/preview)?|delete)'

ROUTES: list[tuple[str, str, str]] = [
    ('GET', r'/api/ontology/health', PUBLIC),   # the service answers {ok} to a stranger and the code fingerprint only to a signed-in person
    ('POST', r'/api/auth/login', PUBLIC),
    ('GET', r'/api/auth/me', SESSION),
    ('POST', r'/api/auth/(logout|password)', SESSION),
    ('GET', r'/api/auth/tokens', SESSION),
    ('POST', r'/api/auth/tokens(/revoke)?', SESSION),
    # read
    ('GET', r'/api/workspace/(datasets|types|relations)(/.+)?', 'viewer'),   # what a person sees of types and relations is filtered by who they are (type_access)
    ('GET', r'/api/workspace/graph/(relations|lineage)', 'viewer'),   # the drawings leave out what this person may not see, like the pages they are made of (ontology_graph)
    ('GET', r'/api/workspace/(tasks|relation-form|queue(/group)?)', 'builder'),   # the task list quotes keys and the reasons the model's suggestions were dropped, which carry values
    ('GET', r'/api/workspace/actions(/.+)?', 'builder'),   # actions are for builders: a viewer runs and reads none (object_actions.action_visible)
    ('GET', r'/api/workspace/pipelines(/.+)?', 'builder'),   # pipelines are for builders: their steps and previews quote the data (workspace_pipelines.pipeline_visible)
    ('GET', r'/api/workspace/(sources|schedules)(/.+)?', 'builder'),   # a builder picks a source's tables and sets schedules; the connection details are shown to an admin only (workspace_sources.public_source)
    ('GET', r'/api/workspace/ask(/.+)?', 'viewer'),   # a person's own questions and answers, within what they may see (workspace_questions)
    ('GET', r'/api/workspace/explore/.+', 'viewer'),   # the explorer reads through type visibility, viewer visibility and row rules like the objects tab (explorer)
    ('POST', r'/api/workspace/explore/(table|chart)', 'viewer'),   # a POST only because the query is long; nothing is written
    ('GET', r'/api/workspace/dashboards(/.+)?', 'viewer'),   # which boards a person may open follows the board's scope (dashboards._may_open)
    ('POST', r'/api/workspace/dashboards/data', 'viewer'),   # a board worked out for whoever opens it, over what they may see
    ('POST', r'/api/workspace/dashboards(/(update|delete|preview))?', 'builder'),
    ('GET', r'/api/workspace/agent/(definitions|unconfirmed)', 'viewer'),   # what an outside agent reads, as the token's person (agent_access)
    ('GET', r'/api/workspace/agent/derived', 'viewer'),   # answered 405 with the way to ask: it is a POST now
    ('POST', r'/api/workspace/agent/derived', 'viewer'),   # a POST so that the key of the object read is not in an address a proxy logs; nothing is written
    ('GET', r'/api/workspace/agent(/skill)?', 'builder'),   # the page of what an agent can call, and the skill download
    ('GET', _RUNS, UNLIMITED),   # the early screen reads its runs with no type list, row rule or kept-back value applied
    ('GET', r'/api/ontology/jobs/[^/]+', UNLIMITED),
    ('GET', r'/api/ontology/library(/.+)?', 'viewer'),   # reference ontologies, no company data
    ('POST', r'/api/ontology/ask', UNLIMITED),
    ('POST', r'/api/workspace/ask', 'viewer'),
    # change data, start model work, write definitions
    ('POST', _UPLOAD_AND_DELETE, 'builder'),
    ('POST', r'/api/workspace/types(/(update|meanings|confirm|key-check|suggest|privacy|views(/(update|confirm))?|derived(/(update|confirm|trial|shape|expression))?))?', 'builder'),
    ('POST', r'/api/workspace/relations(/(update|confirm))?', 'builder'),
    ('POST', r'/api/workspace/queue/(confirm|confirm-group|send-back)', 'builder'),
    ('POST', r'/api/workspace/actions(/(update|confirm|submit|decide|withdraw|undo))?', 'builder'),   # a person may not approve their own submission (object_actions.decide)
    ('POST', r'/api/workspace/pipelines(/(update|confirm|preview|summary|columns|review|run|format-guess|expression/(check|trial)|llm/(state|trial|label|review|clear-cache)|ai/(parse|draft|explain)))?', 'builder'),   # confirming needs a second person who did not edit it (workspace_pipelines.confirm_pipeline)
    ('POST', r'/api/workspace/sources/(pull|refresh)', 'builder'),   # reading a table into a dataset is a builder's, like an upload
    ('POST', r'/api/workspace/sources(/(update|delete|test))?', 'admin'),   # a new outbound connection, and the password for it: the admin's
    ('POST', r'/api/workspace/schedules(/(update|delete))?', 'builder'),   # a schedule repeats what a builder may already do by hand
    ('POST', r'/api/workspace/row-rules', 'admin'),   # who sees which rows of a type: the admin's, with the permissions page
    ('POST', r'/api/workspace/column-access', 'admin'),   # who sees a column of a type: the admin's, with the permissions page
    ('POST', r'/api/ontology/library/import', 'builder'),
    ('POST', r'/api/ontology/(build|jobs|preview|compare|variants|requery)', UNLIMITED),
    ('POST', r'/api/ontology/reference/(preview|confirm)', UNLIMITED),
    ('POST', r'/api/ontology/(confirm|acceptance|card|derived|bulk-approve|repeat-rules|views|rules|form|pipelines/run)', UNLIMITED),
    ('POST', r'/api/ontology/(form|code-meanings)/draft', UNLIMITED),
    ('POST', r'/api/ontology/code-meanings(/(dismiss|withdraw))?', UNLIMITED),
    ('POST', r'/api/ontology/review/confirm', UNLIMITED),
    # people and settings
    ('GET', r'/api/users', 'admin'),
    ('POST', r'/api/users(/(update|disable|reset-password))?', 'admin'),
    ('GET', r'/api/users/tokens', 'admin'),   # tokens that act as a named person, for outside agents: made, listed and revoked by an admin
    ('POST', r'/api/users/tokens(/revoke)?', 'admin'),
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


# What a token made with scope 'read' may call besides every GET: ask a question and look at data (nothing here changes a definition, a rule, a dataset or an account;
# an answer is kept with the question, as for a person at the page).
READ_TOKEN_POSTS = ('/api/workspace/ask', '/api/workspace/explore/table', '/api/workspace/explore/chart', '/api/workspace/dashboards/data', '/api/workspace/dashboards/preview',
                    '/api/workspace/agent/derived')


def read_token_allows(method: str, path: str) -> bool:
    return method == 'GET' or path in READ_TOKEN_POSTS


def required_role(method: str, path: str) -> str:
    """Role (or PUBLIC / SESSION) needed for a request; a route not in the table needs an admin."""
    return route_role(method, path) or 'admin'


def allows(role: str, needed: str) -> bool:
    """The role part only: UNLIMITED needs a builder here, and the gate also asks limited_anywhere."""
    return needed in (PUBLIC, SESSION) or RANK[role] >= RANK['builder' if needed == UNLIMITED else needed]
