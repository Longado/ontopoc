# Incremental EIP Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow `ontology-poc-generator` from a deterministic proposal CLI into a new, independently implemented EIP that turns one business decision into a sourced, reviewable, executable, versioned, and correctable decision-ontology pack.

**Architecture:** Keep one dependency-light domain core and extend a single synthetic decision slice through seven gated vertical loops. The old `nano-ontoprompt` repository is a behavior reference, not a code source or runtime dependency; each borrowed mechanism is restated as a local contract, implemented minimally, and proven by local tests before the next loop begins.

**Tech Stack:** Python 3.11+ standard library first, frozen dataclasses, Enum, JSON/JSONL, hashlib, argparse, pathlib, unittest; add FastAPI and persistence only after their loop has an accepted user-facing need.

---

## 1. Product anchor

The repository keeps its current name during reconstruction, but the product target changes:

> Compile one real business decision into a `DecisionPack` whose ontology, rules, evidence, human decisions, versions, and follow-up actions can be inspected and replayed.

The current proposal document becomes one projection of the pack. It is no longer the product's authoritative object.

The north-star path is:

```text
raw scenario
-> sourced modeling suggestions
-> reviewed DecisionPack
-> executable OntologySpec
-> synthetic facts and deterministic validation
-> findings and human verdict
-> versioned publication
-> controlled action task and result receipt
-> correction returned to the pack and knowledge source
```

The first complete path uses a clearly marked `synthetic_demo` dairy R&D decision: after consumer testing, the R&D owner decides whether to retain, supplement, or return a candidate experiment direction and assigns the next task. The supply-chain exception example remains a regression input to detect industry hard-coding; it is not proof that the method is cross-industry.

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
| 1 — Knowledge-assisted DecisionPack | Can it contribute useful modeling knowledge beyond the input? | versioned knowledge units, sourced candidate suggestions, immutable `DecisionPack` | every suggestion has source, applicability, input binding, and candidate status; no match yields information insufficiency |
| 2 — Executable ontology kernel | Can a confirmed pack become a machine-checkable ontology specification? | stable IDs, explicit object/relation/rule references, reference closure, deterministic compiler | same pack produces byte-stable spec; dangling references and candidate leakage fail loudly |
| 3 — Stateless validation runtime | Can the new EIP evaluate a synthetic case without persistence or side effects? | inline facts, T-Box checks, initial rule kinds, four-state results, checksum-bound receipt | one dairy case produces traceable results and zero writes/actions |
| 4 — Review, version, publish | Can people correct the model and understand what changed? | append-only review, confirmed projection, canonical checksum, semantic diff, local publish gate | review can be replayed; stale base fails; only confirmed content is published |
| 5 — Data mapping and lineage | Can the ontology explain which source rows support each fact and result? | CSV/JSON dataset version, explicit mapping, row lineage, reproducible expansion | same dataset+mapping reproduces facts; missing keys fail; finding traces to source rows |
| 6 — Decision and controlled action | Can validation support a governed business decision instead of ending at a rule result? | finding, verdict, action contract, approval, internal task, result receipt, feedback | no action before approval; before/after and failure are retained; no external writeback |
| 7 — Service and extensibility | Can the verified core be exposed without weakening its contracts? | capability manifest, stateless API, repository port, optional adapters | API and CLI share the same application service; capability claims derive from tested behavior |

Loops 0–4 form the first demonstrable new EIP product. Loops 5–7 expand it toward an enterprise platform only after the earlier gates pass.

This file owns the program sequence, cross-loop contracts, and stop rules. Before a loop enters `in_progress`, create a dated loop-specific implementation plan with the exact API produced by the preceding loop, 2–5 minute TDD steps, focused commands, and commit boundaries. Do not freeze detailed code for later loops before their input contract exists; new findings amend this master plan and the next loop plan, never silently rewrite completed-loop evidence.

## 4. Target file ownership

Introduce files only when their loop starts:

