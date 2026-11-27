<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
    <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc" width="360">
  </picture>
</p>

<h1 align="center">OntoPoc</h1>
<p align="center"><strong>The confirmation gate between a team's data and the AI that answers questions about it: agents answer only from definitions a named person confirmed against the current data, otherwise they refuse and say who can confirm.</strong></p>
<p align="center">Ontology tool for teams and MCP / Claude: data → definitions → checks → confirmation → gated answers, boards and agents.</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue" alt="AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/tested%20on-macOS-black" alt="tested on macOS">
  <img src="https://img.shields.io/badge/Python-3.11%2B-green" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Node-22%2B-green" alt="Node 22+">
  <img src="https://img.shields.io/badge/status-Alpha-orange" alt="Alpha">
</p>

<p align="center">
  <a href="README.md">中文</a> ·
  <a href="https://longado.github.io/ontopoc/">Docs</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="docs/pilot/FIRST_DEFINITION.md">Try it</a> ·
  <a href="#for-agents-mcp--claude">MCP / Claude</a> ·
  <a href="#ontology-faq">Ontology FAQ</a> ·
  <a href="#contributing">Contributing</a>
</p>

<p align="center"><sub>Ontology tool for MCP / Claude · Docs: <a href="https://longado.github.io/ontopoc/">longado.github.io/ontopoc</a> · Follow on X: <a href="https://x.com/linyutai120479">@linyutai120479</a></sub></p>

<p align="center">
  <img src="docs/media/ontopoc-hero.gif" alt="OntoPoc: business tables become definitions that wait for a person to confirm them" width="960">
</p>
<p align="center"><sub>Concept illustration · <a href="docs/media/ontopoc-poster.png">Still image</a> · <a href="docs/media/ontopoc-motion.mp4">MP4</a></sub></p>

OntoPoc is an ontology tool for a team's own data. The team writes down what its tables mean: object types and their keys, what each code in a column means, relations, views such as "valid orders", derived properties. That is the team's ontology, the part of a semantic layer that says how a number is worked out. Code checks each definition against every row, and a second, named person confirms it on a given version of the data. Q&A, boards and AI agents over MCP then answer only from what was confirmed. When the data or a definition changes, what rests on it goes back for another look, and questions that use it are refused, naming the definition and who can confirm it. It is not a knowledge-graph platform or a data platform; it is still in development and nobody but the author uses it yet.

## How it refuses

