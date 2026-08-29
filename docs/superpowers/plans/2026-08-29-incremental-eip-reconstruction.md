# Incremental EIP Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow `ontology-poc-generator` from a deterministic proposal CLI into a new, independently implemented EIP that turns one business decision into a sourced, reviewable, executable, versioned, and correctable decision-ontology pack.

**Architecture:** Keep one dependency-light domain core and extend a single synthetic decision slice through seven gated vertical loops. The old `nano-ontoprompt` repository is a behavior reference, not a code source or runtime dependency; each borrowed mechanism is restated as a local contract, implemented minimally, and proven by local tests before the next loop begins.

**Tech Stack:** Python 3.11+ standard library first, frozen dataclasses, Enum, JSON/JSONL, hashlib, argparse, pathlib, unittest; add FastAPI and persistence only after their loop has an accepted user-facing need.

---

## 1. Product anchor

The repository keeps its current name during reconstruction. Its vision is **Persistent AI FDE**, its product mechanism is **AI FDE Decision Compiler**, and its durable asset is the immutable `DecisionPack`:

> 把客户的一个业务决策，编译成有来源、可验证、可审查、可发布并能持续修正的决策资产。

The current proposal document becomes one projection of the pack. It is no longer the product's authoritative object.

The north-star path is:

```text
raw scenario
-> sourced modeling suggestions
-> candidate DecisionPack
-> draft OntologySpec
-> candidate/draft ValidationReceipt on synthetic facts
-> review, confirm, and publish the baseline
-> revised candidate pack/spec/receipt
-> DecisionDelta against the published baseline
-> review and publish the next version
-> controlled action task and result receipt
-> correction returned to the pack and knowledge source
```

The first complete path uses a clearly marked `synthetic_demo` supply-chain decision: **which orders enter the priority intervention queue** after supplier promise, material relation, or queue policy changes. Selecting an intervention action is a separate decision and remains out of the golden pack until Loop 6. The dairy R&D example becomes a cross-industry regression input to detect hard-coding; it is not proof that the method is cross-industry.

The product moment is `DecisionDelta`: it compares published and candidate `ValidationReceipt` objects and explains which orders entered or left the queue, remained in the queue, or became information-insufficient, with the rule and evidence basis for each change.

## 2. Reconstruction rules

### 2.1 Learn from EIP without copying it

Allowed:

- inspect an EIP behavior, schema, test, or failure mode;
- record the mechanism and reason in `docs/DISCOVERY_LOG.md`;
- express the required behavior as a repository-local test and fixture;
- implement the smallest local design that passes that contract;
- cite the old repository path in an ADR or discovery entry when it affected a decision.

Forbidden:

- copying complete EIP modules, ORM models, migrations, routers, pages, or directory structure;
- importing `nano-ontoprompt` as a Python or runtime dependency;
- sharing its database or assuming its route contract is stable;
- preserving old names merely to make copied code fit;
- claiming parity because a local type resembles an EIP type.

The old EIP stops being authoritative as soon as the new repository has an accepted local contract for that behavior.

### 2.2 Commit discipline

Every commit must answer one reviewable question and leave the full suite green. A normal loop uses several small commits:

1. contract and failing test;
2. minimum implementation;
3. golden fixture or projection;
4. loop evidence and roadmap update.

Do not commit a bulk subsystem import. Do not mix documentation re-anchoring, domain behavior, persistence, and API work in one commit. Push each verified commit when GitHub progress sharing is enabled.

### 2.3 Walking-skeleton discipline

After Loop 2, every loop must preserve one runnable vertical path. A loop is not complete because its classes exist; it is complete only when the golden `DecisionPack` travels through the new behavior and produces inspectable evidence.

## 3. Loop map

| Loop | Product question | Minimum deliverable | Exit evidence |
|---|---|---|---|
| 0 — Truthful baseline | Can the product stop inventing knowledge from input order? | strict input/status model, removal of adjacent-object inference, explicit limitations | object reordering does not change relations; unavailable remains unavailable; no false runtime claims |
| 1 — Knowledge-assisted DecisionPack | Can it contribute useful modeling knowledge beyond the input? | stable source/suggestion identity, sourced candidate suggestions, immutable `DecisionPack` | every suggestion has fixed source snapshot, applicability, input binding, and candidate status; not-applicable and insufficient-information remain distinct |
| 2 — Executable ontology kernel | Can a pack become a machine-checkable draft ontology specification? | explicit object/relation/rule references, reference closure, deterministic compiler | same pack produces byte-stable spec; dangling references and governance-status loss fail loudly |
| 3 — Stateless validation runtime | Can the new EIP evaluate a synthetic case without persistence or side effects? | inline facts, T-Box checks, initial rule kinds, four-state results, content-hash-bound receipt | one supply-chain case produces traceable results and zero writes/actions |
| 4 — Decision change, review, publish | Can people correct the model and understand what business conclusions changed? | append-only review, confirmed projection, semantic diff, `DecisionDelta`, local publish gate | receipt delta explains changed order conclusions; review can be replayed; stale base fails; only confirmed content is published |
| 5 — Data mapping and lineage | Can the ontology explain which source rows support each fact and result? | CSV/JSON dataset version, explicit mapping, row lineage, reproducible expansion | same dataset+mapping reproduces facts; missing keys fail; finding traces to source rows |
| 6 — Decision and controlled action | Can validation support a governed business decision instead of ending at a rule result? | finding, verdict, action contract, approval, internal task, result receipt, feedback | no action before approval; before/after and failure are retained; no external writeback |
| 7 — Service and extensibility | Can the verified core be exposed without weakening its contracts? | capability manifest, stateless API, repository port, optional adapters | API and CLI share the same application service; capability claims derive from tested behavior |

