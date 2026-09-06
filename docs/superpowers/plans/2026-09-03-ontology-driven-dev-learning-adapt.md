# Ontology-Driven Dev Learning and Adapt Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` or `executing-plans` only after the corresponding phase gate is approved. This document is the learning and product-adaptation plan; it does not authorize all listed implementation work at once.

**Goal:** Systematically learn the useful product methods in `sharptoolbox/ontology-driven-dev`, adapt them to OntoPoc's manufacturing quality-decision product, and prove each adopted idea against the temporary-control decision before expanding the system.

**Architecture:** `DecisionPack` remains the only editable semantic authority and `OntologySpec` remains its compiled output. Requirement discovery, seven-model coverage, implementation traceability, UI views, and acceptance reports are derived views or working materials. Source systems remain fact authorities, Python remains deterministic-state authority, Agents remain candidate producers/reviewers, and the quality owner remains decision authority.

**Tech Stack:** Existing Python 3.11 standard-library package and unittest suite; existing React/Vite demo only when a later gate explicitly requires UI. No new production dependency is authorized by this plan.

---

## 1. Why this Adapt exists

OntoPoc has already proved a narrow technical chain:

```text
five-system evidence
→ DecisionPack / OntologySpec
→ deterministic four-state evaluation
→ constrained multi-Agent proposals
→ human confirmation boundary
```

The current product gap is not another runtime framework. It is the ability to show, in business language:

1. whether the decision requirements have been explored completely;
2. which business objects, behaviors, rules, actors, flows, queries, and views are required;
3. which modeled elements are executable and which are only declarations;
4. whether the full quality-control decision can be completed by a user.

`ontology-driven-dev` is useful because it packages requirement discovery, seven-model coverage, model-to-implementation alignment, and a runnable golden case. Its current source does not prove that YAML is a deterministic code generator, so OntoPoc will learn its method without copying that claim or its full stack.

## 2. Product anchor

Every Adapt item must improve this decision:

> After a quality abnormality, which inventory, work-in-process, pending shipment, in-transit, or customer-side objects should enter temporary control or reinspection?

Primary user: quality owner who accepts, changes, or rejects the proposed scope.

Supporting users: quality engineer, production, warehouse/logistics, planning/customer-delivery, and product/process engineering.

Success will be measured first by observable decision behavior, not feature count:

- every scope item has inspectable evidence or an explicit missing-evidence statement;
- no object is excluded while a relevant relationship remains unknown;
- the quality owner can correct the candidate model and scope without editing code;
- a held-out case exposes omissions rather than being forced into a complete-looking result;
- no Agent, UI, or receipt is presented as a production action or customer acceptance.

Baseline business metrics to collect before setting targets:

- time from quality signal to first reviewable scope;
- number and type of human corrections;
- false-exclusion findings during review;
- proportion of `not_evaluable` objects and the missing relationship causing each one;
- time spent locating evidence across ERP/MES/QMS/WMS/PLM.

## 3. What will be learned and how it maps

