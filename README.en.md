<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
    <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc" width="360">
  </picture>
</p>

<h1 align="center">OntoPoc</h1>
<p align="center"><strong>Generates a draft ontology from business data, with verifiable evidence for every element.</strong></p>
<p align="center">For data platform implementation consultants mapping the business objects and relationships in a client's data for the first time.</p>

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
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <img src="docs/media/ontopoc-hero.gif" alt="OntoPoc companion connects business tables into a draft ontology for review" width="960">
</p>
<p align="center"><sub>Concept illustration · <a href="docs/media/ontopoc-poster.png">Still image</a> · <a href="docs/media/ontopoc-motion.mp4">MP4</a></sub></p>

A common approach is to let a language model generate the ontology directly, which leaves its correctness hard to judge. OntoPoc restricts the model to proposing: every element is verified by code against every row, then confirmed by a person.

**Your files stay on your machine** · **All figures are computed by code** · **Source data is never modified**

The interface is in Chinese; this page describes it in English.

## Overview

Upload a few business tables (Excel, CSV) or a process document, and OntoPoc drafts an ontology: which objects the business has, what tells each one apart, and how they relate. Code then checks it against every row: do the fields exist, do the identity fields have values, do the relations actually connect in the data. It runs a data check and answers the question you wrote from the data. You judge each part right or wrong; your judgement is kept, and the next upload of the same file, or a new version of it, starts from it.

The result can be exported in the shape of a data platform's object form or as W3C Turtle (OWL and SHACL), and every feature is also an MCP tool other agents can call.

