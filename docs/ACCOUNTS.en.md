# Sign-in and accounts

Moved from the [README](../README.en.md).

The service asks for a sign-in by default, and there is no default account or password. Make the first admin on the machine that runs the service:

```bash
PYTHONPATH=src python3 -m ontology_poc_generator.accounts create-admin     # asks for a name and a password (12 characters or more); reset-password in the same tool if it is forgotten
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --origin http://127.0.0.1:5178   # --origin: the address the page is served from (here the dev server); repeatable
```

An admin makes everyone else on the Users page: **viewer** reads and asks, **builder** also uploads data and changes definitions, **admin** also manages people. A new account must change the temporary password at its first sign-in. Every action is recorded under the signed-in person; a name typed into a request is ignored. Scripts and the MCP server use a token made under My account (set `ONTOPOC_TOKEN` for MCP); it has its owner's role, except that on the team workspace it cannot confirm a definition, approve a submitted change or record a checked number: the person does those signed in on the page.

**Two-person confirmation**: while two or more people can confirm, a definition one person proposes (meanings, object types, relations, views, actions, derived properties, pipelines) takes effect only when another confirms it, and the proposer cannot confirm their own. With one person who can confirm it switches itself off, and the log marks each self-confirmation. An admin can turn it off on the Users page. An edit made with a token to a confirmed definition, even of its name or description alone, puts it forward again for a person to confirm; each log line of a write made with a token names the token.

**Value rules and who sees what**: a value rule is part of its object type, so the type's confirmer confirms it with the type, and adding, changing or removing one puts the type forward again as a change of its key does. The counts of rows that break a rule, and the keys shown as examples, are of the rows the reader may see: a builder a row rule limits sees their own rows only. A rule on a property kept from someone is not shown to them anywhere (the type page, the review queue, `describe_definitions`). When new data breaks a confirmed rule the type goes back for another look; builders and admins who see all of its data read which rule and how many rows in the reason, the refusal and the standing; a person a row rule or a column limit keeps from part of the data reads the cause without the numbers; a viewer is told only that the type waits, and for whom.

**For a team**: the service listens on this machine only and does not do HTTPS. Put a proxy that does in front of it, for example Caddy (full steps, backups and what to watch in permissions are in [docs/DEPLOY.md](DEPLOY.md), in Chinese):

```
ontopoc.example.com {
    reverse_proxy 127.0.0.1:8767
}
```

Start the service with `--origin https://ontopoc.example.com`: only that address is accepted, the sign-in cookie is Secure, and the sign-in attempt limit counts the address the proxy saw. A non-local http address is refused. `workspace.sqlite` holds password hashes and sign-in records; it is readable by its owner only, and copying it to someone shares the hashes. The proxy must put the address it saw into X-Forwarded-For (nginx: `proxy_set_header X-Forwarded-For $remote_addr;`); the service believes only the last address in that header, and only from the proxies named with `--trusted-proxy` (by default this machine once an https `--origin` is set).

**Trying it on your own machine**: `--no-auth` turns sign-in off and treats every request as the local admin. Do not use it on a shared machine. It needs the environment variable `ONTOPOC_DEV=1`, is refused together with `--origin`, and refuses any request that carries a proxy header (X-Forwarded-For and the like).