```text
src/ontology_poc_generator/
├── models.py                 existing intake and Proposal compatibility
├── generator.py              temporary compatibility facade
├── renderers.py              projections only
├── identity.py               Loop 1 stable content and element identity
├── knowledge.py              Loop 1 knowledge source/unit/suggestion contracts
├── decision_pack.py          Loop 1 authoritative aggregate
├── compiler.py               Loop 1 intake + knowledge -> DecisionPack
├── ontology_spec.py          Loop 2 executable T-Box/rule specification
├── spec_compiler.py          Loop 2 confirmed DecisionPack -> OntologySpec
├── validation.py             Loop 2 structural and reference validation
├── facts.py                  Loop 3 typed inline facts
├── tbox.py                   Loop 3 class/relation conformance
├── rule_eval.py              Loop 3 deterministic four-state evaluation
├── receipts.py               Loop 3 validation receipt
├── review.py                 Loop 4 append-only human decisions
├── versioning.py             Loop 4 canonical checksum and semantic diff
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

## 6. Loop 1 — Knowledge-assisted DecisionPack

### Task 1.1: Define the knowledge contract

**Files:**

- Create: `src/ontology_poc_generator/knowledge.py`
- Create: `tests/test_knowledge.py`
- Create: `knowledge/dairy_rnd/post_consumer_direction_v1.json`

- [ ] Define immutable `SourceRef`, `KnowledgeUnit`, and `KnowledgeSuggestion` records.
- [ ] Restrict source kinds to authoritative reference, implemented artifact, observed case, practitioner note, and synthetic example.
- [ ] Validate that every unit has a version/hash, applicability condition, structured payload, source, and caveat policy.
- [ ] Reject practitioner notes that emit confirmed facts, customer results, numeric thresholds, or executable rules.
- [ ] Prove the same input and knowledge-pack version produce byte-stable suggestions.
- [ ] Commit as `feat: define versioned knowledge units`.

Minimum record shape:

```python
@dataclass(frozen=True)
class KnowledgeSuggestion:
    suggestion_id: str
    unit_id: str
    unit_version: str
    applicability: str
    contribution_type: str
    semantic_key: str
    payload: Mapping[str, object]
    input_bindings: tuple[str, ...]
    source_refs: tuple[str, ...]
    governance_status: str = "candidate"