| Source-project idea | What it teaches | OntoPoc Adapt | Decision |
| --- | --- | --- | --- |
| Eight-stage requirement discovery | A structured way to expose missing business details | Compress into four decision gates and ask only unresolved, high-impact questions | ADAPT |
| M1 object model | Objects, attributes, dictionaries, aggregates | Existing OntologySpec entities, relations, properties plus instance evidence | ADOPT AS VIEW |
| M2 behavior model | Commands, queries, preconditions, results | Describe ingest, model, assess, confirm, and reject behaviors; do not create another executable schema yet | ADAPT AS COVERAGE |
| M3 rule model | Rule identity and relation to behaviors | Existing rule declarations and four-state Python evaluators remain authoritative | ADOPT EXISTING |
| M5 actor model | Roles, permissions, responsibilities | Map decision owner, contributors, Agent roles, and prohibited actions | ADAPT AS COVERAGE |
| M6 flow model | End-to-end collaboration and approval | Map the current decision sequence; add persistence/workflow only after a real cross-day case | ADAPT LATER |
| M7 query/report model | Questions and fixed outputs | Four-state scope, evidence, counterevidence, gaps, and receipt views | ADOPT AS ACCEPTANCE |
| MU UI model | User-visible screens and actions | Use only after the non-UI workflow is accepted; do not make UI a second authority | DEFER |
| Ontology registry | Runtime discovery of model metadata | Consider only after a second real consumer needs it | DEFER |
| Model-to-code mapping | Reveals whether a model element is actually implemented | Derived traceability output tied to pack/spec hashes | ADAPT |
| Golden contract-management example | One runnable path is stronger than broad documentation | Build one Sanhua-shaped synthetic golden decision and one held-out challenge case | ADOPT |
| Mandatory AI chat and read-only SQL | A generic interaction shell | Introduce only when users repeatedly ask cross-view questions that fixed views cannot answer | REJECT FOR NOW |
| Copying the Flask/React techbase | Rapid generic management-system scaffolding | Conflicts with the current focused product and existing codebase | REJECT |

## 4. Target product structure after a successful Adapt

```text
Quality decision brief
  ├─ Gate A: decision and pain
  ├─ Gate B: evidence and model coverage
  ├─ Gate C: rule, uncertainty, and action boundary
  └─ Gate D: acceptance case
            ↓
DecisionPack (editable semantic authority)
            ↓
OntologySpec (compiled semantic authority)
            ├─ Seven-model coverage view (derived)
            ├─ Implementation trace view (derived)
            └─ Missing-capability report (derived)
            ↓
Five-system synthetic facts
            ↓
Deterministic four-state scope + ValidationReceipt
            ↓
Constrained Agent review and recommendation
            ↓
Human accept / change / reject
```

Authority must remain explicit:

| Concern | Authority |
| --- | --- |
| ERP/MES/QMS/WMS/PLM records | Source system or captured synthetic snapshot |
| Business decision definition | Human-confirmed DecisionPack |
| Compiled semantic types and rules | OntologySpec |
| Four-state classification | Python evaluator |
| Candidate extraction and critique | Agent output, never final authority |
| Final temporary-control choice | Quality owner |
| UI, coverage matrix, traceability table | Read-only projection |

## 5. Phase 0 — Source learning and claim audit

**Purpose:** Understand the source project before deciding what OntoPoc should copy.

**Duration:** 1–2 focused working days.

**Files:**

- Create when execution is authorized: `docs/ONTOLOGY_DRIVEN_DEV_LEARNING.md`
- Read only: source repository `README.md`, `SKILL.md`, five `references/` documents, `reference-example/`, `techbase/`, and `code-app-example/`
- Do not modify OntoPoc source code.

**Tasks:**

- [x] Record every material source-project claim: requirement traceability, YAML authority, generation, workflow, permissions, AI chat, and SQL safety.
- [x] For each claim, locate the exact implementing code or classify it as documentation discipline, example implementation, or unverified claim.
- [x] Trace one contract rule from requirement text through YAML, Python service, flow, frontend, and smoke test.
- [x] Record where code is generated, where it is manually written, and where identifiers are only kept aligned by convention.
- [x] Produce an `ADOPT / ADAPT / DEFER / REJECT` matrix with a product reason for every item.

**Proof:**

- Every conclusion links to a specific official repository file.
- “Generated from YAML” is not accepted unless an actual deterministic generator and regression test are identified.
- The learning note contains no Sanhua-sensitive material.

**Exit gate:** Approve the learning matrix. No product code may start before this gate.

**Execution record (2026-09-03):** Phase 0 research and its independent review are complete in `docs/ONTOLOGY_DRIVEN_DEV_LEARNING.md`. The matrix is awaiting product-owner approval; Phase 1 remains unauthorized.

## 6. Phase 1 — Adapt requirement discovery to four decision gates

**Purpose:** Learn the source project's discovery discipline without forcing eight ceremonies on one focused decision.