Loops 0–4 form the first demonstrable AI FDE MVP. Loop 4 is a product-validation gate: Loops 5–7 remain blocked unless one real FDE and one supply-chain business validation participant jointly record a `go` after correcting, approving, or reusing a `DecisionDelta`.

This file owns the program sequence, cross-loop contracts, and stop rules. Before a loop enters `in_progress`, create a dated loop-specific implementation plan with the exact API produced by the preceding loop, 2–5 minute TDD steps, focused commands, and commit boundaries. Do not freeze detailed code for later loops before their input contract exists; new findings amend this master plan and the next loop plan, never silently rewrite completed-loop evidence.

## 4. Target file ownership

Introduce files only when their loop starts:

```text
src/ontology_poc_generator/
├── models.py                 existing intake and Proposal compatibility
├── generator.py              temporary compatibility facade
├── renderers.py              projections only
├── identity.py               Loop 1 stable source, binding, suggestion, and pack content identity
├── knowledge.py              Loop 1 knowledge source/unit/suggestion contracts
├── decision_pack.py          Loop 1 authoritative aggregate
├── compiler.py               Loop 1 intake + knowledge -> DecisionPack
├── ontology_spec.py          Loop 2 executable T-Box/rule specification
├── spec_compiler.py          Loop 2 DecisionPack -> status-preserving draft OntologySpec
├── validation.py             Loop 2 structural and reference validation
├── facts.py                  Loop 3 typed inline facts
├── tbox.py                   Loop 3 class/relation conformance
├── rule_eval.py              Loop 3 deterministic four-state evaluation
├── receipts.py               Loop 3 validation receipt
├── review.py                 Loop 4 append-only human decisions
├── versioning.py             Loop 4 version/base lifecycle and semantic diff
├── decision_delta.py         Loop 4 receipt-to-business-change comparison
├── publication.py            Loop 4 confirmed-only local publication
├── datasets.py               Loop 5 dataset identity and version
├── mappings.py               Loop 5 source-to-ontology mapping
├── lineage.py                Loop 5 row-to-fact-to-result trace
├── decisions.py              Loop 6 findings and verdicts
├── actions.py                Loop 6 action contracts, approvals, receipts
├── application.py            Loop 7 shared use cases
├── api.py                    Loop 7 HTTP adapter
└── repositories.py           Loop 7 persistence ports
```

Rules:

- renderers never create facts, relations, rules, findings, or capability claims;
- the compiler never upgrades a candidate to confirmed;
- rule evaluation has no database, network, LLM, or action dependency;
- publication is a governance state transition, not a renderer option;
- mappings identify facts and provenance but cannot silently change ontology semantics;
- action approval and execution are separate records;
- adapters call application services and contain no domain decisions.

## 5. Loop 0 — Truthful baseline

### Task 0.1: Freeze the current evidence boundary

**Files:**

- Modify: `tests/test_generator.py`
- Verify: `tests/test_cli.py`
- Verify: `tests/test_examples.py`

- [x] Add a regression proving that reordering `objects` cannot create different semantic relations.
- [x] Add strict input tests for JSON booleans and data-source status values.
- [x] Add a regression proving `unavailable` is not rendered as `to_confirm`.
- [x] Add projection coverage for known over-commitment phrases and the `current` / `planned` / `candidate` projection boundary; Agent、行动和回执的逐项样例检查另记于 Task 0.3。
- [x] Run `PYTHONPATH=src python -m unittest discover -s tests -v` and confirm the new tests fail for the documented reasons.

Example order-invariance contract:

