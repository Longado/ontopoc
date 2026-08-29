# Loop 1 — Sourced Supply-Chain Knowledge and DecisionPack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `subagent-driven-development` or `executing-plans`; implement one task at a time with TDD and review each commit before continuing.

**Status:** `in_progress`; Task 1 accepted at `f49087e`; Task 2 accepted at `341a8bd` with 48 tests passing; Task 3 is in progress.

**Goal:** When a user explicitly loads one supply-chain knowledge unit, compile the current scenario into an immutable `DecisionPack` containing input-external, source-backed `candidate` suggestions. The first unit must distinguish supplier qualification from purchase history without producing an order queue, score, or action.

**Architecture:** Keep `ScenarioParameters -> Proposal -> renderer` as a compatibility path. Add a dependency-free knowledge loader and generic declarative matcher, compile `ScenarioParameters + KnowledgeOutcome[]` into a frozen `DecisionPack`, and project the existing `Proposal` from that pack. The knowledge package owns domain vocabulary and applicability; core Python contains no supply-chain or dairy branch.

**Tech stack:** Python 3.11+ standard library, frozen dataclasses, Enum, JSON, SHA-256, argparse, pathlib, unittest.

---

## 1. Current evidence and product boundary

Loop 0 is merged on `main` at `571ff72` with 25 passing tests. The current CLI is truthful but has zero knowledge gain: it only projects explicit input and reports relation information insufficiency when no relation is supplied.

Loop 1 answers one question:

> Can the compiler add a useful modeling distinction that was absent from the input, while showing exactly why it suggested it and when it cannot apply?

The golden decision is:

> Which orders enter the priority intervention queue?

The first unit does not answer that decision. It contributes only the evidence semantics and minimum information needed before a later executable rule could answer it.

### Exit conditions

1. Explicitly loading the unit adds at least one structured suggestion absent from `examples/supply_chain_exception.json`.
2. Every suggestion is `candidate` and includes stable suggestion identity, unit ID/version/hash, fixed source snapshot, caveat, applicability, and stable input bindings.
3. `QUALIFIED_TO_SUPPLY` is supported only by a material-level ASL/qualification source; `HAS_SUPPLIED` is supported only by purchase/receipt/invoice history.
4. The compiler never turns “only bought from A” into “only A is qualified.”
5. A domain mismatch returns `not_applicable`; a matching decision missing required roles or the order-to-material bridge returns `insufficient_information`. A missing queue policy remains a structured readiness gap and does not suppress otherwise useful suggestions.
6. Reordering input objects does not change suggestions or IDs.
7. Default CLI behavior remains the Loop 0 baseline; knowledge is opt-in through `--knowledge-unit`.
8. The existing dairy example remains a regression input and receives no supply-chain suggestions.

### Non-goals

- No final priority queue, risk score, numeric threshold, supplier selection, expediting, replanning, logistics change, or task creation.
- No executable `OntologySpec`, T-Box, rule expression, fact evaluation, or four-state `ValidationReceipt`.
- No review record, pack version/base, semantic diff, `DecisionDelta`, publication, or persistence.
- No LLM, RAG, embeddings, vector store, web UI, database, API, ERP/MES/CRM connector, or external write.
- No claim that the old EIP artifact is a customer fact, authoritative industry standard, production rule, or validated outcome.

---

## 2. Minimum contracts

The exact implementation may refine names during TDD, but it must preserve these responsibilities:

```python
class SourceKind(str, Enum):
    PROVIDED_INPUT = "provided_input"
    AUTHORITATIVE_REFERENCE = "authoritative_reference"
    IMPLEMENTED_ARTIFACT = "implemented_artifact"
    OBSERVED_CASE = "observed_case"
    PRACTITIONER_NOTE = "practitioner_note"
    SYNTHETIC_EXAMPLE = "synthetic_example"


class MatchStatus(str, Enum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_INFORMATION = "insufficient_information"


@dataclass(frozen=True)
class InputBinding:
    binding_id: str
    semantic_key: str
    label: str


@dataclass(frozen=True)
class SourceRef:
    source_ref_id: str
    source_kind: SourceKind
    title: str
    locator: str
    revision: str
    snapshot_sha256: str
    caveat: str


@dataclass(frozen=True)
class KnowledgeSuggestion:
    suggestion_id: str
    unit_id: str
    unit_version: str
    unit_content_hash: str
    contribution_type: str
    semantic_key: str
    payload: tuple[tuple[str, str], ...]
    input_binding_ids: tuple[str, ...]
    source_ref_ids: tuple[str, ...]
    governance_status: str = "candidate"


@dataclass(frozen=True)
class KnowledgeOutcome:
    unit_id: str
    unit_version: str
    unit_content_hash: str
    match_status: MatchStatus
    reason_code: str
    input_binding_ids: tuple[str, ...]
    suggestions: tuple[KnowledgeSuggestion, ...]


@dataclass(frozen=True)
class DecisionPack:
    schema: str
    scenario: ScenarioParameters
    input_bindings: tuple[InputBinding, ...]
    source_refs: tuple[SourceRef, ...]
    knowledge_outcomes: tuple[KnowledgeOutcome, ...]
```

