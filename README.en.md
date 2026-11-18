<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
    <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc" width="360">
  </picture>
</p>

<h1 align="center">OntoPoc</h1>
<p align="center"><strong>An ontology platform for a team: every definition is checked against the data and confirmed by a named person; anything unconfirmed, or out of date since the data changed, is refused in Q&amp;A with the reason.</strong></p>
<p align="center">Datasets → pipelines → object types, relations, views, actions, derived properties → Q&amp;A, boards, agents (MCP).</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue" alt="MIT"></a>
  <img src="https://img.shields.io/badge/tested%20on-macOS-black" alt="tested on macOS">
  <img src="https://img.shields.io/badge/Python-3.11%2B-green" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Node-22%2B-green" alt="Node 22+">
  <img src="https://img.shields.io/badge/status-Alpha-orange" alt="Alpha">
</p>

<p align="center">
  <a href="README.md">中文</a> ·
  <a href="https://longado.github.io/ontopoc/">Docs</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="docs/LEGACY_SCREEN.en.md#try-it">Try it</a> ·
  <a href="#use-with-mcp--claude">MCP / Claude</a> ·
  <a href="#ontology-faq">Ontology FAQ</a> ·
  <a href="#contributing">Contributing</a>
</p>

<p align="center"><sub>Ontology tool for MCP / Claude · Docs: <a href="https://longado.github.io/ontopoc/">longado.github.io/ontopoc</a> · Follow on X: <a href="https://x.com/linyutai120479">@linyutai120479</a></sub></p>

<p align="center">
  <img src="docs/media/ontopoc-hero.gif" alt="OntoPoc companion connects business tables into a draft ontology for review" width="960">
</p>
<p align="center"><sub>Concept illustration · <a href="docs/media/ontopoc-poster.png">Still image</a> · <a href="docs/media/ontopoc-motion.mp4">MP4</a></sub></p>

OntoPoc is an ontology tool for teams and for MCP / Claude clients. It is still in development and nobody but the author uses it yet. The main line is now a team app (the page root, `/`). Upload tables or connect read-only to PostgreSQL or MySQL, build datasets and pipelines, and build object types, relations, views, actions and derived properties from the data. Code checks each one against the data, another builder confirms it, and the data version it was confirmed on is kept. Q&A, boards and agents use confirmed definitions only. When the data changes, the affected definitions go back to "needs another look", and questions that use them are refused, naming which one and who can confirm it. It is not a knowledge-graph platform; this is schema work ahead of a knowledge graph or semantic layer.

The interface is in Chinese only. This page gives the Chinese label in parentheses the first time it names a screen, tab or button.

## The team app

| Part | What it does |
|---|---|
| Accounts and permissions | Local accounts with three roles (admin, builder, viewer) and server-side sessions. An admin can limit an object type to named people, limit rows by rule (allow-lists only), and keep a column's values from the model |
| Data | Datasets: upload CSV or Excel, update by key or overwrite, a new version each time. Sources: read-only PostgreSQL and MySQL, with certificate checks. Schedules: hourly or daily pulls and pipeline runs |
| Pipelines | Filter, join, group, dedupe, calculated columns and more, with an expression editor. Union stacks the rows of several steps by column name: it refuses differing types, missing columns and code columns whose confirmed meanings differ, and counts rows that appear in more than one input. Split sends each row to the first branch whose condition holds, with an optional rest branch, and counts rows per branch, rows whose condition field is empty and rows that went to no branch. An AI step asks the model row by row; what it writes can become a key or a code meaning only after a sample review and another person's confirmation |
| Ontology | Object types (properties, key, the meaning of code columns), relations (how many rows connect, whether the declared cardinality holds), views (such as 有效订单, valid orders), actions (parameters and conditions, writing data only after approval), derived properties (a formula over a row, or a statistic through relations) |
| Confirmation | Proposed → checked by code → confirmed by another builder (with one builder it opens up and the log says so). The data version and anchors are kept at confirmation. A new upload re-checks them; whatever no longer holds goes back to "needs another look", with what reads it, and the cause says whether the data changed, the definition changed, or something upstream did. What one upload moved can be confirmed together on one screen |
| Q&A | Scope is the confirmed types the person may see. A question that names an unconfirmed or stale definition is refused before the model is asked, with the reason. The model sees structure, meanings and the values of columns with few distinct values, never rows, and writes a structured query; code runs it and checks the definitions it used. It can leave a meaning out ("not cancelled") and take the top or bottom N. Each answer is kept with its definitions, who confirmed them and the data versions |
| Use | Object explorer, boards, MCP tools for agents (personal token, read-only by default), the relation graph and lineage graph (from data sources, uploads and pipelines to datasets, then types and answers; coloured by data changed, definition changed, one step behind, further upstream; sources are shown to builders and admins, without connection details) |

