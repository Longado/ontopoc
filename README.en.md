<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
    <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc" width="360">
  </picture>
</p>

<h1 align="center">OntoPoc</h1>
<p align="center"><strong>A direction still in development: draft an ontology from business data, check it against the data with code, confirm it item by item.</strong></p>
<p align="center">The imagined user is a data platform implementation consultant mapping the business objects and relationships in a client's data for the first time.</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue" alt="MIT"></a>
  <img src="https://img.shields.io/badge/tested%20on-macOS-black" alt="tested on macOS">
  <img src="https://img.shields.io/badge/Python-3.11%2B-green" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Node-22%2B-green" alt="Node 22+">
  <img src="https://img.shields.io/badge/status-Alpha-orange" alt="Alpha">
</p>

<p align="center">
  <a href="README.md">中文</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#try-it">Try it</a> ·
  <a href="#use-with-mcp--claude">MCP / Claude</a> ·
  <a href="#ontology-faq">Ontology FAQ</a> ·
  <a href="#contributing">Contributing</a>
</p>

<p align="center"><sub>Ontology engineering · Follow on X: <a href="https://x.com/linyutai120479">@linyutai120479</a></sub></p>

<p align="center">
  <img src="docs/media/ontopoc-hero.gif" alt="OntoPoc companion connects business tables into a draft ontology for review" width="960">
</p>
<p align="center"><sub>Concept illustration · <a href="docs/media/ontopoc-poster.png">Still image</a> · <a href="docs/media/ontopoc-motion.mp4">MP4</a></sub></p>

OntoPoc is a direction still in development, not a finished product. What it tries: draft an ontology from a few business tables or a document, have code check the draft against the data, and have a person confirm it item by item and keep the result. Nobody but the author uses it now, and it has not been compared with doing the same thing directly in a general-purpose coding assistant (for example Claude Code with pandas or DuckDB).

The workbench interface is in Chinese only; the landing page has an English version. This page describes the workbench in English and gives the Chinese label in parentheses the first time it names a screen, tab or button.

## Overview

Upload a few business tables (Excel, CSV) or a process document, and OntoPoc drafts an ontology: which objects the business has, what tells each one apart, and how they relate. To draft, code first counts over every row (how many distinct values each column has, which columns differ on every row, which columns have values found in another column); the model drafts from the field names, up to 3 example values and these counts. Code then checks the draft for 14 kinds of error, for example whether a field exists, whether an identity field has values, whether a relation connects any rows, and sends it back if it fails, up to 3 rounds. It runs data quality checks and answers business questions from the data. A document can also be read as an organisation: units, roles, people and work steps, and who belongs to, works with or hands over to whom, each item with a quote from the text. You judge each part right or wrong; your judgement is kept, and the next upload of the same file, or a new version of it, is compared against it.

Some things the data cannot settle and only the client can. Code gathers them into one list, Items to confirm (要确认的事), each with its basis and a sentence you can ask the client directly. Each table also gets a definition card (口径卡) that says what one row is, what time a date refers to, and whether a number can be added up. You record the client's answers in the meeting, and the questions are then computed with those answers.

Every uploaded table is also stored in a local `workspace.sqlite`: one table per version, the row count checked on every import (rows in the file = rows stored + blank and title rows dropped), each check kept with its query and the rows it looked at, and each confirmation kept as a state with who confirmed it and on what. A definition a person confirmed (what status code 2 means, which row to keep for a repeated number, what counts as a valid order) becomes a named view that questions, pipelines and answer checks all read from one place, instead of relying on the model to remember it.

The result can be exported in the shape of a data platform's object form; as a pipeline requirements sheet (编排需求单) for whoever builds the data pipeline, and a one-page meeting note; or as W3C Turtle (OWL and SHACL). Some features are also MCP tools other agents can call (the newer definition and join features have none yet).

> **Early version.** It has been tried on public and synthetic data only (US federal procurement, Chicago city contracts, Northwind, BART transit, the Taiwan company registry, CMS hospitals and more). Nobody but the author has yet used it end to end on their own, and it has not been compared with doing the same thing directly in a general-purpose coding assistant. The page has been used on macOS only. Batch import has not been tested on any data platform. A single file, or several tables uploaded together, may total at most 10 MB; the model is reached only through DeepSeek's hosted API, with no local-model option. See [Known issues](#known-issues).

## Screenshots