Constraints:

- `DecisionPack` is the authoritative Loop 1 aggregate; `Proposal` is a compatibility projection.
- `binding_id` and `suggestion_id` derive from stable decision/object semantic keys; labels are display-only and never enter identity seeds. They never use array position, time, or randomness.
- The loader computes `unit_content_hash` from canonical JSON; the JSON does not contain a self-referential hash.
- Loop 1 provides canonical `DecisionPack` serialization and a pack content hash function. The hash is returned beside the pack rather than stored inside self-referential content. Loop 4 later adds version/base lifecycle identity.
- `payload` is immutable and deterministically ordered. It may carry relation semantics, natural-language constraints, data requirements, and acceptance questions, but never executable rules or results.
- Source references prove provenance only. They do not prove customer applicability, business truth, or production effectiveness.
- The compiler never upgrades `candidate` to `confirmed`.

---

## 3. First knowledge unit

Create:

- `knowledge/supply_chain/supplier_evidence_boundary_v1.json`
- `knowledge/supply_chain/sources/supplier_evidence_boundary_v1.md`

Identity:

```text
unit_id: supply_chain.order_priority.supplier_evidence_boundary
unit_version: 1.0.0
decision_key: order_priority_intervention
```

The package declares, rather than Python hard-codes:

- required semantic roles: `customer_order`, `material`, `supplier`;
- required bridge: `customer_order REQUIRES material`;
- readiness requirement: business policy describing evidence sufficient for queue entry;
- contribution templates and stable semantic keys;
- mismatch and insufficiency reason codes.

The first suggestions are limited to:

- candidate relation semantics: `supplier QUALIFIED_TO_SUPPLY material`;
- candidate relation semantics: `supplier HAS_SUPPLIED material`;
- candidate constraint: purchase history cannot be promoted to supplier qualification;
- candidate data requirement: material-level qualification status, validity, scope, and snapshot completeness;
- candidate data requirement: order-to-material dependency and cross-source identity mapping;
- candidate acceptance question: when qualification data is absent, does the result stay information-insufficient instead of reporting zero qualified alternatives?
- candidate readiness gap: the queue policy still requires business confirmation before any final order conclusion can exist.

### Fixed behavior references

The unit may learn behavior from these local snapshots, without copying their code:

| Source | Kind | Snapshot SHA-256 | What it supports | Caveat |
|---|---|---|---|---|
| `nano-ontoprompt/backend/app/eip_extensions/quality/vocabulary.yaml`, lines 19–32 | `implemented_artifact` | `1e8b7bf0a128f716d55ab438a0830959dadd15cebcc91e576eee67e2ffd71425` | `SUPPLIES` qualification semantics and `HAS_SUPPLIED` purchase-history semantics | First-party implementation snapshot, not a customer fact or industry standard |
| `nano-ontoprompt/backend/tests/test_eip_supply_chain_risk.py`, qualification/history cases | `synthetic_example` | `a937a6b085733766b09ff5f40468ef9e9b1182c946d1cff9a201947111d27ed8` | “Bought from one” is different from “only one qualified”; unknown is not zero | Synthetic test behavior, not a production outcome |

The readable source note must record repository, path, fragment, hash, supported suggestion IDs, and caveat. The new repository has no runtime dependency on the old repository.

---

## 4. Task 1 — Define and validate the source/knowledge contract

**Files:**

- Create: `src/ontology_poc_generator/knowledge.py`
- Modify: `src/ontology_poc_generator/errors.py`
- Create: `tests/test_knowledge.py`

### TDD steps