```

### Task 1.2: Add deterministic applicability matching

**Files:**

- Modify: `src/ontology_poc_generator/knowledge.py`
- Create: `tests/test_knowledge_matching.py`

- [ ] Match only controlled normalized fields; do not use embeddings or an LLM.
- [ ] Return `applicable`, `not_applicable`, or `insufficient_information`.
- [ ] Add a dairy R&D unit that distinguishes a consumer-test observation, a candidate experiment direction, and the R&D owner's retain/supplement/return decision.
- [ ] Suggest only candidate relations, minimum evidence requirements, and acceptance questions; never suggest a real formula, BOM, material quantity, production conclusion, or customer result.
- [ ] Prove the supply-chain regression input does not match the dairy unit.
- [ ] Commit as `feat: match sourced modeling suggestions`.

### Task 1.3: Build the authoritative DecisionPack

**Files:**

- Create: `src/ontology_poc_generator/identity.py`
- Create: `src/ontology_poc_generator/decision_pack.py`
- Create: `src/ontology_poc_generator/compiler.py`
- Create: `tests/test_decision_pack.py`
- Create: `tests/test_compiler.py`
- Modify: `src/ontology_poc_generator/generator.py`
- Modify: `src/ontology_poc_generator/renderers.py`

- [ ] Define the pack's scene, decision, actor, object, relation, rule, data requirement, acceptance case, and action-contract elements.
- [ ] Give each element a stable ID, semantic key, source references, and governance status.
- [ ] Compile customer input and knowledge suggestions without converting suggestions to confirmed facts.
- [ ] Project the existing Proposal and Markdown from the pack without renderer inference.
- [ ] Prove that label changes do not break references and that unknown references fail.
- [ ] Commit as `feat: compile sourced decision packs`.

## 7. Loop 2 — Executable ontology kernel

### Task 2.1: Define the local OntologySpec

**Files:**

- Create: `src/ontology_poc_generator/ontology_spec.py`
- Create: `tests/test_ontology_spec.py`

- [ ] Define entity types, relation types, property types, rule declarations, and non-executing action contracts.
- [ ] Require explicit domain, range, identifiers, and rule input bindings.
- [ ] Reject dangling references, duplicate semantic keys, invalid self-relations, and unbound rule inputs.
- [ ] Keep the schema local; do not copy the old EIP `OntologySpec` field layout.
- [ ] Commit as `feat: define executable ontology specification`.

### Task 2.2: Compile confirmed content only

**Files:**

- Create: `src/ontology_poc_generator/spec_compiler.py`
- Create: `src/ontology_poc_generator/validation.py`
- Create: `tests/test_spec_compiler.py`
- Create: `tests/test_validation.py`

- [ ] Reject compilation when required elements remain candidate, rejected, or information-insufficient.
- [ ] Compile stable DecisionPack IDs into stable OntologySpec keys.
- [ ] Produce structured validation issues with path, code, message, and severity.
- [ ] Prove the same confirmed pack produces byte-identical canonical JSON.
- [ ] Commit as `feat: compile confirmed packs into ontology specs`.

## 8. Loop 3 — Stateless validation runtime

### Task 3.1: Add typed synthetic facts and conformance

**Files:**

- Create: `src/ontology_poc_generator/facts.py`
- Create: `src/ontology_poc_generator/tbox.py`
- Create: `tests/test_facts.py`
- Create: `tests/test_tbox.py`
- Create: `tests/fixtures/dairy_rnd/ontology_spec.json`
- Create: `tests/fixtures/dairy_rnd/facts.json`

- [ ] Load inline facts marked `synthetic_demo`.
- [ ] Validate entity type, identifier, property type, relation domain/range, and referenced endpoints.
- [ ] Return all issues without modifying the fact set.
- [ ] Prove invalid facts cannot reach rule evaluation.
- [ ] Commit as `feat: validate typed synthetic facts`.

### Task 3.2: Implement the first rule kinds and four states

**Files:**

- Create: `src/ontology_poc_generator/rule_eval.py`
- Create: `tests/test_rule_eval.py`

- [ ] Implement only the rule kinds required by the golden dairy slice.
- [ ] Return exactly `pass`, `fail`, `not_evaluable`, or `unsupported`.
- [ ] Bind each result to rule ID, input fact IDs, missing inputs, and reason.
- [ ] Prove unsupported is not converted into not-evaluable or a data gap.
- [ ] Commit as `feat: evaluate deterministic ontology rules`.

### Task 3.3: Produce an immutable ValidationReceipt

**Files:**

- Create: `src/ontology_poc_generator/receipts.py`
- Create: `tests/test_receipts.py`
- Modify: `src/ontology_poc_generator/cli.py`

- [ ] Bind the receipt to pack, spec, and fact checksums.
- [ ] Include T-Box issues, rule results, and explicit side-effect flags.
- [ ] Add a CLI command that validates local fixtures in memory.
- [ ] Assert `draft_created=false`, `published=false`, `actions_executed=false`, and `external_write=false`.
- [ ] Commit as `feat: add stateless validation receipts`.

## 9. Loop 4 — Review, version, and publish

### Task 4.1: Add immutable draft versions and semantic diff

**Files:**

- Create: `src/ontology_poc_generator/versioning.py`
- Create: `tests/test_versioning.py`

- [ ] Canonicalize pack JSON and calculate SHA-256 checksums.
- [ ] Diff by stable element ID, not array order or JSON line.
- [ ] Include knowledge-pack version, source, status, and review changes.
- [ ] Reject stale-base revisions.
- [ ] Commit as `feat: version and diff decision packs`.

### Task 4.2: Add version-bound append-only human review

**Files:**

- Create: `src/ontology_poc_generator/review.py`
- Create: `tests/test_review.py`

- [ ] Record exact pack version/checksum, subject ID and subject checksum, reviewer role, prior status, verdict, reason, and caller-supplied timestamp.
- [ ] Replay records deterministically against only the version they reviewed.
- [ ] Reject unauthorized transitions, unknown bases, and attempts to apply an old review to changed subject content.
- [ ] Prove changing a label retains the element ID but invalidates review only when the reviewed subject checksum changes.
- [ ] Commit as `feat: record version-bound ontology review`.

### Task 4.3: Add a confirmed-only local publication gate

**Files:**

- Create: `src/ontology_poc_generator/publication.py`
- Create: `tests/test_publication.py`
- Modify: `src/ontology_poc_generator/cli.py`

- [ ] Export a draft review package and a confirmed publication package as separate types.
- [ ] Block publication when required content is candidate, rejected, insufficient, unsupported, or not evaluable.
- [ ] Include manifest, checksums, open issues, generator version, and produced files.
- [ ] Demonstrate one review-return-revise-confirm-publish journey.
- [ ] Commit as `feat: publish confirmed decision packs`.

## 10. Loop 5 — Data mapping and lineage

### Task 5.1: Version one local dataset

**Files:**

- Create: `src/ontology_poc_generator/datasets.py`
- Create: `tests/test_datasets.py`
- Create: `tests/fixtures/dairy_rnd/data/`

- [ ] Support local CSV and JSON only.
- [ ] Record content checksum, schema summary, row count, and source classification.
- [ ] Reject mutable overwrite of an existing dataset version.
- [ ] Commit as `feat: version local ontology datasets`.

### Task 5.2: Map rows to ontology facts

**Files:**

- Create: `src/ontology_poc_generator/mappings.py`
- Create: `tests/test_mappings.py`

- [ ] Define explicit source table, key column, label column, property bindings, and relation bindings.
- [ ] Expand facts without database writes.
- [ ] Fail on missing keys, duplicate identities, invalid coercion, and unknown ontology targets.
- [ ] Commit as `feat: expand mapped ontology facts`.

### Task 5.3: Preserve row-level lineage

**Files:**

- Create: `src/ontology_poc_generator/lineage.py`
- Create: `tests/test_lineage.py`
- Modify: `src/ontology_poc_generator/receipts.py`

- [ ] Connect source row, mapped fact, rule result, and finding IDs.
- [ ] Make coverage claims reproducible from returned lineage records.
- [ ] Prove that a finding cannot claim evidence from an unmapped row.
- [ ] Commit as `feat: trace findings to source rows`.

## 11. Loop 6 — Decision and controlled action

### Task 6.1: Separate rule results, findings, and verdicts

**Files:**

- Create: `src/ontology_poc_generator/decisions.py`
- Create: `tests/test_decisions.py`

- [ ] Produce candidate findings from rule results without treating them as human decisions.
- [ ] Record verdict, reviewer, evidence references, and reasoning.
- [ ] Keep rejected findings and their reasons in history.
- [ ] Commit as `feat: govern ontology findings and verdicts`.

### Task 6.2: Add controlled internal action tasks

**Files:**

- Create: `src/ontology_poc_generator/actions.py`
- Create: `tests/test_actions.py`

- [ ] Define action contract, proposed parameters, approver, internal assignee, before snapshot, status, result, and failure reason.
- [ ] Prove no action is created before an approved verdict and no action runs before explicit approval.
- [ ] Record result receipt and feed a correction event back to the DecisionPack history.
- [ ] Keep ERP/MES/CRM writeback outside this loop.
- [ ] Commit as `feat: add approved internal action loop`.

## 12. Loop 7 — Service and extensibility

### Task 7.1: Extract shared application services

**Files:**

- Create: `src/ontology_poc_generator/application.py`
- Create: `src/ontology_poc_generator/repositories.py`
- Modify: `src/ontology_poc_generator/cli.py`
- Create: `tests/test_application.py`

- [ ] Define use cases for compile, validate, review, version, publish, map, decide, and approve.
- [ ] Keep repository and clock interfaces explicit.
- [ ] Prove CLI behavior uses the same services as programmatic callers.
- [ ] Commit as `refactor: expose verified eip application services`.

### Task 7.2: Add a minimal capability-derived API

**Files:**

- Create: `src/ontology_poc_generator/api.py`
- Create: `tests/test_api.py`
- Modify: `pyproject.toml` only if FastAPI is selected at this gate.

- [ ] Add endpoints only for already verified application use cases.
- [ ] Generate a capability manifest from registered, tested behaviors rather than a handwritten promise list.
- [ ] Prove API and CLI return the same checksums and domain result for the golden fixture.
- [ ] Keep authentication, multi-tenancy, queues, Web UI, and production database in later plans.
- [ ] Commit as `feat: expose verified eip capabilities`.

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

- generate the dairy golden artifact and inspect status, source, and capability language;
- run the supply-chain regression and search production code for industry-name branches;
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
- candidate content reaches an executable or published projection;
- `unsupported` is represented as missing data;
- a new EIP capability requires copying an old subsystem to make progress;
- three real design sessions fail to produce a reusable, accepted correction pattern.

The last condition triggers a product review: keep the repository as an internal design tool unless evidence supports continued platform expansion.

## 16. First execution handoff

Loop 0 已完成：当前全量 unittest 为 25 项通过；乳品研发与供应链异常双样例仅作为 CLI smoke / regression，证明输出不再由对象顺序补造关系、能保留状态与边界，不能证明跨行业有效或形成知识建议。当前知识增益仍为零。Loop 1 仅处于 `ready_to_plan`，下一步先写出 Loop 1 的详细实施计划；在该计划通过前，不实现 Loop 1，也不启动后续 Loop。