<p align="center"><img src="docs/images/readme-confirm.png" alt="Items to confirm: what code gathered for the client" width="880"></p>
<p align="center"><sub>Items to confirm (要确认的事): 8 items on the sample workbook, each with its basis and a sentence you can ask the client (the screenshot shows the earlier list; it is now one card at a time).</sub></p>

<p align="center"><img src="docs/images/readme-card.png" alt="Definition cards: one per table" width="880"></p>
<p align="center"><sub>Definition cards (口径卡): code has already worked out which columns tell each table's rows apart; what one row is and whether a number can be added up are left for the client.</sub></p>

<p align="center"><img src="docs/images/readme-objects.png" alt="Ontology: one card per business object" width="880"></p>
<p align="center"><sub>Ontology (本体管理): the 4 business objects built from the sample workbook; on the left, item-by-item confirmation (逐项确认), stability (稳定性), last-run comparison (和上次比) and build record (建模记录).</sub></p>

<p align="center"><img src="docs/images/readme-instances.png" alt="Instance graph: one customer opened out to its orders and products" width="880"></p>
<p align="center"><sub>Instance graph (实例图谱): customer KH001 opened out to its orders, and one order to its product; on the right, the selected order's raw fields.</sub></p>

<p align="center"><img src="docs/images/readme-ask.png" alt="Questions: the answer is computed by code on the data" width="880"></p>
<p align="center"><sub>Questions (智能问答): the model writes the question as a query; code computes the numbers on the uploaded data and says how many values it read.</sub></p>

<p align="center"><img src="docs/images/readme-check.png" alt="Data check: 7 checks" width="880"></p>
<p align="center"><sub>Data check (数据体检): on this sample, 5 of 7 checks pass; the 2 that fail are problems planted in the sample, with the objects involved listed below.</sub></p>

All screenshots come from the synthetic sample in the repository, `examples/company/demo_company.xlsx`, rendered off-screen by a headless browser.

## How it works