The earlier screen organised around runs is still at `legacy.html`; see [docs/LEGACY_SCREEN.en.md](docs/LEGACY_SCREEN.en.md).

## Quick start

You need Python 3.11+, Node 22+ and a DeepSeek API key. Uploading a PDF also needs `pdftotext` (poppler) installed on this machine.

### Option A: let your AI install it

Paste this into Claude Code or Codex:

```text
Install and run OntoPoc (https://github.com/Longado/ontopoc) on this machine:
1. Read the repository's README.en.md and follow "Quick start".
2. Check python3 --version ≥ 3.11 and node --version ≥ 22; if not, tell me how to install them and stop.
3. Clone the repository, run python3 -m pip install -e '.[sources]' in the repository root ([sources] adds the PostgreSQL and MySQL drivers; if the system Python does not allow a direct install, create a virtual environment first), and run npm ci in landing-page.
4. Ask me for a model key (DeepSeek or OpenRouter) and put it only in this terminal's DEEPSEEK_API_KEY or OPENROUTER_API_KEY; do not write it to any file.
5. From the repository root, first make the admin: PYTHONPATH=src python3 -m ontology_poc_generator.accounts create-admin (I type the name and password myself).
6. Then start the service: PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --origin http://127.0.0.1:5178
7. In another terminal, start the page: cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
8. Open http://127.0.0.1:5178/, sign in to the team app, upload examples/company/demo_company.xlsx, and tell me how many tables the datasets page shows.
```

### Option B: install it yourself

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc
python3 -m pip install -e '.[sources]'   # sources: the PostgreSQL and MySQL drivers; if the system Python does not allow it, first run python3 -m venv .venv && . .venv/bin/activate
(cd landing-page && npm ci)

# first time: make the admin on the machine the service runs on (asks for a name and a password of at least 12 characters)
PYTHONPATH=src python3 -m ontology_poc_generator.accounts create-admin

# terminal 1: the service (port 8767, data in output/ontology-runs/workspace.sqlite; --data-dir for another folder)
export OPENROUTER_API_KEY=your-key          # or DEEPSEEK_API_KEY
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --origin http://127.0.0.1:5178

# terminal 2: the page
cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

`http://127.0.0.1:5178/` is the team app; the earlier screen is at `http://127.0.0.1:5178/legacy.html`. The admin adds other people on the Users (用户) page. Without a key everything else works, and Q&A and modelling say the key is missing. After changing backend code, restart the service; the page says so when it finds the service running old code.

Model: `DEEPSEEK_API_KEY` goes to DeepSeek's own API. With only `OPENROUTER_API_KEY` it goes to OpenRouter, `deepseek/deepseek-v4.1-flash` by default. `EIP_MODEL_API_BASE` and `EIP_MODEL_NAME` name another OpenAI-compatible endpoint and model.

Page code: the team app is in `landing-page/src/app/` and uses only the workspace API `/api/workspace/*`; the earlier screen is in `landing-page/src/legacy/` (entry `legacy.html`; the old landing text is `legacy.html?landing`).

## Use with MCP / Claude

