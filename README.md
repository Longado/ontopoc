<picture>
  <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
  <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc — Trace scope. Review evidence." width="420">
</picture>

# OntoPoc — Trace scope. Review evidence.

English · [中文](README.zh-CN.md)

An ontology drafting and checking tool for implementation consultants and ontology teams. Give it a client's business tables or a process document and within minutes get a draft ontology, together with where it has evidence and where it cannot be trusted:

1. A model sees only field names and a few sample values and proposes the objects, how each is identified and how they relate; code checks the proposal against all the data and sends errors back, three attempts at most. Every concept and relation from a document must quote the text, and code drops what it cannot find.
2. Each upload is modelled three times at once; code aligns the runs and marks objects and relations missing from some of them, the places where the model is unsure and a person should decide.
3. The data check is computed row by row in code: whether every field has a place, whether one identity disagrees with itself, whether IDs are spelled one way, whether relations really link and references resolve.
4. The model writes business questions as structured queries and code computes the answers on the data (counts, shares, grouping by several fields); when it cannot answer, it says whether the ontology, the data or the query format is missing something.
5. When someone has written a reference ontology, code compares the two item by item.

Before building, the upload page shows everything that would be sent to the model; files and results stay on the machine. Verified on a synthetic manufacturing company (four sheets) and its after-sales process document, and on three real public files (Chicago city contracts, a listed company's related-party transaction policy, UCI Online Retail II); see `docs/PRD_ITERATION_3.md` §12. No real client has used it yet, and it is not deployed.

Example scenario: vehicle recall scope review. The same "the model proposes, code verifies" approach applied to NHTSA recall notices and owner complaints, computing the similar complaints inside and outside each recall for a quality engineer to review (Chevrolet Bolt EV / EUV 2017–2023, Hyundai Kona Electric 2019–2021). Data comes from the NHTSA public API; OntoPoc is not affiliated with NHTSA, General Motors or Hyundai, and its candidates and first-pass verdicts are not official findings or defect determinations.

History: the project started on 2026-08-29 as a pre-sales POC proposal compiler, went through supply-chain, synthetic quality, food-recall and recall-scope scenarios, and on 2026-09-14 settled on "upload a file, build an ontology, evaluate it automatically", with recall review kept as an example. The retired lines are tagged `archive-2026-09-13-nhtsa-review`.

> Before developing, read the [guardrails](docs/DEVELOPMENT_GUARDRAILS.md). Current plan and results: [iteration 3 requirements](docs/PRD_ITERATION_3.md); handoff notes: [handoff](docs/HANDOFF_2026-09-13.md). These documents are in Chinese.

## Pages

```bash
cd landing-page && npm ci && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

Open `http://127.0.0.1:5178`. Since 2026-09-14 the default entry is "Upload to ontology" (plan: `docs/PRD_ITERATION_3.md`). You upload a business table (Excel or CSV) or a document (Markdown, text, Word or PDF), get a company ontology built automatically, and see three evaluations. The first two run on their own after every build (documents get only the first); the third runs when you upload a reference:

- how well the ontology fits the data (for documents: whether every item quotes the text);
- whether it can answer business questions (the model writes the queries, code answers them on the data);
- how it compares with a reference ontology written by a person.

The ontology tab is a graph with an evidence inspector, and data problems are marked on the nodes. Each table upload is modelled three times at once, and objects or relations missing from some runs are marked; uploading the same file again also lists what changed since the previous run. Before building, the upload page shows exactly what would be sent to the model. Uploads and questions need the local modeling service; without it, two bundled demo results can be opened: a synthetic manufacturing company's workbook and its after-sales process document.

```bash
# local modeling service (port 8767, needs a local DeepSeek key; files and results stay in output/ontology-runs/)
PYTHONPATH=src python -m ontology_poc_generator.ontology_server
# run one file from the command line
PYTHONPATH=src:. python scripts/run_company_ontology.py --file examples/company/demo_company.xlsx --output output/demo-run.json
# regenerate the synthetic demo workbook
PYTHONPATH=src:. python scripts/make_demo_company.py
```

The recall scope review is now the example entry "Example: vehicle recalls". It reads static files under `landing-page/public/data/` (an index plus one file per dataset: Chevrolet Bolt EV / EUV 2017–2023 and Hyundai Kona Electric / Kona EV 2019–2021) and needs no Python service. A left sidebar switches between the two entries; recall scope review has four tabs: Data scope (check how the data was read, judge each name mapping; the auto-built ontology sits under technical details) → Recalls (grouped by part, re-recalls chained into series) → Review (ordered by after-recall, fire/crash, date; arrow keys and 1/2/3 work) → Results (agreement with the model, reviewer name, download). Reviews live in the local browser; they are local records, not approvals. The page text is Chinese.

`/landing` is the product page. The second entry, "Public recall lookup", matches products and lots for openFDA event 95876 and needs the local Python service below.

## Commands

```bash
PYTHONPATH=src python -m unittest discover -s tests -q            # backend tests
npm --prefix landing-page run test:unit                             # frontend tests
npm --prefix landing-page run build && npm --prefix landing-page run test:sites
PYTHONPATH=src:. python scripts/build_public_review_pack.py --check # every dataset in the index still matches its run

# add a dataset, in order (steps 3 and later need a local DeepSeek key, see handoff §4; never commit keys)
# 1. snapshot a make, models and years from NHTSA
PYTHONPATH=src:. python scripts/fetch_nhtsa_snapshot.py \
  --make chevrolet --model "bolt ev" --model "bolt euv" --years 2017-2023 --output examples/nhtsa/<snapshot>.json
# 2. list the recall campaigns in that snapshot
PYTHONPATH=src:. python scripts/run_public_ontology.py --snapshot examples/nhtsa/<snapshot>.json
# 3. online run on the same snapshot: build the ontology, then scope and first verdicts for the campaigns you pick
PYTHONPATH=src:. python scripts/run_public_ontology.py --snapshot examples/nhtsa/<snapshot>.json \
  --campaign 20V701000 --campaign 18V576000 --output output/public-ontology-<time>.json
# 4. keep the run, publish the page data (also updates landing-page/public/data/index.json), check it
cp output/public-ontology-<time>.json examples/nhtsa/runs/<name>.json
PYTHONPATH=src:. python scripts/build_public_review_pack.py --report examples/nhtsa/runs/<name>.json --snapshot examples/nhtsa/<snapshot>.json
PYTHONPATH=src:. python scripts/build_public_review_pack.py --check
# 5. the dataset now appears in the page's dataset picker

# after a review: add the download to the label store, then compare rule, model and rule-then-model (counts only)
PYTHONPATH=src:. python scripts/import_reviews.py --input <dataset>-review.json --reviewer <code name>   # writes examples/labels/ (public repo: complaint ids and verdicts, no complaint text or VINs)
PYTHONPATH=src:. python scripts/compare_judgments.py --labels examples/labels/<dataset>.jsonl

# rerun the model's first calls on a recorded run's inputs and count how many change (needs the key)
PYTHONPATH=src:. python scripts/check_stability.py --report examples/nhtsa/runs/<name>.json --snapshot examples/nhtsa/<snapshot>.json --output output/stability-<time>.json

# event 95876 local service and CLI
PYTHONPATH=src python -m ontology_poc_generator.recall_server
PYTHONPATH=src python -m ontology_poc_generator.recall_cli --product F-0369-2025/1 --lot X7547814
```

## Code map

| File | Role |
|---|---|
| `src/ontology_poc_generator/nhtsa_sources.py` | fetch, dedupe, per-source date normalisation, snapshot validation and hash, recall references |
| `src/ontology_poc_generator/public_ontology.py` | field catalog, ontology verification (17 error codes), object graph, build loop, value aliases |
| `src/ontology_poc_generator/public_scope.py` | scope query, before/after timing, complaint text check with quote gate |
| `src/ontology_poc_generator/public_review_pack.py` | page data: groups, series, candidates, blind-spot counts |
| `src/ontology_poc_generator/review_labels.py` | review downloads → label store; the fire-keyword rule; rule / model / rule-then-model counts |
| `src/ontology_poc_generator/model_gateway.py`, `recognition.py` | OpenAI-compatible gateway and the model call contract |
| `src/ontology_poc_generator/recall_*.py` | event 95876 lookup (scope table, matching, local server, DeepSeek extraction check) |
| `landing-page/src/PublicRecallReview.jsx`, `publicReviewModel.js` | review page and its pure functions |
| `landing-page/src/RecallWorkspace.jsx`, `recallWorkspaceModel.js` | event 95876 workbench |
| `landing-page/src/App.jsx` | product page |
| `examples/nhtsa/` | snapshot and recorded online runs |

## Limits

Scope stops at model year; public recall data has no VIN. Model verdicts are first calls with no human-labelled regression set yet. Verified on one dataset; the four roles (event, affected object, mechanism, signal) fit recall-versus-complaint scope, not arbitrary questions. Names that differ across sources are bridged only by verified aliases; anything not bridged is still missed, and the page reports how many complaints entered no candidate list. A review does not mean a defect is confirmed, a vehicle recalled or anything dispositioned.

License: MIT.
