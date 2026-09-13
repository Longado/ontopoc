# End-to-End Multi-Agent Modeling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the quality modeling CLI from reviewed object mentions to a three-role workflow that compiles an evidence-bound decision draft into the existing `DecisionPack` and closed `OntologySpec`.

**Architecture:** A decision analyst extracts the decision contract, an ontology modeler identifies controlled quality object types and relations, and an evidence reviewer judges every candidate. Python remains authoritative for exact-source evidence, stable identity, reviewer coverage, required-field readiness, relation closure, and compilation into existing domain artifacts.

**Tech Stack:** Python 3.11 standard library, existing OpenAI-compatible gateway, existing `ScenarioParameters` / `DecisionPack` / `OntologySpec` compilers, `unittest`.

---

### Task 1: Define the v2 product contract

**Files:**
- Modify: `tests/test_agent_modeling.py`
- Modify: `src/ontology_poc_generator/agent_modeling.py`

- [x] **Step 1: Write the failing ready-path test**

The wished-for API uses three gateways and produces compiled artifacts:

```python
result = run_multi_agent_modeling(
    source_text,
    decision_analyst_gateway,
    ontology_modeler_gateway,
    evidence_reviewer_gateway,
)
self.assertEqual(result["schema"], "multi_agent_modeling.v2")
self.assertEqual(result["modeling_status"], "ready_for_human_confirmation")
self.assertEqual(result["decision_pack"]["pack"]["schema"], "decision_pack.v1")
self.assertTrue(result["ontology_spec"]["reference_closure"]["is_closed"])
```

The decision analyst returns `decision_contract_candidate.v1`; the ontology modeler returns `ontology_candidate_proposal.v2`; the reviewer returns `modeling_evidence_review.v1` with exactly one verdict for every generated candidate ID.

- [x] **Step 2: Run the focused test and verify RED**

```bash
PYTHONPATH=src python3.11 -m unittest tests.test_agent_modeling
```

Expected: failure because the existing function accepts only two gateways and emits v1.

- [x] **Step 3: Implement the v2 roles and canonical candidates**

Replace the v1 prompts and orchestration with:

```python
def run_multi_agent_modeling(
    source_text: str,
    decision_analyst_gateway: RecognitionGateway,
    ontology_modeler_gateway: RecognitionGateway,
    evidence_reviewer_gateway: RecognitionGateway,
) -> dict[str, object]:
    ...
```

Required decision fields are `industry`, `scene_name`, `business_decision`, `decision_owner`, and `trigger`. Optional reviewed collections are participants, constraints, data sources, desired actions, and acceptance questions. Ontology candidates use the bounded quality vocabulary and program-owned role/semantic keys.

- [x] **Step 4: Compile accepted candidates with existing authority code**

When all required decision fields, at least one acceptance question, and at least two object types are accepted, construct `ScenarioParameters`, then call:

```python
pack = compile_decision_pack(scenario)
compilation = compile_ontology_spec(pack)
```

Return canonical pack/spec data and reference-closure evidence. The result remains a draft requiring human confirmation; no ontology authority is updated.

- [x] **Step 5: Verify GREEN**

Run the Task 1 command and expect all core tests to pass.

### Task 2: Preserve fail-closed behavior and useful blocking output

**Files:**
- Modify: `tests/test_agent_modeling.py`
- Modify: `src/ontology_poc_generator/agent_modeling.py`

- [x] **Step 1: Write failing gap and contradiction tests**

```python
self.assertEqual(result["modeling_status"], "blocked_missing_evidence")
self.assertIn("decision_owner", result["blocking_gaps"])
self.assertIsNone(result["decision_pack"])
self.assertIsNone(result["ontology_spec"])
```

Also retain regression coverage for hallucinated evidence, missing/duplicate reviewer verdicts, stable model ordering, and accepted relations whose endpoints were rejected.

- [x] **Step 2: Verify RED**

Run the focused core tests. Expected: the current implementation raises or compiles instead of returning the required typed gap result.

- [x] **Step 3: Implement deterministic readiness**

Compute blocking gaps only from absent or rejected required candidates. Never ask an LLM whether compilation is complete. Contradictory reviewer output remains an input error; ordinary missing evidence returns a blocked result with reviewed candidates intact.

- [x] **Step 4: Verify GREEN**

Run the focused core tests and expect all to pass.

### Task 3: Make the single CLI exercise the full workflow

**Files:**
- Modify: `tests/test_agent_modeling_cli.py`
- Modify: `src/ontology_poc_generator/agent_modeling_cli.py`
- Modify: `README.md`

- [x] **Step 1: Write the failing three-role CLI test**

```python
exit_code = main([str(source), "--output", str(output)])
self.assertEqual(exit_code, 0)
self.assertEqual(len(FakeGateway.instances), 3)
self.assertEqual(json.loads(output.read_text())["modeling_status"], "ready_for_human_confirmation")
```

- [x] **Step 2: Verify RED**

```bash
PYTHONPATH=src python3.11 -m unittest tests.test_agent_modeling_cli
```

Expected: failure because the CLI creates only two role gateways.

- [x] **Step 3: Upgrade the existing command and documentation**

Instantiate three gateways with the existing configuration and keep `ontopoc-agent-model` as the only command. Document one synthetic command, the three roles, and the draft/human-confirmation boundary. Add no dependency, server, database, or web page.

- [x] **Step 4: Verify locally and against DeepSeek**

```bash
PYTHONPATH=src python3.11 -m unittest \
  tests.test_agent_modeling tests.test_agent_modeling_cli \
  tests.test_decision_pack tests.test_provided_compiler tests.test_spec_compiler
git diff --check
```

Then run the command path with a generic synthetic quality scenario and a valid DeepSeek credential. Acceptance requires three served-model roles, `ready_for_human_confirmation`, a canonical DecisionPack, and a reference-closed OntologySpec. Do not save or send customer-sensitive material.
