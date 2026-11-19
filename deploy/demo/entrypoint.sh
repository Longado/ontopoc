#!/bin/sh
# Starts the public demo: on the first start the data folder is empty, so the sample workspace is built into it
# (the admin's password is printed once in the log: keep it). Then the service runs in demo mode behind the proxy.
set -eu
: "${ONTOPOC_DOMAIN:?set ONTOPOC_DOMAIN to the address people open, e.g. demo.example.com}"
DATA="${ONTOPOC_DATA_DIR:-/data}"
if [ ! -f "$DATA/.ontopoc-demo-ready" ]; then
  if [ -f "$DATA/.ontopoc-demo" ]; then
    echo "An earlier seed stopped halfway: building the demo workspace again in $DATA"
    python -m ontology_poc_generator.demo seed --data-dir "$DATA" --force-fresh
  elif [ -z "$(python -m ontology_poc_generator.accounts list --data-dir "$DATA")" ]; then
    echo "First start: building the demo workspace in $DATA"
    python -m ontology_poc_generator.demo seed --data-dir "$DATA"
  fi
fi
exec python -m ontology_poc_generator.ontology_server --demo --port "${ONTOPOC_PORT:-8767}" --data-dir "$DATA" \
  --page-dir /app/page --origin "https://$ONTOPOC_DOMAIN"