| Action | What the system does |
|---|---|
| Open the ontology library (本体库) in the left sidebar | Search and browse 12 Playground reference ontologies by domain, and see objects, properties and relations on a graph. You can also import `.rdf/.owl` files in RDF/XML format. This is for reading definitions only: import calls no model, and you must pick the file again after a refresh |
| Upload tables and write the question you want answered | Code first counts every row: how many distinct values each column has, which columns differ on every row, which columns point into another table. The model sees each column's name, up to 3 example values and these counts, and proposes objects, identity fields and relations; code checks 14 kinds of error and sends it back to redo, up to 3 rounds |
| Wait for the build | Builds the same file 3 times at once and marks where the 3 disagree, for you to decide; only objects and relations are compared, not properties; if your purpose asks a question, it is answered from the data too, ready to keep as an acceptance question |
| Open Items to confirm (要确认的事) | Code gathers what to confirm with the client from the data, the questions and the confirmation record, for example rows whose relations do not connect, objects with the same name but different numbers, and filters the model added by itself in a question. Each item has its basis and a sentence you can ask the client directly. Items come as a stack of cards: the basis, up to 3 example rows from the uploaded table and the check result, a progress line (items left, items decided), keys 1 to 4 to reply (confirm, wrong, not applicable, known exception with its reason, plus the item's own choices) and J / K to move; an item with choices of its own can also be answered in words alone; each reply keeps its own draft; the "left" count leaves out the card to fill in and the objects to judge, which can only be done elsewhere; an answer under 已定 can be taken back and changed with its words in the form, and so can the meanings of a code column, "not a code" and a repeat rule; once a newer version exists, answers and take-backs on the older one are refused. Each reply records who gave it and whether it was decided one by one or in bulk; "not applicable" and "known exception" are not asked again on the next upload unless the data they rest on changes: for a code meaning its values and their share of the rows, for a repeated number the numbers, for unmatched or mismatching rows their share, for the rest that can be counted (conflicting values, groups sharing a name, relations that did not appear often enough, questions that cannot be answered) whether the count has doubled or halved (by at least 5); for what has nothing to count (a model-reported data gap about one column, a column with no table to work it out from) the decision holds until the person takes it back. Only the one-click approval can record "bulk". Only what code can verify completely is listed to approve together: a relation whose two objects are judged right, whose every row connects, whose target table has no repeated numbers, and whose direction is either declared and holds in the data or undeclared but computed one-to-one or many-to-one (the list says which). After you have looked, approving records a bulk confirmation for those items only; what others signed and their versions stay as they were. The service works the list out again inside the write transaction and approves nothing if it changed. A code meaning is a person's reading of the data, which the data cannot prove, so it is never in the list and is confirmed one by one. Approved relations show under 已定 with who approved and "bulk". Columns whose name does not match their arithmetic are here too: a column called 交付天数P50 is worked out again from the rows in another table, and if it is really the mean, it becomes an item (rename it or keep it). Confirmed code meanings, repeated-number rules, named views and relations remember the data they were confirmed on; when a later upload moves it (say the status codes shift), the confirmation is marked "needs another look" (需要再看一眼) and is not used as confirmed until a person confirms it again |
| Open Data (数据接入) | Each table is checked for row count and key on import (empty numbers, repeated numbers), and the rows dropped are listed with the reason. Code finds columns that look like codes (status 1/2/3), each value with its row count and evidence, and you write what it means. A repeated number in the table that describes an object becomes an item to confirm: keep every row, keep the latest by a column, or call it a data error. Confirmed definitions generate named views (such as "valid orders" or "latest snapshot") listed with their SQL and row count; a definition that no longer holds is marked unavailable with the reason. Every relation is checked on the stored tables: how many rows connect, which keys do not (3 orders name KH099, which the customer table lacks), whether the described end repeats a key, and whether the declared cardinality holds |
| Join two tables on Data (数据接入) | Pick two tables (or views) and the join columns. Every node shows its rows in and out; when the join makes more rows than the left table, it names the keys that repeat on the right and the sums that would be counted twice. In the synthetic test tables, 160 orders left-joined to tickets become 169 rows |
| Open Definition cards (口径卡) | One per table: what one row is, what time a date column refers to, whether a numeric column can be added up. Code fills in what it can work out; only the cells the client can answer are left for the meeting. The answers you fill in are used when questions are computed, and are written into the pipeline requirements sheet |
| Open the data check (数据体检) | Code runs 7 checks on the data, e.g. whether one number carries conflicting details, whether every uploaded table is used. The relation check only requires each relation to connect at least one row; the page states how many rows connect |
| Ask a question (智能问答) | The model writes a structured query and code computes the answer on the data; each answer says "理解为…" (read as…): which confirmed definition the model used for the question, including its direction ("cancelled", "not cancelled"), and code checks that against the query that actually ran. One that is undeclared, unused or whose name matches nothing is refused with how it was read; when it cannot, it says whether the ontology lacks something, the data lacks it, or the question is beyond the query. An amount that needs a formula (unit price × quantity × (1 − discount)) is proposed by the model, tried by code on every row, and once you confirm it the question is recomputed and answered. If an answer carries a filter the model added by itself, the filter is listed separately and you can drop it and recompute. The model can also write a round of 6 questions on request |
| Look at a relation's binding | Shows the source table and the two end ID columns, e.g. `EmployeeId → ReportsTo`. An endpoint reference connects only to objects that exist and never writes a subordinate's attributes onto the superior. When verification fails, it shows where, why and what to change |
| Judge each part, rename, add what is missing | Saved as this file's reference ontology; the next upload is compared against it and prefilled |
| Fix up to 3 questions as acceptance questions (验收问题) | Every rerun computes them with the same query and tells you which changed |
| Adopt rules found in the data | Every rerun checks them and lists the objects that break them |
| Mark an uploaded file as a new version (新版本) | Last time's confirmations (including what you judged wrong), acceptance questions and rules carry over, with how many of each object came and went. An object the model proposes again after you judged it wrong is flagged on its own |
| Draft the object form | One model call drafts Chinese names, descriptions and display fields; what you edited is never overwritten by a redraft |
| Export the object forms: click "⤓ 表单" at the top right | One CSV per object, in the columns data platforms usually ask for when defining an object |
| Click "⤓ TTL" at the top right | Three Turtle files: `ontology.ttl` describes objects, fields, relations and identity fields in OWL; in `data.ttl` every object is named by its identity values, so the same object in two tables or two versions of a file has one name and merges; `shapes.ttl` writes adopted rules as SHACL for any validator. What you judged wrong is left out |
| Click "⤓ 编排需求单" (pipeline requirements sheet) at the top right | Downloads a zip (one Markdown file and one JSON file) for whoever builds the data pipeline: the requirements that the data check, the items to confirm, the definition card answers, the confirmed metrics and the adopted rules place on data preparation. Each line states its source (found in the data by code, the client's answer, or a person's confirmation). It calls no model and changes no data |
| Click "⤓ 纪要" (meeting note) at the top right, or press ⌘K | Meeting note: one page of Markdown with the items to confirm first, for use in the meeting. ⌘K: search the objects, fields, relations and tables of this run and jump to where they are |

The model only judges; loops and calculations are in code, with model calls chained at most 3 deep and each call tied to a judgement a person has to make. There are 6 agents, each with a definition card in [docs/AGENTS.md](docs/AGENTS.md).

## Try it

Once installed (see [Quick start](#quick-start)), with the synthetic sample in the repository:

| Action | Expected result |
|---|---|
| Without the modelling service, click "Open sample tables" (打开示例数据表) | A bundled result: 4 objects, 3 relations |
| Upload `examples/company/demo_company.xlsx` with "哪些客户的售后问题最多？" (which customers have the most after-sales problems?) as the purpose | After about half a minute to a minute, 4 objects: customer, product, order, after-sales ticket; data check 5 / 7 passed, the 2 that fail being the problems planted in the sample; in Questions (智能问答) › Ask (提问), this question is already answered from the data |
| Open Items to confirm (要确认的事) | In the built-in demo, 8 items to confirm with the client (the count changes with whether the three builds agree), including the planted problems: customer KH012 has different cities on two rows, and the orders refer to KH099, who is not in the customer table |
| In Questions (智能问答), ask "每个客户的订单总金额是多少？" (total order amount per customer) | Totals per customer, highest 241,420, from 160 values read |
| Relations (本体关系) → Instance graph (实例图谱), pick a customer | The customer and its orders as a graph; click an order to open its product |
| Click "⤓ 表单" at the top right | A zip: 4 object-form CSVs and an import note |

## Quick start

You need Python 3.11+, Node 22+ and a DeepSeek API key. Uploading a PDF also needs `pdftotext` (poppler) installed on this machine.

### Option A: let your AI install it

Paste this into Claude Code or Codex:

```text
Install and run OntoPoc (https://github.com/Longado/ontopoc) on this machine:
1. Read the repository's README.en.md and follow "Quick start".
2. Check python3 --version ≥ 3.11 and node --version ≥ 22; if not, tell me how to install them and stop.
3. Clone the repository, run python3 -m pip install -e . in the repository root (this installs openpyxl, which reads Excel; if the system Python does not allow a direct install, create a virtual environment first), and run npm ci in landing-page.
4. Ask me for a DeepSeek API key and put it only in this terminal's DEEPSEEK_API_KEY; do not write it to any file.
5. From the repository root, start the modelling service: PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server
6. In another terminal, start the page: cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
7. Open http://127.0.0.1:5178/legacy.html, upload examples/company/demo_company.xlsx, and tell me how many checks passed in the data check (数据体检).
```

### Option B: install it yourself

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc
python3 -m pip install -e .        # openpyxl, which reads Excel; if the system Python does not allow it, first run python3 -m venv .venv && . .venv/bin/activate
(cd landing-page && npm ci)

# terminal 1: the modelling service (port 8767, results in output/ontology-runs/)
export DEEPSEEK_API_KEY=your-key
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server

# terminal 2: the page
cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

Open `http://127.0.0.1:5178/legacy.html` (the screen organised around runs, which the quick start above uses). The bundled samples open without a key. After changing backend code, restart the modelling service; the page says so when it finds the service running old code.

### Page layout (being rebuilt)

`http://127.0.0.1:5178/` is the new screen, built around one workspace with no runs: the left navigation is grouped as Home, Tasks, Data, Ontology, Apps and Lineage. What works today is Datasets (upload, update by key or overwrite, fields, preview, versions) and Tasks (modelling jobs and upload records); the rest is greyed out. The new screen lives in `landing-page/src/app/`, reads only the workspace API `/api/workspace/*` and never imports the old code. The old screen is all in `landing-page/src/legacy/` (entry `legacy.html`; the old landing text is `legacy.html?landing`), and each old piece goes once the new page that replaces it works. For deployment: what used to be `/landing` is now `legacy.html?landing`; the site configuration has not been changed.

## Use with MCP / Claude

Some features are exposed as 32 MCP tools, and the repository is also a Claude Code plugin (the newer features have no tool yet, see below). The tools share the local modelling service with the page: start the service first, then connect a client.

### Install as a Claude Code plugin

The repository is itself a Claude Code plugin. Once installed you can build and confirm ontologies from Claude Code; modelling, checking and the confirmation record still happen in the local OntoPoc service, so start it first (see above).

```bash
claude plugin marketplace add Longado/ontopoc
claude plugin install ontopoc@ontopoc
```

In a new session there are two commands: `/ontopoc:ontopoc-build` (upload files and build) and `/ontopoc:ontopoc-review` (confirm item by item). At session start the plugin says one line if the local service is not running. It looks for Python as `ONTOPOC_PYTHON`, then `python3`, then `python`.

### Connect Claude Code or another MCP client

The 32 tools cover building, browsing, questions, confirmation and export. They share the same local service as the page and can be called directly from Claude Code and other clients (run this in the repository root). These newer features have no MCP tool yet and can only be used on the page or over HTTP: saving a code meaning, saving a repeated-number rule, named views, the two-table join, and confirming again a definition marked "needs another look". Items to confirm and the answer checks do come through the existing tools, but the changes themselves cannot be made over MCP.

```bash
claude mcp add ontopoc -- env PYTHONPATH=$PWD/src python3 -m ontology_poc_generator.mcp_server
```

The tool list is in [docs/MCP.md](docs/MCP.md).

## Features

| Module | What is in it |
|---|---|
| Ontology library (本体库) | 12 Playground reference ontologies, browsed by domain, with objects and relations on a graph; import `.rdf/.owl` files in RDF/XML format |
| Items to confirm (要确认的事) | What to confirm with the client, a stack of cards with the basis, example rows and check result, answered with keys 1 to 4; the meeting note can be downloaded |
| Definition cards (口径卡) | One per table: what one row is, what time a date column refers to, whether a numeric column can be added up, whether the objects are all there; records who answered and the source |
| Data (数据接入) | Each uploaded table: rows, skipped title lines, each column's type, length and fill; the import row-count and key checks, code meanings, repeated-number rules, named views, two-table join and relation checks; when tables are left unconnected, the column that would connect them |
| Ontology (本体管理) | Object cards (search, filter by your verdict, cards or list); each object's page: overview, fields (the object form), rows (paged, CSV download), confirmation; plus item-by-item confirmation, stability, last-run comparison (和上次比), new version (新版本) and build record |
| Relations (本体关系) | A graph that lays itself out (drag, zoom), the instance graph, the relation list; relations code sees in the data but the ontology lacks are drawn as dashed suggestions |
| Organisation (组织架构) | Choose "组织架构" when uploading a public study: the organisation tree, collaboration and handover (the arrow says what is handed over), a role table, periods, and what the material does not state; export Mermaid organisation charts, one chart per year range |
| Questions (智能问答) | Ask, acceptance questions, the model's questions (filter by answered) |
| Data check (数据体检) | 7 checks, rules (规则), comparison with a reference ontology (对照标准) |

Under "More examples" (更多示例) in the sidebar there are two more example uses of the same method: vehicle recall scope (NHTSA public data, no local service needed), and product and lot matching for food recall event 95876 (openFDA, which needs a separate local recall service started). See [docs/RECALL_EXAMPLE.md](docs/RECALL_EXAMPLE.md). OntoPoc is not affiliated with NHTSA or any carmaker, and its candidates are not defect findings.

## Ontology FAQ

### What is ontology engineering?

Here, ontology engineering means turning business objects, how they are identified, and the relations between them into definitions you can check. OntoPoc is trying a concrete path: draft an ontology from a few business tables or one document, let code check the draft against the data, then have a person confirm item by item and save the result.

### How is an ontology different from a knowledge graph?

An ontology first states which objects exist, how they are identified, and which relations are allowed. A knowledge graph usually also contains specific instances and their relations. OntoPoc focuses on the former: drafting and checking definitions, then running checks and Q&A on the data you uploaded this time. It is not a knowledge-graph platform and does not provide a durable instance store or online object query.

### How does this relate to a semantic layer?

A semantic layer often sits on a warehouse or metrics platform and defines business meaning (objects, measures, definitions) for reuse in queries. OntoPoc sits one step earlier: the first time you receive a client's tables or a document, it helps sort objects, identity fields, relations, and the definitions that still need the client's answer. You can export object forms, a pipeline requirements sheet, and Turtle (OWL / SHACL) for later platform or pipeline work. Import into any specific platform has not been tested yet.

### What is an ontology MCP, and how do I use it here?

Here, ontology MCP means calling ontology-related functions through MCP tools. OntoPoc exposes some page features as MCP tools (32 in all; code meanings, repeated-number rules, named views and the two-table join are not among them yet) for clients such as Claude Code, Claude Desktop, and Cursor. The tools use local stdio and talk to the modelling service already running on this machine. Claude Code can also install the repository as a plugin and use `/ontopoc:ontopoc-build` and `/ontopoc:ontopoc-review`. Setup is under [Use with MCP / Claude](#use-with-mcp--claude); the tool list is in [docs/MCP.md](docs/MCP.md).

### Who is OntoPoc for today?

The intended user is an implementation consultant on a data platform, sorting business objects and relations the first time client data arrives. No one outside the author has completed the full flow independently yet; the UI has only been used on macOS. See [Known issues](#known-issues) for current limits.

## Privacy

- Uploaded files and all results stay on this machine, in `output/ontology-runs/`.
- Sent to the model (DeepSeek): the modelling purpose; for each table its row count, each column's name, up to 3 example values, the counts code took (values present, distinct values, whether all differ), the columns or column pairs that differ on every row, and likely links (including into the same table); every value of a category-like column; when writing questions, every value of columns with at most 12 distinct values, and any question you type in 智能问答 (Q&A) as written; when you click "起草" (draft) for field descriptions, each field's type and maximum length; when you click "找出可能的对应" (find possible matches), for objects identified by a single field with 2 to 200 values, all identity values and how many rows each appears in; for documents, the text, at most 12 chunks per upload. The upload page shows exactly what will be sent for modelling, column by column.
- Each model call leaves one line in `output/ontology-runs/model_calls.jsonl` (which agent, how long, success or failure), never the content.
- The service accepts requests from this machine only.

## Known issues

- **Questions about a relation between objects of the same kind have no direction yet.** Relations such as employee reports-to or parent-child organisation can be modelled, verified and exported; but a question cannot say superior or subordinate, so it states the limit and stops.
- **The model builds differently each time.** Three builds of one file often differ, now mainly in the relations: in one measurement on Northwind on 10-28 (8 kinds of object, 7 relations), 4 relations differed across the 3 builds, nearly all because the same relation ran the other way (order → customer / customer → order). The page marks where they disagree for you to decide.
- **A new version may come with a different way of telling objects apart.** Once, Chicago's contracts went from "number + revision" to number alone; then only counts can be compared, not objects one by one, and the page says so ("识别方式已变更", identification changed).
- **The relation check only requires one connected row.** In the data check, a relation passes as soon as it connects one row, even if the share of rows that connect is very low; the page states how many rows connect, so look at that number.
- **Definitions and joins are narrow.** A code meaning covers a few values of one column; a repeated number has three ways to be read; a join has only input, join and output steps and refuses to run past a row cap; the name-versus-calculation check knows only P50, P90, mean, total, max and min, and needs a same-named source column in another table. All of this has been tried only on synthetic planted tables and public data, never on a real client's data.
- **Answer checks rely on the model declaring honestly.** Code checks that the query that ran matches how the model said it read the question; if the model misstates the reading and the query happens to match, the check cannot see it. The query language can only say "a field equals a value", so "not cancelled" runs only through a named view, and is refused otherwise.
- **"Needs another look" is judged by share of the table.** A value's rows must more than double or fall below half, and by at least 5 rows. These two numbers are chosen, not measured; a shift smaller than that goes unnoticed.
- **Code finds only some missing relations.** Removing each relation in turn on 17 saved runs (public and synthetic data), it found 24 of 33 again; on complete ontologies it has not suggested a false one.
- **Queries cannot yet** filter by a numeric condition, limit to a time range, give two numbers in one question, or say which things tend to appear together. It says so when asked.
- **Batch import is untested.** The exported form columns follow what data platforms usually ask for; import format, key rules and how relations are expressed differ by platform and have not been tested on any, so no relation table is exported.
- **Turtle export is checked only by reading it back with rdflib and pyshacl.** It has not been loaded into Protégé or a graph database.
- **The page has been used on macOS only.** Backend and page unit tests pass on Linux (CI); Windows is untested.

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

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q      # backend tests (1424; install ".[check]" first, or 9 TTL checks are skipped)
npm --prefix landing-page run test:unit                       # page tests (369)
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
| [docs/MCP.md](docs/MCP.md) | The 32 MCP tools |
| [docs/PLATFORM_FORM_REFERENCE.md](docs/PLATFORM_FORM_REFERENCE.md) | Data platform object forms, compared |
| [docs/PRD_ITERATION_9.md](docs/PRD_ITERATION_9.md) | The latest iteration plan (round 9, closing the loop); changes in later rounds are described in the merged PRs |
| [docs/DEVELOPMENT_GUARDRAILS.md](docs/DEVELOPMENT_GUARDRAILS.md) | Red lines, and directions waiting for a trigger |

## License

[MIT](LICENSE) © Yutai Lin