- [ ] Add a failing import test for `SourceKind`, `SourceRef`, `KnowledgeUnit`, `KnowledgeSuggestion`, and `KnowledgeValidationError`.
- [ ] Run `PYTHONPATH=src python -m unittest tests.test_knowledge -v`; confirm failure is the missing contract.
- [ ] Implement frozen source and knowledge value objects with non-empty field validation.
- [ ] Add failing tests for an unknown source kind, missing version, missing caveat, invalid SHA-256, duplicate source IDs, and a template referencing an unknown source.
- [ ] Implement the minimum validation needed for those tests.
- [ ] Add failing tests that reject non-candidate templates and executable/result payload keys such as `threshold`, `expression`, `result`, `action`, or `writeback`.
- [ ] Implement the explicit forbidden-key guard; do not add a general policy engine.
- [ ] Add a test proving raw mutable dictionaries cannot mutate an accepted unit.
- [ ] Run focused tests, then `PYTHONPATH=src python -m unittest discover -s tests -v` and `git diff --check`.
- [ ] Commit: `feat: define sourced knowledge contracts`.

---

## 5. Task 2 — Load the fixed supplier-evidence unit

**Files:**

- Create: `knowledge/supply_chain/supplier_evidence_boundary_v1.json`
- Create: `knowledge/supply_chain/sources/supplier_evidence_boundary_v1.md`
- Modify: `src/ontology_poc_generator/knowledge.py`
- Modify: `tests/test_knowledge.py`

### TDD steps

- [x] Add a failing loader test for the exact unit ID, version, source IDs, contribution types, and stable template order.
- [x] Add a failing test that repeated loads produce the same canonical content hash.
- [x] Add a failing test that changing package content without changing the expected source snapshot is visible through a different unit hash.
- [x] Write the readable source note with the two exact snapshot hashes and caveats above.
- [x] Write the declarative JSON package; keep industry vocabulary out of Python.
- [x] Implement `load_knowledge_unit(path)` and canonical JSON SHA-256 using standard library only.
- [x] Add a test proving the loader does not read or import the old EIP repository at runtime.
- [x] Run focused tests, full tests, and `git diff --check`.
- [x] Commit: `feat: add supplier evidence knowledge unit` (`341a8bd`; 48 tests passing).

---

## 6. Task 3 — Match applicability without industry branches

**Files:**

- Modify: `src/ontology_poc_generator/knowledge.py`
- Create: `src/ontology_poc_generator/identity.py`
- Create: `tests/test_knowledge_matching.py`
- Create: `tests/test_identity.py`
- Modify: `examples/supply_chain_exception.json`
- Modify: `src/ontology_poc_generator/models.py`
- Modify: `tests/test_generator.py`

### TDD steps

- [ ] Narrow the golden sample's main decision to “哪些订单进入优先干预队列”; keep desired actions only as legacy planned context.
- [ ] Add optional controlled semantic input required by the matcher: `decision_key`, object-role bindings, declared bridges, and queue-policy status. Each role receives a stable semantic key and binding ID independent of label. Preserve legacy positional construction and default CLI behavior.
- [ ] Add failing identity tests proving the same semantic key keeps its ID across label changes and object reordering; implement the smallest deterministic identity helper.
- [ ] Add failing validation tests for malformed semantic bindings and unknown referenced object labels.
- [ ] Implement the minimum immutable intake fields and validation.
- [ ] Add a failing test: matching decision + all roles + bridge returns `applicable` with deterministic bindings; a missing/unconfirmed queue policy appears as a structured readiness-gap suggestion.
- [ ] Add a failing test: dairy or a different decision returns `not_applicable`, with no suggestions.
- [ ] Add failing tests: matching decision missing a required role or bridge returns `insufficient_information`, not `not_applicable`.
- [ ] Add a failing order-invariance test for objects and bindings.
- [ ] Add a temporary declarative unit in the test with different aliases and prove the same matcher handles it, demonstrating no supply-chain branch in Python.
- [ ] Implement generic exact/normalized matching from package-declared conditions only.
- [ ] Run focused tests, full tests, both legacy CLI smoke commands, and `git diff --check`.
- [ ] Commit: `feat: match knowledge units deterministically`.

---

## 7. Task 4 — Compile the immutable DecisionPack

**Files:**

- Create: `src/ontology_poc_generator/decision_pack.py`
- Create: `src/ontology_poc_generator/compiler.py`
- Create: `tests/test_decision_pack.py`
- Create: `tests/test_compiler.py`
- Modify: `src/ontology_poc_generator/generator.py`
- Modify: `src/ontology_poc_generator/models.py`

