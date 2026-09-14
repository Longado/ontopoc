<picture>
  <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
  <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc — Trace scope. Review evidence." width="420">
</picture>

# OntoPoc — Trace scope. Review evidence.

English · [中文](README.zh-CN.md)

After a recall is issued, which similar complaints fall outside its scope? OntoPoc answers that question for a quality engineer from two public sources, NHTSA recall notices and owner complaints:

1. A model proposes an ontology from field names and sample values only; code verifies the proposal against every record (17 checks) and sends errors back, three attempts at most.
2. Category names that exist in only one source go to the model for an alias; code keeps an alias only when it links more records, and every candidate that depends on one is marked.
3. For each recall, code computes the covered model years and the same-part complaints in three buckets (inside this recall, covered by another same-part recall, outside every one), dated before or after the recall. Recalls that name an earlier recall as the repair they redo are chained into a series.
4. The model gives a first verdict on each complaint text; "same defect" must quote the complaint, and code checks the quote is really there.
5. A quality engineer reviews each candidate on a static page. The reviews are the labels that will calibrate step 4.

Verified on Chevrolet Bolt EV / EUV 2017–2023 (13 recalls, 679 complaints) and Hyundai Kona Electric / Kona EV 2019–2021 (4 recalls, 107 complaints), both fetched 2026-09-13. No customer data, no VIN-level scope, no deployment yet.

History: the project started on 2026-08-29 as a pre-sales POC proposal compiler and went through supply-chain, synthetic quality and food-recall scenarios before settling on recall scope review on 2026-09-13. The retired lines were removed from the branch; the full state before removal is tagged `archive-2026-09-13-nhtsa-review`.

> Before developing, read the [guardrails](docs/DEVELOPMENT_GUARDRAILS.md). Current state and next steps: [handoff](docs/HANDOFF_2026-09-13.md), [feature inventory](docs/FEATURES_2026-09-13.md), [iteration 2 requirements](docs/PRD_ITERATION_2.md). These documents are in Chinese.

## Pages

```bash
cd landing-page && npm ci && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

Open `http://127.0.0.1:5178`. The default scenario, "Vehicle recall scope (NHTSA)", reads static files under `landing-page/public/data/` (an index plus one file per dataset: Chevrolet Bolt EV / EUV 2017–2023 and Hyundai Kona Electric / Kona EV 2019–2021) and needs no Python service. A left sidebar switches between the two entries; recall scope review has four tabs: Ontology (confirm ontology and aliases) → Recalls (grouped by part, re-recalls chained into series) → Review (ordered by after-recall, fire/crash, date) → Results (agreement with the model, reviewer name, download). Reviews live in the local browser; they are local records, not approvals. The page text is Chinese.

`/landing` is the product page. The second entry, "Public recall lookup", matches products and lots for openFDA event 95876 and needs the local Python service below.

## Commands

```bash
PYTHONPATH=src python -m unittest discover -s tests -q            # backend tests
npm --prefix landing-page run test:unit                             # frontend tests
npm --prefix landing-page run build && npm --prefix landing-page run test:sites
PYTHONPATH=src:. python scripts/build_public_review_pack.py --check # every dataset in the index still matches its run

# online run (needs a local DeepSeek key, see handoff §4; never commit keys)
PYTHONPATH=src:. python scripts/run_public_ontology.py \
  --campaign 21V650000 --campaign 18V576000 --output output/public-ontology-<time>.json
cp output/public-ontology-<time>.json examples/nhtsa/runs/<name>.json
PYTHONPATH=src:. python scripts/build_public_review_pack.py --report examples/nhtsa/runs/<name>.json --snapshot examples/nhtsa/<snapshot>.json

# snapshot another make or model
PYTHONPATH=src:. python scripts/fetch_nhtsa_snapshot.py \
  --make chevrolet --model "bolt ev" --years 2017-2023 --output examples/nhtsa/<name>.json

# after a review: add the download to the label store, then compare rule, model and rule-then-model (counts only)
PYTHONPATH=src:. python scripts/import_reviews.py --input <dataset>-review.json --reviewer <code name>
PYTHONPATH=src:. python scripts/compare_judgments.py --labels examples/labels/<dataset>.jsonl

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
