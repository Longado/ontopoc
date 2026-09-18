<picture>
  <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
  <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc — Draft the ontology. Show the evidence." width="420">
</picture>

# OntoPoc — Draft the ontology. Show the evidence.

English · [中文](README.zh-CN.md)

Hand it a client's business tables or a process document. In a few minutes you get a draft ontology — what the objects are, how each one is identified, how they relate — together with where it has evidence and where it cannot be trusted. Then you go through it item by item and say what is right; that judgement is kept, and the next upload of the same file starts from it.

For implementation consultants and ontology teams. It runs on your machine; files and results never leave it.

## How it works

**The model proposes, code verifies, a person decides.** The model sees field names and a few example values and proposes the objects, identity fields and relations; code checks the proposal against every row and sends errors back, three attempts at most. Each upload is modelled three times at once and code marks what the runs disagree about — the places the model is unsure and a person should decide.

**Every claim is computed, not asserted.** The data check runs seven things row by row in code: whether every field has a place, whether one identity disagrees with itself, whether IDs are spelled one way, whether relations really link, whether references resolve, whether every table connects to the rest, and whether every table you uploaded was read at all. The model then writes business questions as structured queries and code computes the answers on the data — counts, shares, sums, averages, grouping by several fields. When it cannot answer, it says whether the ontology, the data or the query format is what is missing.

**The judgement survives.** A person judges each object and relation, renames, adds what is missing. Two spellings of one thing (a full name and its short form) are proposed by the model, checked against the data by code, and accepted or dropped by a person — nothing is merged, no data is changed. The confirmation becomes that file's reference ontology: upload the same file again and it is compared automatically, with last time's judgement prefilled, so only the differences need looking at. Renaming an object does not read as losing it — matching goes by which table and which identity fields, not by the label.

## What it has been checked against

No real client has used it yet, and it is not deployed. What has been checked, and how:

- **Chicago city contracts, 3,000 rows.** A per-department total of 4,631,003,200 matches adding the rows up in Python. Name matching proposed "PLANNING & DEVELOPMENT" for "DEPARTMENT OF PLANNING AND DEVELOPMENT" (140 rows against 3) and a second pair for the fleet department (67 against 12); after a person accepted them and re-uploaded the file, one pair was proposed again by the model and the other came back from the earlier confirmation.
- **Chinook invoices, 412 rows.** An average invoice of 5.65, matching Python.
- **UCI Online Retail II** and **a listed company's related-party transaction policy (PDF)**: each exposed problems that are now fixed.
- **A synthetic manufacturing company** (four sheets) and its after-sales process document, with two problems planted on purpose that the data check finds.
- 306 real questions have been asked across runs; the checks and limits are recorded per round in `docs/PRD_ITERATION_5.md`.

Tests: 358 backend, 128 page, both on every pull request.

## Limits

- The ontology is the model's proposal. Passing verification means it fits the data, not that it is the best way to carve up the business.
- Queries cannot yet filter by a numeric condition, restrict a time window, or return two different measures in one question.
- Synonyms in an attribute column are out of range: name matching only covers objects a single name identifies. `docs/PRD_ITERATION_5.md` §8 measures what that costs.
- Confirmations are remembered per file hash, so a client's updated file (even one extra row) does not match the previous one, and nothing warns you.
- Tables and documents are modelled separately; one business's tables and documents cannot be combined yet.
- Only field names, at most 3 example values per column, and the full value list of columns with at most 12 values are sent to the model (for documents, the text). The upload page lists exactly this before anything is sent.

## Run it

```bash
# the page
cd landing-page && npm ci && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
# the local modeling service (port 8767, needs a local DeepSeek key; results stay in output/ontology-runs/)
PYTHONPATH=src python -m ontology_poc_generator.ontology_server
```

Open `http://127.0.0.1:5178`. Without the service, two bundled demo results can still be opened: a synthetic company's workbook and its after-sales process document. Changing the backend means restarting the service — the page says so when it sees a stale one.

```bash
PYTHONPATH=src python -m unittest discover -s tests -q          # backend tests
npm --prefix landing-page run test:unit                         # page tests
PYTHONPATH=src:. python scripts/run_company_ontology.py --file examples/company/demo_company.xlsx --output output/demo-run.json
PYTHONPATH=src:. python scripts/make_demo_company.py            # regenerate the synthetic workbook
```

## Example: vehicle recall scope review

The same "the model proposes, code verifies" approach applied to NHTSA recall notices and owner complaints: it computes the similar complaints inside and outside each recall for a quality engineer to review (Chevrolet Bolt EV / EUV 2017–2023, Hyundai Kona Electric 2019–2021). It lives under "More examples" in the page sidebar, reads static files under `landing-page/public/data/`, and needs no Python service. Its commands and code map are in [docs/RECALL_EXAMPLE.md](docs/RECALL_EXAMPLE.md).

Data comes from the NHTSA public API. OntoPoc is not affiliated with NHTSA, General Motors or Hyundai; its candidates and first-pass verdicts are not official findings or defect determinations, and a review does not mean a defect is confirmed or a vehicle recalled.

## Code map

| File | Role |
|---|---|
| `src/ontology_poc_generator/company_sources.py` | read uploaded tables and documents, one file or a batch |
| `src/ontology_poc_generator/company_ontology.py` | the modelling prompt and the build-and-verify loop |
| `src/ontology_poc_generator/public_ontology.py` | field catalog, ontology verification (17 error codes), object graph |
| `src/ontology_poc_generator/ontology_eval.py` | the seven data checks, computed row by row |
| `src/ontology_poc_generator/ontology_questions.py` | business questions and the structured queries code answers them with |
| `src/ontology_poc_generator/name_variants.py` | two spellings of one thing: candidates the data backs, never merged |
| `src/ontology_poc_generator/ontology_confirm.py` | a person's judgement, the reference ontology it becomes, and the prefill next time |
| `src/ontology_poc_generator/ontology_acceptance.py` | the 1–3 fixed acceptance questions and how they survive renaming |
| `src/ontology_poc_generator/ontology_compare.py` | comparing two ontologies by what they are built from |
| `src/ontology_poc_generator/ontology_server.py` | the local service the page talks to |
| `landing-page/src/OntologyStudio.jsx` | the workbench: upload, ontology, data check, questions, confirmation |
| `landing-page/src/*Model.js` | the page's pure functions, each with its own tests |

## History and documents

The project started on 2026-08-29 as a pre-sales POC proposal compiler, went through supply-chain, synthetic quality, food-recall and recall-scope scenarios, and on 2026-09-14 settled on "upload a file, build an ontology, evaluate it automatically", with recall review kept as an example. Retired lines are tagged `archive-2026-09-13-nhtsa-review`.

The documents below are in Chinese. Read the [guardrails](docs/DEVELOPMENT_GUARDRAILS.md) before developing.

| Document | What it holds |
|---|---|
| [docs/PRODUCT.md](docs/PRODUCT.md) | what the product is, which layers it stands on, what it produces |
| [docs/FEATURES_2026-09-16.md](docs/FEATURES_2026-09-16.md) | what happens on one upload, where the code is, the known limits |
| [docs/PRD_ITERATION_5.md](docs/PRD_ITERATION_5.md) | the latest round: what was built, how it was checked, what it does not cover |
| [docs/PRD_ITERATION_6.md](docs/PRD_ITERATION_6.md) | the current plan |
| [docs/DEVELOPMENT_GUARDRAILS.md](docs/DEVELOPMENT_GUARDRAILS.md) | the lines not to cross, and directions waiting for a trigger |

License: MIT.
