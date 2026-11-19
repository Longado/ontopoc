# OntoPoc pilot quick start (one page)

For a team of 3 to 8 (ops, finance, data) running a 2-week pilot on one machine. Needs Python 3.11+ and Node 22+.

## 1. Install and start

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc
scripts/ontopoc-start.sh
```

The script sets up a virtual environment, builds the page, asks you for the first admin's name and a password (12 characters or more), and starts the service at **http://127.0.0.1:8767**. Run it again any time to start the service again.

If the script is not in your checkout yet, do it by hand (see the main [README.en.md](../../README.en.md)): `python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[sources]'`, then `(cd landing-page && npm ci && npm run build)`, then `PYTHONPATH=src python3 -m ontology_poc_generator.accounts create-admin`, then `PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server`.

The service listens on this machine only. For teammates on other computers, put an HTTPS proxy in front of it ([docs/DEPLOY.md](../DEPLOY.md), in Chinese, has Caddy and nginx snippets and the `--origin` setting); do not open port 8767 to the network.

## 2. Add teammates and roles

Sign in as the admin, then **Settings > Users > New user**. The dialog gives you a message with the sign-in address, username and an initial password to send to that person (shown once). They must choose a new password at first sign-in.

| Role | Can |
|---|---|
| Viewer | Read and ask questions; cannot see raw data rows |
| Builder | Also upload data, create object types and pipelines, and confirm what others built |
| Admin | Also manage users, connect databases, set permissions |

**Make at least two Builders.** A definition is confirmed by a different builder than the one who proposed it; with a single builder, the service lets that person confirm and the log says so. For a pilot, a good split is 2 to 3 Builders (whoever knows the data) and the rest Viewers who ask questions.

## 3. Model key (optional)

```bash
export OPENROUTER_API_KEY=your-key     # or DEEPSEEK_API_KEY; set it in the terminal that starts the service
```

Never write the key into a file or paste it into chat. **Without a key**, uploads, definitions, confirmation, the review queue and the checks all work. What turns off: suggestions of object types, drafted meanings, and the Assistant's natural-language answers (it says the key is missing). The model sees names, types, meanings and values of low-variety columns, never rows.

## 4. Where data lives and backups

With `scripts/ontopoc-start.sh` everything is in `~/.ontopoc/data` (or `ONTOPOC_DATA_DIR`); started by hand, it is `output/ontology-runs/` in the checkout (or the folder you pass as `--data-dir`):

| File | What it is |
|---|---|
| `workspace.sqlite` | All datasets and versions, definitions, confirmations, answers, logs, and the accounts' password hashes |
| `sources.key` | The key that seals database passwords. Lose it and database sources must be re-entered |

Back up both **with the service stopped**, or run `sqlite3 workspace.sqlite ".backup /path/to/backup.sqlite"`. Keep backups where only you can read them: the sqlite file contains password hashes. Upload limit: 10 MB per upload; a table at most 1 million cells.

## 4b. Reading from MySQL or PostgreSQL

Admins add a database under **Data > Sources** (needs `pip install -e '.[sources]'`, which the start script does). Give OntoPoc a read-only account. Each table becomes a dataset; **Update by key** keeps rows that vanished from the table, **Overwrite** mirrors it.

Encryption is **None** by default for a database on the same machine and **Required** otherwise. "Required (verify certificate)" checks the server's certificate *and its host name*. MySQL's auto-generated certificate has no host name, so it never passes, even when you paste its CA. For a database on another machine, have the DBA install a certificate issued for the host name you connect to (from your company CA; paste that CA in the source form).

## 5. Next

Run [FIRST_DEFINITION.md](FIRST_DEFINITION.md) with the sample data in [sample/](sample/), then follow the schedule in [README.md](README.md). The **Send feedback** link in the avatar menu (top right) opens the feedback page; set `ONTOPOC_FEEDBACK_URL` before starting the service to point it at your own form or chat.
