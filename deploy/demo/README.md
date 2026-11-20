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

The model key is optional: without one the demo runs with questions off (boards still work) and the page says so.

After the first visitors, check that they are counted by their own addresses and not by one shared address (which would
let only 5 guests in an hour):

```sh
docker compose exec ontopoc python -c "import sqlite3; print(sqlite3.connect('/data/workspace.sqlite').execute('SELECT client, COUNT(*) FROM demo_guest GROUP BY client').fetchall())"
```

## Try the whole stack on your own machine first

With Docker (or colima) running, the same two containers on `https://localhost:8443` with Caddy's own local certificate
(the browser warns about it once):

```sh
cd deploy/demo
sed 's/^ONTOPOC_DOMAIN=.*/ONTOPOC_DOMAIN=localhost:8443/' demo.env.example > demo.env
printf 'services:\n  net:\n    ports: !override\n      - "8443:8443"\n' > /tmp/ontopoc-local.yml
docker compose -p ontopoc-test -f docker-compose.yml -f /tmp/ontopoc-local.yml --env-file demo.env up -d --build
docker compose -p ontopoc-test down -v      # when done
```

Here every visit comes through Docker's own port forward, so guests all show one address; on a server they show their own.

## Run it on this machine (no Docker)

```sh
PYTHONPATH=src .venv/bin/python -m ontology_poc_generator.demo seed --data-dir ~/.ontopoc/demo
PYTHONPATH=src .venv/bin/python -m ontology_poc_generator.ontology_server --demo \
  --data-dir ~/.ontopoc/demo --page-dir landing-page/dist/client --port 8770
```

## How it holds together

Three containers share one network namespace: `net` (does nothing, owns the ports), `ontopoc` (the service, on loopback
only) and `caddy` (HTTPS). The service or Caddy can crash or be restarted alone and the site comes back in a second or
two; `docker compose ps` shows the service `healthy` once the sample workspace is built. Caddy sends
`Strict-Transport-Security`, so browsers that have visited keep to HTTPS.

## Start over

`docker compose down -v` deletes the workspace; the next `up` builds the sample again.