### TDD steps

- [ ] Add a failing frozen-dataclass test for `InputBinding`, `KnowledgeOutcome`, and `DecisionPack`.
- [ ] Add a failing test that the applicable golden pack contains input-external candidate suggestions with exact source/unit/hash/binding provenance.
- [ ] Add failing tests that `not_applicable` and `insufficient_information` outcomes never contain suggestions.
- [ ] Add a failing test that no suggestion contains a score, final queue membership, action, rule result, review, version, or publication field.
- [ ] Add a failing deterministic-ID test across repeated compilation and object reordering.
- [ ] Add a failing rename test proving a label change keeps binding/suggestion IDs while changing display content.
- [ ] Add a failing canonical serialization test proving the same pack has the same content hash.
- [ ] Implement `compile_decision_pack(params, knowledge_units=())` as a pure function.
- [ ] Add a failing compatibility test that `generate_proposal(params)` with no unit stays byte-equivalent to the Loop 0 projection.
- [ ] Change `generate_proposal` to project from the pack while preserving the public default call.
- [ ] Add `knowledge_outcomes` and suggestions to the end of `Proposal` with immutable defaults; do not break positional callers.
- [ ] Add exact no-unit Markdown and JSON golden regressions. Because the current JSON renderer uses `asdict`, explicitly omit empty knowledge-only fields in compatibility mode so the default Loop 0 JSON schema remains unchanged.
- [ ] Run focused tests, full tests, and `git diff --check`.
- [ ] Commit: `feat: compile sourced decision packs`.

---

## 8. Task 5 — Expose opt-in CLI projections and close Loop 1

**Files:**

- Modify: `src/ontology_poc_generator/cli.py`
- Modify: `src/ontology_poc_generator/renderers.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_generator.py`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/DISCOVERY_LOG.md`

### TDD steps

- [ ] Add a failing CLI test for repeatable `--knowledge-unit PATH`; default invocation must still load none.
- [ ] Add a failing JSON projection test that preserves structured source, match status, suggestion, and binding fields.
- [ ] Add a failing Markdown test that labels all additions “有来源的候选建议” and displays source locator/hash caveats.
- [ ] Add negative assertions for confirmed, evaluated, final queue, score, action created, reviewed, versioned, published, and external write claims.
- [ ] Implement CLI loading and error handling as input validation; do not add subcommands or persistence.
- [ ] Implement renderer formatting only; renderer must not match, infer, or change status.
- [ ] Run focused tests and full tests.
- [ ] Generate supply-chain JSON/Markdown with the unit and dairy JSON/Markdown with the same unit into a temporary directory.
- [ ] Inspect: supply-chain output has source-backed candidates; dairy is `not_applicable`; the insufficiency fixture explains a missing bridge; a separate missing-policy fixture keeps the suggestions and adds a readiness gap; all remain `synthetic_demo`.
- [ ] Run `git diff --check`.
- [ ] Update ROADMAP/DISCOVERY only with the exact observed test count, commands, evidence, and remaining limitations.
- [ ] Commit: `docs: close sourced knowledge loop`.

---

## 9. Final verification commands

```bash
PYTHONPATH=src python -m unittest tests.test_knowledge -v
PYTHONPATH=src python -m unittest tests.test_knowledge_matching -v
PYTHONPATH=src python -m unittest tests.test_decision_pack tests.test_compiler -v
PYTHONPATH=src python -m unittest discover -s tests -v

tmp_dir="$(mktemp -d)"
PYTHONPATH=src python -m ontology_poc_generator.cli \
  examples/supply_chain_exception.json \
  --knowledge-unit knowledge/supply_chain/supplier_evidence_boundary_v1.json \
  --format json --output "$tmp_dir/supply.json"

PYTHONPATH=src python -m ontology_poc_generator.cli \
  examples/dairy_rnd.json \
  --knowledge-unit knowledge/supply_chain/supplier_evidence_boundary_v1.json \
  --format json --output "$tmp_dir/dairy.json"

git diff --check
git status --short
```

Loop 1 is complete only after an independent reviewer verifies the exit conditions against the generated artifacts. If the unit merely restates the input, hides why it matched, or implies a final business conclusion, stop and revise Loop 1; do not enter Loop 2.