Some features are exposed as 39 MCP tools, and the repository is also a Claude Code plugin. The tools share the local service with the page: start the service first, then connect a client. An outside agent using a personal token (`ONTOPOC_TOKEN`) gets the 5 read-only tools by default: read definitions, ask, run an OntoPoc Query, list unconfirmed items, read a derived property.

### Install as a Claude Code plugin

The repository is itself a Claude Code plugin. Once installed you can build and confirm ontologies from Claude Code; modelling, checking and the confirmation record still happen in the local OntoPoc service, so start it first (see above).

```bash
claude plugin marketplace add Longado/ontopoc
claude plugin install ontopoc@ontopoc
```

In a new session there are two commands: `/ontopoc:ontopoc-build` (upload files and build) and `/ontopoc:ontopoc-review` (confirm item by item). At session start the plugin says one line if the local service is not running. It looks for Python as `ONTOPOC_PYTHON`, then `python3`, then `python`.

### Connect Claude Code or another MCP client

The 39 tools share the same local service as the page and can be called directly from Claude Code and other clients (run this in the repository root). 34 of them work on the earlier screen's runs (building, browsing, questions, confirmation, export) and 5 on the team app: read confirmed definitions, ask, run an OntoPoc Query ([QUERY.md](docs/QUERY.md)), list unconfirmed items, read a derived property. Uploading, writing definitions and confirming in the team app have no MCP tool yet; use the page or HTTP.

```bash
claude mcp add ontopoc -- env ONTOPOC_TOOLSET=all PYTHONPATH=$PWD/src python3 -m ontology_poc_generator.mcp_server
```

The tool list is in [docs/MCP.md](docs/MCP.md).

## The earlier screen organised around runs

The earlier screen organised around one run at a time is still at `legacy.html`. Its overview, screenshots, how it works, a walkthrough and features are in [docs/LEGACY_SCREEN.en.md](docs/LEGACY_SCREEN.en.md).

## Ontology FAQ

### What is ontology engineering?

Here, ontology engineering means turning business objects, how they are identified, and the relations between them into definitions you can check. OntoPoc is trying a concrete path: draft an ontology from a few business tables or one document, let code check the draft against the data, then have a person confirm item by item and save the result.

### How is an ontology different from a knowledge graph?

An ontology first states which objects exist, how they are identified, and which relations are allowed. A knowledge graph usually also contains specific instances and their relations. OntoPoc focuses on the former: drafting and checking definitions, then running checks and Q&A on the data you uploaded this time. It is not a knowledge-graph platform and does not provide a durable instance store or online object query.

### How does this relate to a semantic layer?

A semantic layer often sits on a warehouse or metrics platform and defines business meaning (objects, measures, definitions) for reuse in queries. OntoPoc sits one step earlier: the first time you receive a client's tables or a document, it helps sort objects, identity fields, relations, and the definitions that still need the client's answer. You can export object forms, a pipeline requirements sheet, and Turtle (OWL / SHACL) for later platform or pipeline work. Import into any specific platform has not been tested yet.

### What is an ontology MCP, and how do I use it here?

