# The public demo site

A public OntoPoc where visitors click **Try the demo** and look around as a guest: read-only, the pilot sample data
(`docs/pilot/sample`), questions answered by the model within a daily cap. Real accounts are made by the admin only.
Real business data never goes here; pilot teams run their own copy (`scripts/ontopoc-start.sh`).

## What a visitor gets

- A guest account made on the click (`guest-…`, role viewer). It reads everything in the sample workspace and asks
  questions; it cannot upload, define, confirm, change a password or make tokens.
- At most 10 questions an hour per guest, and `ONTOPOC_DEMO_DAILY_ASKS` (default 200) for all guests together in any
  24 hours, so the model bill has a ceiling. Set a spending limit on the key at the provider too.
- At most 5 guests per address an hour (an IPv6 address counts by its /64), `ONTOPOC_DEMO_GUESTS_PER_HOUR` (default 60) new guests an hour in all, and `ONTOPOC_DEMO_MAX_GUESTS` (default 300) at once. Guests, their questions
  and their sessions are deleted after 24 hours; the sample workspace itself never changes, because guests cannot write.

## Run it on a server

Needs: a Linux server with Docker, a domain whose DNS points at it, ports 80 and 443 open.

```sh
git clone https://github.com/Longado/ontopoc && cd ontopoc/deploy/demo
cp demo.env.example demo.env      # fill in ONTOPOC_DOMAIN and the demo's own model key
docker compose --env-file demo.env up -d --build
docker compose logs ontopoc | grep -i password   # the demo admin's password, printed once on the first start
```

Caddy fetches the HTTPS certificate itself. If another proxy sits in front of Caddy (a CDN or a tunnel), make Caddy trust it (`trusted_proxies`), or every visitor counts as that proxy's one address. Open `https://<domain>/`.

## Run it on this machine (no Docker)

```sh
PYTHONPATH=src .venv/bin/python -m ontology_poc_generator.demo seed --data-dir ~/.ontopoc/demo
PYTHONPATH=src .venv/bin/python -m ontology_poc_generator.ontology_server --demo \
  --data-dir ~/.ontopoc/demo --page-dir landing-page/dist/client --port 8770
```

## Start over

`docker compose down -v` deletes the workspace; the next `up` builds the sample again.