Three outcomes, all on the bundled sample data (150 orders, status codes 0 to 5), which the [live demo](https://35-229-236-140.sslip.io/) (temporary address) also serves to read-only guests:

| You ask | OntoPoc says | Why |
|---|---|---|
| "Total amount of valid orders?" | **119,810**, with the line it rests on: the view *Valid orders* (paid, shipped, delivered), who confirmed it, on orders v1 | Every definition the answer uses is confirmed |
| A question that names a definition nobody has confirmed yet | Held back before the model is asked, naming the definition and who can confirm it | Proposed is not confirmed. A person who may see the definition gets its name and who can confirm it; a viewer, who only reads confirmed definitions, is not told the names of definitions never confirmed, and for a confirmed one waiting for another look is told only that the answer waits for a confirmation |
| The same question after `orders_update.csv` arrives (new code 6, nobody gave it a meaning) | Refused: *Valid orders* needs another look; a board shows that it waits and the last number | The data changed under the confirmation |

An answer on every row also shows each confirmed view's own number beside it, and an answer on one confirmed view also shows the number for every row. Which rows the main number covers is decided as before.

**A figure a join repeated is not worked out.** When a pipeline joins orders to their lines, every line row carries its order's amount; adding that amount up on an "order line" type counts an order once per line. A run looks at structure, not values: as soon as one row of a join's side stands on more than one output row, every column from that side is marked ("Counts repeated rows"), even when a total happens to come out right, and whatever its type, so an amount stored as text does not escape (the note on pages is shown on number columns only). The mark follows the column through the later steps of the same pipeline (cast, calculated column, fill, filter, union, an AI step) and into a pipeline that reads it. It comes off by measurement, not by the kind of step: while the join's hidden row columns are there, the output is measured again, and the mark goes only when no row of that side stands on more than one row; an aggregate loses them, and then only a grouping by exactly that side's join key (nothing added), unique on that side, with max, min or count distinct takes it off. Only the current version of a dataset counts. From then on Q&A, OntoPoc Query, MCP, derived properties, boards and charts, checked numbers and questions we need refuse a sum, an average, a median, a percentile or a distribution of such a column (group totals included), and point to the way out: work it out on the type that has one row per thing (one row per order, say). A person who may open the pipeline is told which one; anyone else gets the same sentence without the name, and a person limited to some rows gets the same sentence too. It refuses; it never de-duplicates for you. A count of objects, a count distinct, a max or a min still answer (in Q&A and charts: OntoPoc Query has count but no max or min); confirming such a type is not blocked, and the confirm screen carries the note.

**Upgrading from an earlier version.** A pipeline output with a join written by an earlier version was never measured for repeats. After the upgrade, on such a version every aggregate of any column but a count, a count distinct, a max and a min is refused, with a sentence that says which pipeline to run again (named only to those who may open pipelines); its checked numbers show as refused and its questions we need go back to "needs another look". Run each pipeline that has a join once after upgrading; a pipeline without a join over uploaded data is not affected. The demo and the sample data have no pipelines: their boards and questions answer as before.

On the live demo a guest gets the first answer and one refusal of the third kind: the type Customer was confirmed once and now waits for a second look, so a question that names it is refused before the model is asked, and the guest is told only that the answer waits for a confirmation. A question names it by its name, Customer (any case, singular or plural, as a whole word, for example "Valid order amount by Customer city"), or by its other name 客户 ("按客户城市看有效订单金额").

**Other names.** An object type, a property, a code meaning, a view or a derived property can carry up to five other names, for example the Chinese name of an English one (the demo's view *Valid orders* is also called 有效订单). A question that uses one is read as if it used the name: it is refused before the model where the name would be, and a question that says a confirmed view's other name is refused when the model does not read that view, as with its name. The model is told the other names of the confirmed definitions it is told about. Nothing else changes: which rows an answer covers is still the model's reading, checked by code. A definition's own name is always heard; an other name found only inside a longer name of another definition is not (on the demo, Customer's other name 客户 inside the property's 客户号). Other names are part of the definition, so the person who confirms it confirms them; an other name may not equal a name of a definition of another kind; two definitions in one scope may not share one, a name in Chinese may not contain another in its scope, and a view's name may not be inside an object type's (the other way round is fine: 订单 inside 有效订单).

The sum of the amount column is 162,960. It is arithmetically right and it is not revenue: cancelled and refunded orders still carry an amount. That gap is what the gate is for.

## How a definition gets confirmed

1. **Put it forward.** A builder writes the definition, asks the model to suggest one from the datasets, or imports the tests of a dbt `manifest.json` (a suggestion or an import is only a proposal).
2. **Code checks it on every row.** Keys are unique and filled, relations connect (and say how many rows do not), every code has a meaning, and each value rule on a type's properties holds (not empty; greater than, at least, less than, at most or between numbers; one of the codes with a meaning; one date not before another), with the rows that break it counted and up to 20 named by key. A rule the data breaks can be proposed, but the type cannot be confirmed until no row breaks it. A key check over no rows does not count as passed (relation checks do not yet make that distinction).
3. **A second builder confirms it.** Never the one who proposed it, and never anyone who changed it since it was last confirmed, whether they changed its name, its description or its other names. Any change to a confirmed definition, by anyone (its last confirmer included), sends it back to wait for a second person; putting it back exactly as it was last confirmed confirms it again. The cost: when two builders have both changed a definition, a third person has to confirm it, or one of them puts it back; whoever is held is told who changed it and the ways out. A pipeline's new description counts as a change of the pipeline, as a new step does: it waits for a second person, its scheduled runs stop, and the definitions on what it writes go back for another look until they are confirmed again. With one builder the rule opens up and the log says so. The confirmation keeps who, when and which data version.
4. **It is used.** Q&A, boards and agents see it, each number with the line it rests on.
5. **It goes back when things move.** A new upload or pull re-checks it; if it no longer holds, it and what reads it go to "needs another look", with the cause (data changed, definition changed, upstream). The review queue brings it back to step 3.

Walk through it in 40 minutes with two people: [docs/pilot/FIRST_DEFINITION.md](docs/pilot/FIRST_DEFINITION.md).

## Quick start

You need Python 3.11+ and Node 22+. A model key (DeepSeek or OpenRouter) is optional: without one, Q&A and suggestions say the key is missing and everything else works.

### One command (Mac / Linux)

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc && ./scripts/ontopoc-start.sh
```

It installs the dependencies, builds the page, makes the first admin on the first run, and serves the page and the API on one address, `http://127.0.0.1:8767/`; data lives in `~/.ontopoc/data` (`ONTOPOC_DATA_DIR`, `ONTOPOC_PORT` to change). For a team behind HTTPS see [docs/DEPLOY.md](docs/DEPLOY.md). To try it with your team for two weeks, use the [pilot kit](docs/pilot/README.md).

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
8. Open http://127.0.0.1:5178/, sign in, upload docs/pilot/sample/orders.csv and customers.csv, and tell me how many rows each dataset shows.
```

### Option B: install it yourself

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc
python3 -m pip install -e '.[sources]'   # sources: the PostgreSQL and MySQL drivers; if the system Python does not allow it, first run python3 -m venv .venv && . .venv/bin/activate
(cd landing-page && npm ci)

# first time: make the admin on the machine the service runs on (asks for a name and a password of at least 12 characters)
PYTHONPATH=src python3 -m ontology_poc_generator.accounts create-admin

# terminal 1: the service (port 8767, data in output/ontology-runs/workspace.sqlite; --data-dir for another folder)
export OPENROUTER_API_KEY=your-key          # or DEEPSEEK_API_KEY; optional
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --origin http://127.0.0.1:5178

# terminal 2: the page
cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

The dev server listens on this machine only. To open it to other machines (for example as `terminal.local`), start it with `ONTOPOC_DEV_HOST=0.0.0.0`; anyone on the network can then reach it.

The admin adds other people on the Users page. After changing backend code, restart the service; the page says so when it finds the service running old code.

Model: `DEEPSEEK_API_KEY` goes to DeepSeek's own API. With only `OPENROUTER_API_KEY` it goes to OpenRouter, `deepseek/deepseek-v4.1-flash` by default. `EIP_MODEL_API_BASE` and `EIP_MODEL_NAME` name another OpenAI-compatible endpoint and model.

## For agents (MCP / Claude)

An outside agent connects as a named person, with a personal token an admin makes on the AI tool access page. With `ONTOPOC_TOOLSET=read` set, as in every command below, or with a read-only token (what that page offers first), it gets only six read-only MCP tools, worked out with that person's permissions:

| Tool | What it does |
|---|---|
| `describe_definitions` | The confirmed object types, properties, code meanings, relations, views and derived properties, with the refusal rules |
| `ontopoc_query` | Work out a number straight from an ontology query ([QUERY.md](docs/QUERY.md)): no model |
| `ask` | Ask in one sentence when a query cannot be written; the model writes the query, code runs it |
| `list_unconfirmed` | What cannot be used yet, and why |
| `read_derived_property` | The value of a confirmed derived property |
| `definition_standing` | Whether each definition is confirmed now, by whom and on which data version; for one that is not, why and who can confirm it. The same is at `GET /api/workspace/agent/standing`, with a CSV download |

What it refuses: anything that rests on a definition that is not confirmed, or needs another look, or that the token's person may not see. The refusal is passed on as it is, with the reason; no guessed answer. These six tools cannot upload, write definitions or confirm. A token with the scope "all" (the default for a token a person makes on their own account page) used without `ONTOPOC_TOOLSET=read` also exposes the earlier screen's 34 run tools, which can upload files, build and confirm there; so set it. Start the service first, then, from the repository root:

```bash
claude mcp add ontopoc -- env ONTOPOC_TOKEN=<your token> ONTOPOC_TOOLSET=read PYTHONPATH=$PWD/src python3 -m ontology_poc_generator.mcp_server
```

The AI tool access page shows a JSON block for Claude Desktop, Cursor and other MCP clients, with the service address filled in; add `"ONTOPOC_TOOLSET": "read"` to its `env`. The full list is in [docs/MCP.md](docs/MCP.md). The page also offers a skill pack (zip): a snapshot of the confirmed definitions that does not refuse when the data changes later, so prefer MCP.

**Claude Code plugin.** The repository is also a Claude Code plugin (`claude plugin marketplace add Longado/ontopoc`, then `claude plugin install ontopoc@ontopoc`). Its two commands, `/ontopoc:ontopoc-build` and `/ontopoc:ontopoc-review`, still work on the earlier run-based screen, not on the team app's gate; see [docs/LEGACY_SCREEN.en.md](docs/LEGACY_SCREEN.en.md).

## What is in it, and what it does not do

| Part | What it does |
|---|---|
| Accounts and permissions | Local accounts with three roles (admin, builder, viewer) and server-side sessions. A viewer reads confirmed definitions only. An admin can limit an object type to named people, limit rows by rule (allow-lists only), and hide a column; a builder can keep a column's values from the model |
| Data | Upload CSV or Excel, update by key or overwrite, a new version each time, with the rows counted on the way in. Read-only PostgreSQL and MySQL: a pull **copies** the table into a new version, at most 500,000 rows and about 200 MB per pull; a larger table is refused, not cut short. Only PostgreSQL and MySQL; checking in place in your database is not built. Schedules pull or run pipelines hourly, daily, weekly |
| Definitions | Object types (key, properties, what code columns mean, value rules on the properties: at most 20 per type, each on one property of that type), relations (how many rows connect, whether the declared cardinality holds), views, derived properties (a formula over a row, or a statistic through relations); up to five other names on each type, property, meaning, view and derived property |
| Confirmation | Proposed → checked by code → confirmed by another builder, with the data version and anchors kept. When the data or a definition changes, what no longer holds goes back to "needs another look", and whoever can confirm it, and whoever confirmed it last, gets one notice in Notifications. One exception for relations: one confirmed with every row connected and no repeated key stays confirmed while that is still true, even when the row counts changed. What one upload moved can be confirmed together on one screen |
| Answers | Q&A: a question that names an unconfirmed or stale definition, by its name or an other name, is refused before the model is asked. The model sees structure, meanings and the values of columns with few distinct values, never rows, and writes a structured query; code runs it and checks the definitions it used. Besides a number, a question can ask which objects (a list of the objects that count would count, at most 50 a page, with the asker's own total) or for one object by its key (a key the asker may not read is answered as a key nobody has); a date can be compared with today; a view can use a confirmed per-row derived property. The rows go to the person, never to the model, and are not kept with a saved answer. A list never takes away a number: written beside a sum, a share, a grouping or a ranking it is let be and the number is answered as before; beside a plain count, the count stays first and the rows come with it. A lookup is a condition: beside a number it is refused, never dropped. A lookup in a view the question names looks only in that view. These answers are on (`ROW_ANSWERS` in `workspace_questions.py`); switched off, every answer is what it was before them. OntoPoc Query works these out with no model. Boards answer through the same gate, with numbers only |
| Questions we need | A list of up to 30 questions the team needs answered, each with what it should give (a number, or that it must be refused), proposed by one builder and confirmed by another, signed in, while two-person confirmation is on (with it off a person may confirm their own, and the log says so). A builder or admin whom no type list, column rule or row rule limits runs it: each question is asked 1 to 5 times through the same gate as Q&A and comes back as passes, differs, refused by the gate (with the definitions that block it and who can confirm them), no answer (a reply that could not be read, or no query), no expectation yet (every answer is shown, to adopt one), needs another look (what the expected answer read has moved since) or not asked. Runs have their own budget, at most 300 model calls in any 24 hours, stated before each run and charged as each call goes out; they do not use a person's questions an hour. A run goes on in the service after it starts and the page follows it. Builders and admins only |
| Around it | Light pipelines (filter, join, group, dedupe, calculated columns, union, split, extract a part), the lineage and relation graphs (coloured by why something went back), an object explorer, English and Chinese pages |

**Extract a part.** A pipeline's transform step can split a text column on a separator and put one part into a new column: the setting "door_lock=3" split on "=", part 1, gives the variable name "door_lock", and a relation from the new column to a variables type then says, in its check, how many rows did not connect. The separator is 1 to 10 characters, found exactly as written and never read as a pattern (as with replace text: a pattern a person writes never runs); the part is 1 to 100, or the last. A row without the separator gets an empty value, never a guess, and so does a row with fewer parts than asked. The trial run, the preview and the run each say how many (for example: 37 of 100 rows had no "="), and the step editor lists the first 10 of those rows. The new column is text, carries the marks of the column it came from (not sent to the model, written by the model, repeated by a join) and says which column and separator it came from; it is not the source column itself, so that column's confirmed code meanings do not pass to it. Limits: text columns only; one part per operator (add one operator per part); no trimming (follow it with Clean text when needed); once written to a dataset, the dataset page records which pipeline wrote the column, not which column it came from.

It does not do heavy orchestration, large data, live queries against your database, or a wide choice of charts. Actions (approved writes to data) and the AI steps inside pipelines are still there but off the main path. The earlier run-based screen is at `legacy.html` (last line below).

## Privacy

- Uploaded files, pulled tables and all results stay on the machine running the service.
- The model sees the names and types of object types and properties, confirmed code meanings, relations, what derived properties say, and every value of columns with few distinct values (such as city or tier). Key columns and columns a builder marks "don't send values" send no values. No rows are sent.
- Each model call leaves one line in `model_calls.jsonl` (which agent, how long, success or failure), never the content. A call made by a run of Questions we need is marked as that run's.
- What the earlier screen sends to the model is in [docs/LEGACY_SCREEN.en.md](docs/LEGACY_SCREEN.en.md#what-the-model-sees).

## Known issues

See [docs/KNOWN_ISSUES.en.md](docs/KNOWN_ISSUES.en.md).

## Ontology FAQ

### What is ontology engineering here?

Writing checkable definitions for business objects: how each is identified, what its codes mean, which rows count (a view) and which relations hold. In OntoPoc a person or a model puts a definition forward, code checks it against the data, and a different person confirms it.

### How is an ontology different from a knowledge graph?

An ontology first states which objects exist, how they are identified, and which relations are allowed. A knowledge graph usually also contains the specific instances and their links. OntoPoc keeps to the former, on data copied into its own workspace; it is not a knowledge-graph platform and does not provide a durable instance store.

### How is this different from generating an ontology automatically?

Recent work has a language model do most of the building of an ontology or a graph from text: AutoOntic ([arXiv 2611.15467](https://arxiv.org/abs/2611.15467)) induces types, a hierarchy and relation constraints, and Causals ([arXiv 2611.16267](https://arxiv.org/abs/2611.16267)) is a graph built from news. Both say what they leave unmeasured: AutoOntic's evaluation "does not directly measure extraction precision", and the Causals release "has no representative estimate of semantic accuracy". OntoPoc works on the step after drafting, and mainly on tables: code checks each definition against the data, a named person confirms it, and it goes back for another look when the data changes. A model may draft a definition, but Q&A and agents do not use it before those checks and a confirmation; until then a board shows a number that rests on it only to builders and admins, in grey with the reason, and not to viewers.

### How does this relate to a semantic layer?

Your metrics may already be defined in a semantic layer on a warehouse. Who signed them? Who notices when the data changes underneath? OntoPoc is about that part: each definition carries the person who confirmed it and the data version, goes back for another look when the data moves, and the AI refuses to use it until someone confirms it again. It keeps its own copy of the data. If you use dbt, upload `manifest.json` on the object types page: OntoPoc reads its model tests (unique, not_null, relationships, accepted_values) and proposes object types and relations, at most 50 per import and shown as a preview before anything is written; another builder still confirms each against the data. It does not read composite keys, dbt constraints, metrics, the semantic layer or dbt Cloud, it does not follow later changes to the manifest, and the import confirms nothing. It does not export to a specific semantic layer yet.

### Does OntoPoc use OWL or RDF?

Not inside. The team app keeps its own object model and does not run an OWL reasoner: OWL reads data under an open world, so two objects with the same key become one object, where OntoPoc refuses the repeated key. Anyone signed in, viewers included, can download the confirmed definitions they may see as two Turtle files from `GET /api/workspace/agent/schema` (builders and admins also find a link on the AI tool access page): OWL for object types, keys, properties and relations, SKOS for code meanings, and SHACL shapes for the key, code and cardinality checks. Views and derived properties are in them as text, not as OWL axioms, and no row of data is. rdflib and pyshacl read them in OntoPoc's tests; ROBOT with the HermiT reasoner was run once, by hand, on a sample, and no OWL profile is claimed for a downloaded file. What maps where, and what does not fit, is in [docs/STANDARDS.en.md](docs/STANDARDS.en.md). The earlier screen has a separate Turtle export of its own.

### What is an ontology MCP, and how do I use it here?

Here, ontology MCP means an agent reading a team's confirmed ontology through MCP tools. With `ONTOPOC_TOOLSET=read` or a read-only personal token, OntoPoc's MCP server gives an agent six read-only tools (read definitions, ask, run an OntoPoc Query, list unconfirmed items, read a derived property, see whether each definition is confirmed now) for clients such as Claude Code, Claude Desktop and Cursor, over local stdio. Setup is under [For agents](#for-agents-mcp--claude); the list is in [docs/MCP.md](docs/MCP.md).

### Who is OntoPoc for today?

A small data team (three to eight people, ops, finance, data) that wants an AI to answer questions about its own tables, and wants it to refuse rather than answer quietly wrong. Builders write definitions and confirm each other's; viewers ask questions and read boards. Nobody outside the author has used it independently yet; the page has only been used on macOS.

## Contributing

**Does a team's AI refuse at the right moments, and only then?**

| Area | Contribution |
|---|---|
| Pilot | Run the [pilot kit](docs/pilot/README.md) with a small team and send the question log: right, wrong, refused, and whether each refusal was for a good reason |
| Checks | Find a definition that passes the checks and is still wrong on real-looking data, and file it with the data |
| Agents | Connect an MCP client with a read-only token and report where the refusal rules were unclear to it |
| Prompts and evaluation | Pick accepted answers as labelled samples and compare old and new prompts with one command |
| Cross-platform | Run it on Windows or Linux and file what breaks |

Issues and pull requests are welcome. Read the [development guardrails](docs/DEVELOPMENT_GUARDRAILS.md) first. Sign-in, roles, tokens and two-person confirmation are in [docs/ACCOUNTS.en.md](docs/ACCOUNTS.en.md); the service has no default account or password.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q      # backend tests (2,684 on 2026-11-27; install ".[check,sources]" first, or the Turtle, OWL and SHACL tests and some source checks are skipped)
npm --prefix landing-page run test:unit                       # page tests (833 on 2026-11-27)
PYTHONPATH=src:. python3 scripts/real_model_check.py --out /tmp/check   # real model against SQL (needs a model key; fails only on a wrong number)
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --data-dir /tmp/ontopoc-trial   # a trial run in another data directory
```

Page code: the team app is in `landing-page/src/app/` and uses only `/api/workspace/*`; the earlier screen is in `landing-page/src/legacy/`. The design documents are in Chinese:

| Document | About |
|---|---|
| [docs/PRODUCT.md](docs/PRODUCT.md) | What OntoPoc is for, and what it keeps and leaves out |
| [docs/QUERY.md](docs/QUERY.md) | OntoPoc Query |
| [docs/MCP.md](docs/MCP.md) | The MCP tools |
| [docs/AGENTS.md](docs/AGENTS.md) | Every model call: its definition card and the call log |
| [docs/DEVELOPMENT_GUARDRAILS.md](docs/DEVELOPMENT_GUARDRAILS.md) | Red lines, and directions waiting for a trigger |
| [docs/STANDARDS.en.md](docs/STANDARDS.en.md) | OWL, SHACL and SKOS: what the download of confirmed definitions holds, and what does not fit (in English and Chinese) |

## License

[AGPL-3.0](LICENSE) © Yutai Lin. v0.2.0 and earlier stay under MIT; for a commercial license, see [NOTICE.md](NOTICE.md).

---

The earlier screen, organised around one modelling run at a time (drafting an ontology from a few tables or a document, the caliber card, object forms and Turtle export; a PDF upload there also needs `pdftotext` from poppler), is still at `legacy.html`: [docs/LEGACY_SCREEN.en.md](docs/LEGACY_SCREEN.en.md).

<!-- mcp-name: io.github.Longado/ontopoc -->
