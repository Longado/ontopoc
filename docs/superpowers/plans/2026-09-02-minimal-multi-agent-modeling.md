# Minimal Multi-Agent Modeling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local two-agent CLI that turns one quality-event text into evidence-bound object and relation candidates reviewed by a second agent.

**Architecture:** Reuse the existing JSON model gateway twice with separate modeler and evidence-reviewer prompts. Python validates every proposed evidence span, generates stable IDs, enforces reviewer coverage and relation closure, and emits one `multi_agent_modeling.v1` result that still requires human confirmation.

**Tech Stack:** Python 3.11 standard library, existing `RecognitionGateway` and `OpenAICompatibleGateway`, `unittest`.

---

### Task 1: Evidence-bound two-agent core

**Files:**
- Create: `src/ontology_poc_generator/agent_modeling.py`
- Create: `tests/test_agent_modeling.py`

- [x] **Step 1: Write the failing core test**

```python
result = run_multi_agent_modeling(source_text, modeler_gateway, reviewer_gateway)
self.assertEqual(result["schema"], "multi_agent_modeling.v1")
self.assertEqual([item["role"] for item in result["agents"]], ["modeler", "evidence_reviewer"])
self.assertTrue(result["boundaries"]["human_confirmation_required"])
```

The fake modeler returns objects and relations whose `evidence_span` values occur verbatim in the source. The fake reviewer returns exactly one verdict for every generated candidate ID.

- [x] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=src python3.11 -m unittest tests.test_agent_modeling
```

Expected: import failure because `agent_modeling` does not exist.

- [x] **Step 3: Implement the minimum core**

```python
def run_multi_agent_modeling(
    source_text: str,
    modeler_gateway: RecognitionGateway,
    reviewer_gateway: RecognitionGateway,
) -> dict[str, object]:
    # 1. request ontology_candidate_proposal.v1
    # 2. reject evidence spans absent from source and generate stable IDs
    # 3. request ontology_candidate_review.v1 over canonical candidates
    # 4. require one verdict per candidate and closed accepted relations
    # 5. return multi_agent_modeling.v1 with explicit no-action boundaries
```

Only the current quality-control vocabulary is accepted. No orchestration framework, memory, retry layer, persistence, or action contract is added.

- [x] **Step 4: Verify GREEN**

Run the Task 1 command and expect all tests to pass.

### Task 2: Local CLI entry point

**Files:**
- Create: `src/ontology_poc_generator/agent_modeling_cli.py`
- Create: `tests/test_agent_modeling_cli.py`
- Modify: `pyproject.toml`

- [x] **Step 1: Write the failing CLI test**

```python
exit_code = main([str(source), "--output", str(output)])
self.assertEqual(exit_code, 0)
self.assertEqual(json.loads(output.read_text())["schema"], "multi_agent_modeling.v1")
```

Patch the existing gateway with an offline fake. Assert the CLI reads credentials only from an environment variable and never writes the key into output.

- [x] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=src python3.11 -m unittest tests.test_agent_modeling_cli
```

Expected: import failure because `agent_modeling_cli` does not exist.

- [x] **Step 3: Implement the minimum CLI**

```python
modeler = OpenAICompatibleGateway(api_base=api_base, api_key=api_key, model=model)
reviewer = OpenAICompatibleGateway(api_base=api_base, api_key=api_key, model=model)
result = run_multi_agent_modeling(source_text, modeler, reviewer)
```

Reuse the existing atomic writer and output-collision check. Register only `ontopoc-agent-model`; do not add a server or browser integration.

- [x] **Step 4: Verify GREEN and scope**

Run:

```bash
PYTHONPATH=src python3.11 -m unittest tests.test_agent_modeling tests.test_agent_modeling_cli
git diff --check
```

Expected: focused tests pass; no web files, dependencies, persistence, or external actions are introduced.