```python
def test_object_order_does_not_invent_relations(self):
    base = {
        "industry": "供应链",
        "scene_name": "履约风险处置",
        "business_decision": "选择需要优先处置的订单",
        "decision_owner": "计划经理",
        "trigger": "订单交付风险上升时",
        "acceptance_questions": ["能否解释处置依据？"],
    }
    first = ScenarioParameters.from_dict({
        **base,
        "objects": ["供应商", "物料", "订单"],
    })
    second = ScenarioParameters.from_dict({
        **base,
        "objects": ["订单", "供应商", "物料"],
    })
    self.assertEqual(
        generate_proposal(first).relation_candidates,
        generate_proposal(second).relation_candidates,
    )
```

### Task 0.2: Remove false inference and preserve states

**Files:**

- Modify: `src/ontology_poc_generator/models.py`
- Modify: `src/ontology_poc_generator/generator.py`
- Modify: `src/ontology_poc_generator/renderers.py`
- Test: `tests/test_generator.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_examples.py`

- [x] Replace mutable data-source dictionaries with a validated immutable value object.
- [x] Accept only explicit relations; when none exist, return an empty candidate list plus an information gap.
- [x] Preserve `available`, `to_confirm`, and `unavailable` without collapsing them.
- [x] Replace current-runtime promises with `planned` or `requires_validation` language.
- [x] Run focused tests, then the full suite.
- [x] 拆分为三个小提交完成：`0a709f1 fix: preserve validated data source states`、`2b8659f fix: require explicit relation semantics`、`0fc2538 fix: label unimplemented capabilities as planned`。

### Task 0.3: Close the baseline with evidence

**Files:**

- Modify: `docs/ROADMAP.md`
- Modify: `docs/DISCOVERY_LOG.md`

- [x] Generate both current examples into a temporary directory.
- [x] 人工检查双样例，确认其未把规则、Agent、行动、版本或回执写成已执行。
- [x] Run `git diff --check`.
- [x] Record the exact test result and the known zero-knowledge limitation.
- [x] Commit as `docs: close truthful baseline loop`.

## 6. Loop 1 — Sourced supply-chain knowledge and DecisionPack

**Status:** `planned`; implementation has not started.

The authoritative step-by-step plan is [2026-08-29-loop1-sourced-supply-chain-knowledge.md](2026-08-29-loop1-sourced-supply-chain-knowledge.md). Loop 1 owns stable `SourceRef` and suggestion identity, declarative applicability, `KnowledgeOutcome`, and the immutable `DecisionPack`. It does not own Action, rule execution, fact results, review, version, or publication.

Its only knowledge unit separates material-level supplier qualification evidence (`QUALIFIED_TO_SUPPLY`, supported only by ASL/qualification records) from purchase history (`HAS_SUPPLIED`, supported only by PO/receipt/invoice history). “Only bought from A” must never imply “only A is qualified.” The unit may suggest evidence requirements, relation semantics, and acceptance questions, but it does not produce a final queue, risk score, or intervention action.

The matcher is generic: match aliases and role requirements are declared in the knowledge package, never as supply-chain branches in Python. A domain mismatch returns `not_applicable`; missing required semantic roles or an order-to-material bridge returns `insufficient_information`. A missing queue policy remains a structured readiness gap so that the unit can still suggest why that policy is needed. The default CLI loads no unit and preserves Loop 0 behavior; `--knowledge-unit` is explicit opt-in.

## 7. Loop 2 — Executable ontology kernel

**Status:** blocked by Loop 1. Create a dated TDD plan only after the accepted Loop 1 `DecisionPack` contract exists.

**Question:** Can a pack become a machine-checkable local `OntologySpec` without losing stable identity or governance status?

**Owned contract:** entity/relation/property types, explicit domain/range, rule declarations and input bindings, reference closure, structured validation issues, canonical spec serialization and spec content hash. Action is not part of this loop.

Candidate elements may compile only into a clearly marked draft/synthetic spec and must retain candidate status. They cannot be represented as confirmed or published. The later Loop 4 review and publication gate owns the transition to a confirmed publication.

**Exit:** the same pack produces byte-stable draft spec content; label changes do not change semantic IDs; dangling references and status loss fail loudly.

## 8. Loop 3 — Stateless validation runtime

**Status:** blocked by Loop 2. Create a dated TDD plan only after the accepted `OntologySpec` contract exists.

**Question:** Can the new EIP evaluate the golden synthetic supply-chain case with no persistence or side effects?

**Owned contract:** canonical synthetic facts and facts content hash, T-Box conformance, the minimum deterministic rule kinds, exact `pass / fail / not_evaluable / unsupported` states, and an immutable `ValidationReceipt` bound to pack/spec/facts content hashes.

Each decision conclusion needed by the later delta must include stable `decision_scope`, `decision_key`, subject/order ID, conclusion key/value, rule IDs, input fact IDs, missing inputs, and reason. Candidate/draft validation is allowed only when the receipt keeps that status visible.

**Exit:** three synthetic orders produce traceable “in queue / not in queue / information insufficient” conclusions; invalid facts cannot reach evaluation; the receipt declares zero publication, action, and external writes.