**Duration:** 2–3 focused working days.

**Files:**

- Create: `docs/QUALITY_DECISION_DISCOVERY.md`
- Modify only after RED tests: `src/ontology_poc_generator/agent_modeling.py`
- Test: `tests/test_agent_modeling.py`
- Test: `tests/test_agent_modeling_cli.py`

**Four gates:**

### Gate A — Decision and pain

Confirm the trigger, decision sentence, decision owner, affected object categories, decision deadline, and current manual process.

Required output:

```text
trigger → decision owner → decision → affected object categories → expected action
```

### Gate B — Evidence and model coverage

Confirm which ERP/MES/QMS/WMS/PLM facts exist, system ownership, identifiers, time semantics, batch/version/BOM links, normal comparisons, and missing relationships.

Required output: evidence inventory plus unresolved questions; never fill customer-specific facts from industry convention.

### Gate C — Rule, uncertainty, and action boundary

Confirm the conditions for `confirmed_impact`, `possible_impact`, `excluded`, and `not_evaluable`; confirm what the system may recommend and what only a human may decide.

Required output: deterministic classification contract and prohibited claims.

### Gate D — Acceptance case

Confirm one known case, one boundary case, and one held-out case. Define what the quality owner should be able to inspect and change.

Required output: executable acceptance examples, not a feature wish list.

**Tasks:**

- [ ] Write failing tests showing that missing decision owner, trigger, source ownership, exclusion rule, or acceptance case blocks readiness at the appropriate gate.
- [ ] Update the decision-analysis prompt to return four gate results and unresolved questions.
- [ ] Keep candidate extraction separate from human confirmation; do not add automatic acceptance.
- [ ] Run focused Agent contract tests with fake gateways only.
- [ ] Review the four-gate document with a product/quality perspective before changing the live model prompt.

**Proof:**

- A complete synthetic case reaches `ready_for_human_confirmation`.
- A case missing an exclusion condition or system-of-record remains blocked.
- Existing evidence refs and four-state constraints remain unchanged.

**Exit gate:** A quality-domain reviewer says the four gates expose the questions needed to decide scope. Otherwise revise the discovery contract, not the runtime.

## 7. Phase 2 — Seven-model coverage as a derived product view

**Purpose:** Use the seven models to detect omissions without creating seven editable YAML authorities.

**Duration:** 3–5 focused working days.

**Files:**

- Create: `src/ontology_poc_generator/model_coverage.py`
- Create: `tests/test_model_coverage.py`
- Modify: `src/ontology_poc_generator/connected_assessment_cli.py`
- Modify: `README.md`
- Do not modify the DecisionPack or OntologySpec schemas in this phase.

**Derived coverage sections:**

| Section | OntoPoc source | Minimum question answered |
| --- | --- | --- |
| M1 Objects | OntologySpec types and five-system facts | What is being evaluated and how is it linked? |
| M2 Behaviors | Current application operations | What can ingest, assess, review, confirm, or reject? |
| M3 Rules | Rule declarations and Python evaluators | Which classifications are executable? |
| M5 Actors | Decision owner, participants, Agent roles | Who proposes, reviews, decides, and may not act? |
| M6 Flow | Connected assessment sequence | What is the actual order and where does it stop? |
| M7 Queries | Scope/evidence/gap/receipt outputs | What questions can the product answer? |
| MU UI | Existing CLI/artifact/browser surfaces | Where can a user inspect or change the result? |

Each section returns one of:

- `covered`: supported by a concrete current artifact or implementation;
- `missing`: required by the decision but absent;
- `not_applicable`: explicitly unnecessary for this decision.

**Tasks:**

- [ ] Write a failing test for one complete synthetic quality case and one case missing actor/action coverage.
- [ ] Implement a pure projection over existing artifacts; do not persist or edit coverage separately.
- [ ] Include evidence or implementation references for every `covered` result.
- [ ] Reject unknown coverage statuses and duplicate section IDs.
- [ ] Add optional CLI output without changing existing output bytes.
- [ ] Run the full backend suite and existing artifact checks.