> **Early version.** Everything has been checked on public and synthetic data only (Chicago city contracts, Northwind, BART transit, the Taiwan company registry, CMS hospitals and more). Nobody but the author has yet used it end to end on their own. Tested on macOS only. Batch import has not been tested on any data platform. See [Known issues](#known-issues).

## Screenshots

<p align="center"><img src="docs/images/readme-objects.png" alt="Ontology: one card per business object" width="880"></p>
<p align="center"><sub>Ontology (本体管理): the 4 objects built from the sample workbook, with check, question and stability status on top.</sub></p>

<p align="center"><img src="docs/images/readme-instances.png" alt="Instance graph: one customer opened out to its orders and products" width="880"></p>
<p align="center"><sub>Instance graph: customer KH001 opened out to its orders, then an order to its product; on the right, the selected order's fields as written.</sub></p>

<p align="center"><img src="docs/images/readme-ask.png" alt="Questions: the answer is computed by code on the data" width="880"></p>
<p align="center"><sub>Questions (智能问答): the model writes the question as a query; code computes the numbers on the uploaded data and says how many values it read.</sub></p>

<p align="center"><img src="docs/images/readme-rules.png" alt="Rules found in the data, checked on every rerun once adopted" width="880"></p>
<p align="center"><sub>Rules in the data check: code finds candidate rules in the data; adopted ones are checked on every rerun.</sub></p>

All screenshots come from the synthetic sample in the repository, `examples/company/demo_company.xlsx`, rendered off-screen by a headless browser.

## How it works

| Action | What the system does |
|---|---|
| Upload tables and write the question you want answered | The model sees only each column's name and up to 3 example values, and proposes objects, identity fields and relations; code checks 17 kinds of error and sends it back to redo, up to 3 drafts |
| Wait for the build | Builds the same file 3 times at once and marks where the 3 disagree (where the model is unsure and you should decide); if your purpose asks a question, it is answered from the data too, ready to keep as an acceptance question |
| Open the data check (数据体检) | Code computes 7 checks row by row, e.g. whether one number carries conflicting details, whether every uploaded table is used |
| Ask a question (智能问答) | The model writes a structured query and code computes the answer on the data; when it cannot, it says whether the ontology lacks something, the data lacks it, or the question is beyond the query. The model can also write a round of 6 questions on request |
| Judge each part, rename, add what is missing | Saved as this file's reference ontology; the next upload is compared against it and prefilled |
| Fix up to 3 questions as acceptance questions | Every rerun computes them with the same query and tells you which changed |
| Adopt rules found in the data | Every rerun checks them and lists the objects that break them |
| Upload a client's new version and say so | Last time's confirmation, questions and rules carry over, with how many of each object came and went |
| Click "Draft" (起草) on the object form | One model call drafts Chinese names, descriptions and display fields; what you edited is never overwritten by a redraft |
| Click "⤓ 表单" at the top right | One CSV per object, in the columns data platforms usually ask for when defining an object |
| Click "⤓ TTL" at the top right | Three Turtle files: `ontology.ttl` describes objects, fields, relations and identity fields in OWL; in `data.ttl` every object is named by its identity values, so the same object in two tables or two versions of a file has one name and merges; `shapes.ttl` writes adopted rules as SHACL for any validator. What you judged wrong is left out |

The model only judges; loops and calculations are in code, with model calls chained at most 3 deep and each call tied to a judgement a person has to make. There are 6 agents, each with a definition card in [docs/AGENTS.md](docs/AGENTS.md).

## Try it

Once installed (see [Quick start](#quick-start)), with the synthetic sample in the repository:

| Action | Expected result |
|---|---|
| Without the modelling service, click "Open sample tables" (打开示例数据表) | A bundled result: 4 objects, 3 relations |
| Upload `examples/company/demo_company.xlsx` with "哪些客户的售后问题最多？" | After half a minute to a minute, 4 cards: customer, product, order, after-sales ticket; data check 5 / 7, the two failures being the problems planted in the sample; the questions chip shows your question answered from the data |
| Ask "每个客户的订单总金额是多少？" (total order amount per customer) | Totals per customer, highest 241,420, from 160 values read |
| Relations (本体关系) → Instance graph, pick a customer | The customer and its orders as a graph; click an order to open its product |
| "⤓ 表单" at the top right | A zip: 4 object-form CSVs and a note on what to test before importing |

## Quick start

You need Python 3.11+, Node 22+ and a DeepSeek API key.

### Option A: let your AI install it

Paste this into Claude Code or Codex:

```text
Install and run OntoPoc (https://github.com/Longado/ontopoc) on this machine:
1. Read the repository's README.en.md and follow "Quick start".
2. Check python3 --version ≥ 3.11 and node --version ≥ 22; if not, tell me how to install them and stop.
3. Clone the repository and run npm ci in landing-page.
4. Ask me for a DeepSeek API key and put it only in this terminal's DEEPSEEK_API_KEY; do not write it to any file.
5. From the repository root, start the modelling service: PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server
6. In another terminal, start the page: cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
7. Open http://127.0.0.1:5178, upload examples/company/demo_company.xlsx once, and tell me how many data checks passed.
```

### Option B: install it yourself

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc
(cd landing-page && npm ci)

# terminal 1: the modelling service (port 8767, results in output/ontology-runs/)
export DEEPSEEK_API_KEY=your-key
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server

# terminal 2: the page
cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

Open `http://127.0.0.1:5178`. The bundled samples open without a key. After changing backend code, restart the modelling service; the page says so when it finds the service running old code.

### Install as a Claude Code plugin

The repository is itself a Claude Code plugin. Once installed you can build and confirm ontologies from Claude Code; modelling, checking and the confirmation record still happen in the local OntoPoc service, so start it first (see above).

```bash
claude plugin marketplace add Longado/ontopoc
claude plugin install ontopoc@ontopoc
```

In a new session there are two commands: `/ontopoc:ontopoc-build` (upload files and build) and `/ontopoc:ontopoc-review` (confirm item by item). At session start the plugin says one line if the local service is not running. It looks for Python as `ONTOPOC_PYTHON`, then `python3`, then `python`.

### Connect Claude Code or another MCP client

Every feature on the page is a standard MCP tool (stdio, 27 tools) calling the same local service:

```bash
claude mcp add ontopoc -- env PYTHONPATH=$PWD/src python3 -m ontology_poc_generator.mcp_server
```

The tool list is in [docs/MCP.md](docs/MCP.md).

## Features

| Module | What is in it |
|---|---|
| Data (数据接入) | Each uploaded table: rows, skipped title lines, each column's type, length and fill; when tables are left unconnected, the column that would connect them |
| Ontology (本体管理) | Object cards (search, filter by your verdict, cards or list); each object's page: overview, fields (the object form), rows (paged, CSV download), confirmation; plus confirmation board, stability, last-run comparison, new version, build record |
| Relations (本体关系) | A graph that lays itself out (drag, zoom), the instance graph, the relation list; relations code sees in the data but the ontology lacks are drawn as dashed suggestions |
| Organisation (组织架构) | Read a public study as an organisation instead: the membership tree, who hands what to whom, a role table, the periods it is cut into, and what the text says is not known; exported as Mermaid diagrams, one per period if you want |
| Questions (智能问答) | Ask, acceptance questions, the model's questions (filter by answered) |
| Data check (数据体检) | 7 checks, rules, comparison with a reference ontology |

There is also an example use of the same method on vehicle recall scope (NHTSA public data), under "More examples" (更多示例) in the sidebar; see [docs/RECALL_EXAMPLE.md](docs/RECALL_EXAMPLE.md). OntoPoc is not affiliated with NHTSA or any carmaker, and its candidates are not defect findings.

## Privacy

- Uploaded files and all results stay on this machine, in `output/ontology-runs/`.
- Sent to the model (DeepSeek): each column's name and up to 3 example values; when writing questions, every value of columns with at most 12 distinct values; for documents, the text, at most 12 chunks per upload. The upload page shows exactly what will be sent, column by column.
- Each model call leaves one line in `output/ontology-runs/model_calls.jsonl` (which agent, how long, success or failure), never the content.
- The page accepts requests from this machine only.

## Known issues

- **The model builds differently each time.** Three builds of one file often differ: on Northwind, only 4 of 8 objects appeared in all 3. The page marks where they disagree for you to decide.
- **A new version may come with a different way of telling objects apart.** Once, Chicago's contracts went from "number + revision" to number alone; then only counts can be compared, not objects one by one, and the page says so.
- **Code finds only some missing relations.** Removing each relation in turn on 17 saved runs (public and synthetic data), it found 24 of 33 again; on complete ontologies it has not suggested a false one.
- **Queries cannot yet** filter by a numeric condition, limit to a time range, give two numbers in one question, or say which things tend to appear together. It says so when asked.
- **Batch import is untested.** The exported form columns follow what data platforms usually ask for; import format, key rules and how relations are expressed differ by platform and have not been tested on any, so no relation table is exported.
- **Turtle export is checked only by reading it back with rdflib and pyshacl.** It has not been loaded into Protégé or a triple store.
- **Tested on macOS only.** Windows and Linux are untested.

## Contributing

**Can an ontology be read, corrected and carried forward by the people whose business it describes?**

| Area | Contribution |
|---|---|
| User research | Have a consultant who is not the author use it from upload to handover notes without help, and record where they get stuck |
| Data quality | Rule discovery has only "required" and "date order"; value ranges, non-negative and others need defining on real data first |
| Platform integration | Test batch import on a specific data platform and add the relation table export |
| Prompts and evaluation | Pick accepted results from local runs as labelled samples, and compare old and new prompts with one command |
| Cross-platform | Run it on Windows or Linux and file what breaks |

Issues and pull requests are welcome. Read the [development guardrails](docs/DEVELOPMENT_GUARDRAILS.md) first.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q      # backend tests (572)
npm --prefix landing-page run test:unit                       # page tests (207)
PYTHONPATH=src:. python3 scripts/run_company_ontology.py --file examples/company/demo_company.xlsx --output output/demo-run.json
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --data-dir /tmp/ontopoc-trial   # a trial run in another data directory, leaving your runs alone
PYTHONPATH=src:. python3 scripts/make_demo_company.py         # regenerate the synthetic workbook
```

The design documents are in Chinese:

| Document | About |
|---|---|
| [docs/PRODUCT.md](docs/PRODUCT.md) | What the product is and which layers it covers |
| [docs/AGENTS.md](docs/AGENTS.md) | The 5 agents' definition cards and the call log |
| [docs/MCP.md](docs/MCP.md) | The 27 MCP tools |
| [docs/PLATFORM_FORM_REFERENCE.md](docs/PLATFORM_FORM_REFERENCE.md) | Data platform object forms, compared |
| [docs/PRD_ITERATION_7.md](docs/PRD_ITERATION_7.md) | The latest round's plan and record |
| [docs/DEVELOPMENT_GUARDRAILS.md](docs/DEVELOPMENT_GUARDRAILS.md) | Red lines, and directions waiting for a trigger |

## License

[MIT](LICENSE) © Yutai Lin