Here, ontology MCP means calling ontology-related functions through MCP tools. OntoPoc exposes some page features as MCP tools (39 in all, 5 of them for the team app: read definitions, ask, run an OntoPoc Query, list unconfirmed items, read a derived property) for clients such as Claude Code, Claude Desktop, and Cursor. The tools use local stdio and talk to the modelling service already running on this machine. Claude Code can also install the repository as a plugin and use `/ontopoc:ontopoc-build` and `/ontopoc:ontopoc-review`. Setup is under [Use with MCP / Claude](#use-with-mcp--claude); the tool list is in [docs/MCP.md](docs/MCP.md).

### Who is OntoPoc for today?

The team app is meant for a data team: builders make definitions from the data and confirm each other's, viewers ask questions and read boards. The earlier screen is meant for an implementation consultant on a data platform, sorting business objects and relations the first time client data arrives. Nobody outside the author has used either independently yet; the UI has only been used on macOS. See [Known issues](docs/KNOWN_ISSUES.en.md) for current limits.

## Privacy

- Uploaded files and all results stay on this machine, in `output/ontology-runs/`.
- In the team app the model sees the names and types of object types and properties, confirmed code meanings, relations, what derived properties say, and every value of columns with few distinct values (such as city or tier). Key columns and columns an admin marks "don't send values" (不发取值) send no values. No rows are sent.
- Sent to the model by the earlier screen (DeepSeek, or a model on OpenRouter): the modelling purpose; for each table its row count, each column's name, up to 3 example values, the counts code took (values present, distinct values, whether all differ), the columns or column pairs that differ on every row, and likely links (including into the same table); every value of a category-like column; when writing questions, every value of columns with at most 12 distinct values, and any question you type in 智能问答 (Q&A) as written; when you click "起草" (draft) for field descriptions, each field's type and maximum length; when you click "找出可能的对应" (find possible matches), for objects identified by a single field with 2 to 200 values, all identity values and how many rows each appears in; for documents, the text, at most 12 chunks per upload. The upload page shows exactly what will be sent for modelling, column by column.
- Each model call leaves one line in `output/ontology-runs/model_calls.jsonl` (which agent, how long, success or failure), never the content.
- The service accepts requests from this machine only.

## Known issues

See [docs/KNOWN_ISSUES.en.md](docs/KNOWN_ISSUES.en.md).

## Contributing

**Can an ontology be read, corrected and carried forward by the people whose business it describes?**

| Area | Contribution |
|---|---|
| User research | Have a consultant who is not the author use it from upload to exporting the meeting note without help, and record where they get stuck |
| Data quality | Rule discovery has only "required" and "date order"; value ranges, non-negative and others need defining on real data first |
| Platform integration | Test batch import on a specific data platform and add the relation table export |
| Prompts and evaluation | Pick accepted results from local runs as labelled samples, and compare old and new prompts with one command |
| Cross-platform | Run it on Windows or Linux and file what breaks |

Issues and pull requests are welcome. Read the [development guardrails](docs/DEVELOPMENT_GUARDRAILS.md) first.

### Sign-in and accounts

The service requires sign-in and has no default account or password. Creating the admin, roles, tokens, two-person confirmation and running it for a team are in [docs/ACCOUNTS.en.md](docs/ACCOUNTS.en.md).

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q      # backend tests (about 2000; install ".[check,sources]" first, or TTL and some source checks are skipped)
npm --prefix landing-page run test:unit                       # page tests (about 530)
PYTHONPATH=src:. python3 scripts/real_model_check.py --out /tmp/check   # real model against SQL (needs a model key; fails only on a wrong number)
PYTHONPATH=src:. python3 scripts/run_company_ontology.py --file examples/company/demo_company.xlsx --output output/demo-run.json
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --data-dir /tmp/ontopoc-trial   # a trial run in another data directory, leaving your runs alone
PYTHONPATH=src:. python3 scripts/make_demo_company.py         # regenerate the synthetic workbook
```

The design documents are in Chinese:

| Document | About |
|---|---|
| [docs/PRODUCT.md](docs/PRODUCT.md) | Direction and boundaries |
| [docs/PLAYGROUND_INTERNALIZATION.md](docs/PLAYGROUND_INTERNALIZATION.md) | Where the ontology library comes from, the limits of the RDF/XML import, and later rounds |
| [docs/AGENTS.md](docs/AGENTS.md) | The 6 agents' definition cards and the call log |
| [docs/MCP.md](docs/MCP.md) | The MCP tools |
| [docs/PLATFORM_FORM_REFERENCE.md](docs/PLATFORM_FORM_REFERENCE.md) | Data platform object forms, compared |
| [docs/PRD_ITERATION_9.md](docs/PRD_ITERATION_9.md) | The latest iteration plan (round 9, closing the loop); changes in later rounds are described in the merged PRs |
| [docs/DEVELOPMENT_GUARDRAILS.md](docs/DEVELOPMENT_GUARDRAILS.md) | Red lines, and directions waiting for a trigger |

## License

[MIT](LICENSE) © Yutai Lin