**Proof:**

- The same pack/spec always produces byte-stable coverage output.
- Removing a required actor or query changes only the corresponding coverage section to `missing`.
- No new YAML format, database, dependency, or frontend state is introduced.

**Exit gate:** The coverage output must reveal at least one meaningful omission in a held-out scenario or reduce review effort for a quality user. If it merely restates existing JSON, stop and do not proceed.

## 8. Phase 3 — Executable implementation traceability

**Purpose:** Distinguish real runtime capability from model declarations and UI claims.

**Duration:** 2–4 focused working days after Phase 2 passes.

**Files:**

- Review the existing spike commit: `74363b3`
- Candidate implementation: `src/ontology_poc_generator/implementation_map.py`
- Candidate test: `tests/test_implementation_map.py`
- Candidate CLI integration: `src/ontology_poc_generator/cli.py`
- Update: `docs/FRONTEND_BACKEND_CAPABILITY_MAP.md`

**Required trace:**

```text
model element
→ origin binding/suggestion
→ source_ref
→ compiler/validator/evaluator
→ output artifact or user surface
→ current execution state
```

Allowed execution states:

- `declared_only`;
- `runtime_input`;
- `runtime_executable`;
- `user_visible` only when a current surface actually renders it.

**Tasks:**

- [ ] Compare spike `74363b3` against the approved Phase 2 coverage contract.
- [ ] Keep it only if the output answers a user review question; otherwise revert it before further implementation.
- [ ] Write failing tests for missing source references, pack/spec hash mismatch, stable ordering, and false executable claims.
- [ ] Derive traceability from current authority artifacts and an explicit current-consumer catalog; do not infer implementation by naming convention.
- [ ] Add the result to one CLI or artifact entry point only.
- [ ] Ensure existing DecisionPack and OntologySpec output formats remain unchanged.

**Proof:**

- A declared relation with no runtime consumer is visibly `declared_only`.
- A supported rule links to the evaluator and ValidationReceipt.
- A mismatched pack/spec pair is rejected.
- Deleting or renaming a declared consumer makes a focused test fail.

**Exit gate:** A reviewer can answer “is this element actually used?” without reading source code. Otherwise remove the feature rather than add more metadata.

## 9. Phase 4 — One Sanhua-shaped golden decision and one held-out case

**Purpose:** Prove that the learned method improves the product's real decision loop.

**Duration:** 3–5 focused working days.

**Files:**

- Extend only synthetic/public fixtures under `tests/fixtures/enterprise_sources/`
- Modify: `tests/test_connected_assessment.py`
- Modify: `tests/test_connected_assessment_cli.py`
- Modify only if required: `scripts/generate_quality_investigation_artifact.py`
- Do not add customer-sensitive source material to the repository.

**Golden case must include:**

- one QMS quality signal and abnormal inspection;
- MES batch usage and production version;
- PLM BOM/version relationship;
- WMS inventory, work-in-process, pending shipment, and in-transit objects;
- ERP order/customer-side relationship;
- at least one object in each of the four evaluation states;
- human correction of one Agent candidate;
- final candidate control scope with evidence and missing-evidence statements;
- no root-cause confirmation and no external action.

**Held-out case must challenge:**

- mixed normal/abnormal batch evidence;
- a missing BOM or version bridge;
- an object that would be falsely excluded by optimistic traversal;
- an Agent attempt to add an unknown object or rewrite deterministic reasoning.

**Tasks:**

- [ ] Write the held-out failing test before changing evaluators or prompts.
- [ ] Run the golden case through the native CLI, not through a manually assembled screenshot.
- [ ] Record which discovery gate or coverage section catches each omission.
- [ ] Ask a quality-domain reviewer to accept, change, or reject the proposed scope.
- [ ] Record time, corrections, false-exclusion findings, and unresolved data gaps.