## 9. Loop 4 — Review, version, and publish

**Status:** blocked by Loop 3. Create a dated TDD plan only after the accepted receipt contract exists.

**Question:** Can an FDE understand and correct how a model change affects the queue decision, then publish only reviewed content?

**Owned contract:** immutable pack version/base, version-bound append-only review, stable-ID structural semantic diff, stale-base rejection, confirmed-only publication, and `DecisionDelta` comparing published/candidate receipts for the same decision scope. Pack/spec/facts content hashes already come from their producing loops; Loop 4 adds lifecycle identity, not first-time content hashing.

`DecisionDelta` reports orders entering the queue, leaving the queue, remaining in the queue, or becoming information-insufficient, with old/new conclusion, rule and evidence basis. “High risk” is not a second output unless a later accepted contract defines it.

**Exit:** return—revise—review—publish is replayable; old review cannot apply to changed content; only confirmed and successfully validated content publishes.

**Product-validation artifact:** record `delta_id`, delta/receipt hashes, the real-FDE role, the supply-chain business-validation role, correction/approval/reuse evidence, explicit `go` or `no_go`, reason, and timestamp. Only their jointly recorded `go` unlocks Loop 5–7; otherwise stop and re-anchor.

## 10. Loop 5 — Data mapping and lineage

**Status:** blocked by a recorded Loop 4 product-validation `go`.

**Question:** Can the accepted supply-chain decision explain which local source rows support each fact and conclusion?

**Candidate scope:** local CSV/JSON dataset identity, explicit mapping, deterministic fact expansion, and row-to-fact-to-result lineage. Use the supply-chain golden fixture; dairy remains only a no-hard-coding regression. A dated plan is required before implementation.

## 11. Loop 6 — Decision and controlled action

**Status:** blocked by a recorded Loop 4 product-validation `go` and Loop 5.

**Question:** Can a validated queue conclusion become a governed human verdict and controlled internal task?

This is the first loop that may model “which intervention action to take.” It separates rule results, findings, verdicts, approvals, action contracts, internal tasks, result/failure receipts, and feedback. External ERP/MES/CRM writeback remains out of scope. A dated plan is required before implementation.

## 12. Loop 7 — Service and extensibility

**Status:** blocked by a recorded Loop 4 product-validation `go` and Loop 6.

**Question:** Can verified use cases be exposed without weakening their contracts?

**Candidate scope:** shared application services, repository ports, capability-derived API, and CLI/API parity. Web UI, authentication, multi-tenancy, queues, and production database require separate evidence and plans.

## 13. Deferred until a new approved plan

The loop plan does not authorize:

- copying or migrating the old EIP database;
- Neo4j, Chroma, vector search, RAG, or free-form LLM modeling;
- a visual ontology editor or general Web workbench;
- RDF, OWL, SHACL, SPARQL, Ontop, or TypeDB integration;
- production connectors, streaming, background jobs, multi-tenancy, or RBAC;
- automatic external action execution;
- a marketplace of industry packs;
- customer effectiveness claims based on synthetic data.

These can enter only when a completed loop exposes a concrete limitation and a new plan defines a user-visible acceptance condition.

## 14. Cross-loop verification

Run at every task boundary:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
git diff --check
git status --short
```

At every loop boundary also:

- generate the supply-chain golden artifact and inspect status, source, and capability language;
- run the dairy regression and search production code for industry-name branches;
- record exact tests, artifacts, invalidated assumptions, and next-loop gate in `docs/ROADMAP.md`;
- record the EIP or external mechanism reviewed in `docs/DISCOVERY_LOG.md`;
- ensure every changed file directly supports the loop;
- commit the evidence separately from the implementation when it improves reviewability.

## 15. Stop and re-anchor conditions

Stop the active loop when:

- output information still equals normalized input plus fixed prose;
- a customer-facing claim has no source or explicit unknown state;
- a renderer invents a fact absent from the DecisionPack;
- an ontology result cannot be tied to spec and data checksums;
- candidate content is represented as confirmed, reaches publication, or is validated without an explicit draft/candidate marker;
- `unsupported` is represented as missing data;
- a new EIP capability requires copying an old subsystem to make progress;
- three real design sessions fail to produce a reusable, accepted correction pattern.

The last condition triggers a product review: keep the repository as an internal design tool unless evidence supports continued platform expansion.

## 16. First execution handoff

Loop 0 已完成：当前全量 unittest 为 25 项通过；双样例仅作为 CLI smoke / regression，不能证明跨行业有效或形成知识建议。当前知识增益仍为零。Loop 1 的详细实施计划已经建立，状态为 `planned`，尚未开始实现。下一步按该计划从失败测试和固定 source snapshot 开始；不得把计划存在写成 Loop 1 已完成，也不得提前进入 Loop 2。
