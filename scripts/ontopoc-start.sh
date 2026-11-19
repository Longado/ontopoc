#!/bin/sh
# One command from a fresh clone to a running OntoPoc: ./scripts/ontopoc-start.sh
# Installs what is missing (venv, python packages, page build), makes the first admin when there is none, then serves the
# page and the API together on one address. A second run skips everything already done.
#   ONTOPOC_DATA_DIR   where the data lives (default ~/.ontopoc/data)
#   ONTOPOC_PORT       the port (default 8767)
#   ONTOPOC_PYTHON     the python to build the venv with (default python3)
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DATA_DIR=${ONTOPOC_DATA_DIR:-$HOME/.ontopoc/data}
PORT=${ONTOPOC_PORT:-8767}
PY=${ONTOPOC_PYTHON:-python3}
VENV="$ROOT/.venv"
PAGE="$ROOT/landing-page"
DIST="$PAGE/dist/client"

say() { printf '%s\n' "$*"; }
die() { printf 'ontopoc: %s\n' "$*" >&2; exit 1; }

command -v "$PY" >/dev/null 2>&1 || die "python3 not found. Install Python 3.11 or newer."
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "Python 3.11 or newer is needed (this is $("$PY" -c 'import platform; print(platform.python_version())')). Set ONTOPOC_PYTHON to a newer python3."
command -v node >/dev/null 2>&1 || die "node not found. Install Node 18 or newer (22 recommended)."
command -v npm >/dev/null 2>&1 || die "npm not found. Install Node 18 or newer (22 recommended)."
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 18 ? 0 : 1)' \
  || die "Node 18 or newer is needed (this is $(node --version))."

# python side
if [ ! -x "$VENV/bin/python" ]; then
  say "Creating $VENV ..."
  "$PY" -m venv "$VENV" || die "could not create a virtual environment (on Debian/Ubuntu: apt install python3-venv)."
fi
STAMP="$VENV/.ontopoc-installed"
if [ ! -f "$STAMP" ] || [ "$ROOT/pyproject.toml" -nt "$STAMP" ]; then
  say "Installing python packages ..."
  "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -e "$ROOT[sources]" || die "pip install failed."
  : > "$STAMP"
fi

# page side: build when there is no build, or something it is built from is newer
need_build=0
if [ ! -f "$DIST/index.html" ]; then
  need_build=1
elif [ -n "$(find "$PAGE/src" "$PAGE/public" "$PAGE/index.html" "$PAGE/legacy.html" "$PAGE/package-lock.json" "$PAGE/vite.config.mjs" -newer "$DIST/index.html" -type f 2>/dev/null | head -n 1)" ]; then
  need_build=1
fi
if [ "$need_build" = 1 ]; then
  if [ ! -d "$PAGE/node_modules" ] || [ "$PAGE/package-lock.json" -nt "$PAGE/node_modules" ]; then
    say "Installing page packages (npm ci) ..."
    (cd "$PAGE" && npm ci --no-audit --no-fund --loglevel=error) || die "npm ci failed."
    touch "$PAGE/node_modules"
  fi
  say "Building the page ..."
  (cd "$PAGE" && npm run build --silent >/dev/null) || die "the page build failed (run: cd landing-page && npm run build)."
fi

# first admin
mkdir -p "$DATA_DIR"
chmod 700 "$DATA_DIR" 2>/dev/null || true
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
if [ -z "$("$VENV/bin/python" -m ontology_poc_generator.accounts list --data-dir "$DATA_DIR")" ]; then
  say ""
  say "No accounts yet. Make the first admin (a name, then a password of at least 12 characters):"
  "$VENV/bin/python" -m ontology_poc_generator.accounts create-admin --data-dir "$DATA_DIR" || die "no admin was made; run this script again."
fi

if [ -z "${OPENROUTER_API_KEY:-}" ] && [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  say ""
  say "Note: no OPENROUTER_API_KEY or DEEPSEEK_API_KEY is set, so meanings and suggestions are off. Everything else works; set one and run this again to turn them on."
fi

say ""
say "Open  http://127.0.0.1:$PORT/  and sign in with the admin you made.  (Ctrl-C stops it; data is in $DATA_DIR)"
say ""
exec "$VENV/bin/python" -m ontology_poc_generator.ontology_server --port "$PORT" --data-dir "$DATA_DIR" --page-dir "$DIST"
