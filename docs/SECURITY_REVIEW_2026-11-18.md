# Security review, 2026-11-18

## Scope

Logins, sessions, roles and permissions before pilot teams run OntoPoc self-hosted (and later behind an HTTPS proxy, see DEPLOY.md):
`auth_http.py`, `accounts.py`, `access.py`, `agent_access.py`, the request dispatch in `ontology_server.py`, `sources_http.py`, `use_layer.py`,
`mcp_server.py`, and how `type_access`, `row_rules` and the per-owner stores (assistant turns, questions, notices, actions) are reached over HTTP.

## Method

Read the code, then probed a real server (the test helpers in `tests/test_access.py`) with a team of admin, two builders and a viewer:
route matrix by role, other-person ids, odd paths and methods. Only what could be shown with a request or a test was treated as a finding.

## Findings

| # | Severity | What | Status | Test |
|---|----------|------|--------|------|
| 1 | Low | A failed 500 or a failed modeling job told the signed-in person the text of file errors (OSError), which carry server paths (`[Errno 28] ...: '/srv/.../run.json'`). Now only the kind of error is said, and the full text goes to the service log. | Fixed | `tests/test_security_review_2026_11.py::ErrorTextTests` |
| 2 | Low | A failed sign-in wrote the typed name to the log even when no account had that name. A person who pastes their password into the name box left it in `workspace.sqlite` in plain text. A name no account has is now logged as `(unknown name)`; a real account's name is still kept. (`tests/test_accounts.py` changed to match.) | Fixed | `tests/test_security_review_2026_11.py::SecurityReviewTests` |

## Notes (not changed, no failing request)

- Personal tokens made by the person on My account (`all` scope) have no end date; only admin-issued agent tokens expire (7 to 365 days). They are revoked on password change, role change and disabling. Consider an expiry for them too.
- The gate reads the path with `urlsplit` (drops `#...` and tab characters), while the dispatch compares the raw `self.path`. No case was found where this gives more rights than the table says (a mismatch falls to a 404 or the admin default), but one normalised path used by both would remove the doubt.
- The login limit counts by address. Behind a proxy that is not on this machine and not listed with `--trusted-proxy`, everyone shares the proxy's address and 20 wrong passwords in ten minutes block everyone. DEPLOY.md already says to set it.
- A user can create many personal tokens (no cap); labels are limited to 64 characters. Storage growth only.

## Checked and fine

- Passwords: scrypt (N=2^15, r=8, p=3, 16-byte random salt, cost stored per hash and re-hashed at next sign-in), `hmac.compare_digest`, NFC-normalised, minimum 12 and maximum 1024 characters, common-password and same-as-username checks, at most 3 hashes at once.
- Lockout: counted before the password is checked, by name+address, by name and by address; unknown names counted the same; same work and same words for wrong name, wrong password and no password (dummy hash); disabled is told only after the right password.
- Reset and first login: admin reset sets `must_change`, ends sessions, revokes tokens and clears locks; a person cannot reset their own password without the current one; a `must_change` person can only call me, logout and password.
- Sessions: 256-bit random, only the SHA-256 stored, HttpOnly, SameSite=Strict, `Secure` and the `__Host-` prefix once an https origin is set, 8 h idle and 14 day absolute limits, new session at every sign-in (the old one ends), at most 10 per person. Ended on logout, password change (the current one kept), role change, and disabling; a disabled person's token stops at once.
- CSRF: every POST needs an Origin from the allowed list unless it carries a real bearer token (an empty bearer value does not count); the Host must be a configured one; no PUT/DELETE/OPTIONS/HEAD/PATCH handlers (501), so no preflight can succeed. A bearer header makes the cookie be ignored.
- Authorization: one route table, default deny (a route not listed needs admin, and a test fails when the server has a route the table lacks). Viewer, builder and admin probes of `/api/users`, `/permissions`, `/sources`, `/row-rules`, `/column-access` with query strings, trailing slashes, `//`, case changes and encoded characters all gave 403 for the wrong role.
- Ownership (IDOR): assistant turns, ask history and answers, notices and tokens are all filtered by the caller's id; another builder's turn id and another person's token id answer 404 (or no row). Only the submitter can withdraw an action.
- Tokens: read scope allows GET plus a short list of read-only POSTs; it cannot reach account routes (a token is refused there); expired, revoked and disabled-owner tokens are refused; admin accounts get no agent token; tokens are shown once and stored hashed.
- Proxy headers: `X-Forwarded-For` is believed only from a trusted peer, and then only its last address; `--no-auth` refuses any proxy header, any `--origin`, and needs `ONTOPOC_DEV=1`. The server binds to 127.0.0.1 only.
- Files: saved runs, jobs and library items are opened only through strict name patterns (`SAVED_NAME`, `JOB_ID`); upload names are not used as paths; downloads set `Content-Disposition` with the name URL-quoted; every answer carries nosniff, no-referrer and a CSP of `default-src 'none'`.
- Logs: the access log is off; no token or password is printed; the 500 for sources and schedules already answers a fixed sentence.