**Proof:**

- The golden case completes to human review.
- The held-out case fails closed at the intended boundary.
- The reviewer can trace each scope object from source record to classification and recommendation.
- No result claims customer production validation.

**Exit gate:** Continue only if the Adapt changes a real review decision or exposes a real omission. Technical completeness alone is insufficient.

## 10. Phase 5 — Productize only validated friction

This phase is not automatically authorized. Select at most one item based on observed user friction:

| Observed friction | Allowed next capability | Entry condition |
| --- | --- | --- |
| Users cannot understand coverage JSON | One read-only coverage/trace view | Two review sessions show the same comprehension failure |
| Users repeatedly ask cross-view questions | Bounded deterministic Q&A, then optional model Q&A | At least three repeated question patterns are recorded |
| Investigations wait across days or teams | Persisted decision case and task states | A real workflow needs resume/retry/ownership |
| Multiple consumers need semantic metadata | Read-only ontology registry | Two real consumers exist |
| A second business application repeats mappings | Deterministic generator for the repeated slice | Two stable, accepted callers exist |
| Customer tables must remain in place | Ontop or a bounded virtual mapping adapter | Read-only schema samples and access constraints are available |

Still prohibited without a separate decision:

- copying `techbase/`;
- installing seven-YAML as a second authority;
- generic CRUD/code generation;
- mandatory AI chat;
- generic RBAC/workflow/reporting platforms;
- Temporal, BaSyx, pySHACL, LinkML, or Ontop without their specific entry condition;
- real freeze, stop-production, shipment block, or external writeback.

## 11. Prioritized roadmap

### Now — learn and decide

1. Complete Phase 0 claim/code audit.
2. Approve or revise the four-gate discovery contract.
3. Decide whether `74363b3` is retained as a spike or reverted.

### Next — prove product value

4. Build the derived seven-model coverage view.
5. Build or refine implementation traceability only after coverage acceptance.
6. Run the golden and held-out quality cases with a human reviewer.

### Later — remove observed friction

7. Choose at most one Phase 5 capability based on recorded user behavior.
8. Re-baseline metrics after the first real read-only customer mapping.

### Not planned

9. Full source-project fork, full application generator, generic platform rewrite, or production writeback.

## 12. Treatment of the premature spike commit

Commit `74363b3` was created before this learning plan and therefore is not accepted as the Adapt result.

Current handling:

- keep it isolated on the open feature branch;
- do not build additional capabilities on top of it;
- classify it as a Phase 3 spike;
- after Phase 0–2 review, explicitly choose either:
  - retain and refine it because it answers an approved review question; or
  - revert it cleanly because it does not contribute to the validated product loop.

No revert, merge, or further push is authorized by this plan alone.

## 13. Whole-plan acceptance criteria

The Adapt is complete only when all of the following are true:

- source-project claims have been checked against source code;
- every source idea is classified `ADOPT / ADAPT / DEFER / REJECT`;
- four-gate discovery has been reviewed against the quality-control decision;
- seven-model coverage is derived from existing authority rather than separately edited;
- implementation traceability distinguishes declarations from executable behavior;
- one golden case and one held-out case have been run through a native entry point;
- a human quality reviewer has made at least one explicit accept/change/reject decision;
- outcomes and limitations are recorded without production or customer-acceptance claims;
- no dependency, framework, UI, persistence layer, or external writeback was added without its entry condition.

## 14. Execution checkpoints

This plan should be executed as four separately approved batches:

1. **Learning batch:** Phase 0 only; documentation, no code.
2. **Product-contract batch:** Phase 1 only; prompt/contract changes after review.
3. **Coverage and trace batch:** Phase 2, then a separate go/no-go for Phase 3.
4. **Acceptance batch:** Phase 4 with synthetic/public data and a human review session.

At each checkpoint report:

- what was learned or changed;
- what evidence was produced;
- which product decision became easier or safer;
- what remains unknown;
- whether the next phase is authorized.
