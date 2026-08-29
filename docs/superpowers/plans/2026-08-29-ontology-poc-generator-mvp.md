# Ontology POC Generator MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic CLI that validates industrial-scene parameters and generates a decision-centered ontology POC proposal in Markdown and structured JSON.

**Architecture:** Keep the methodology core dependency-free: immutable input dataclasses validate the scenario, a planner derives a proposal model, and separate renderers produce Markdown or JSON. The CLI is only an adapter; a later web API must call the same planner instead of duplicating generation logic.

**Tech Stack:** Python 3.11+ standard library, dataclasses, argparse, unittest, JSON, Markdown.

---

### Task 1: Scenario contract and validation

**Files:**
- Create: `tests/test_generator.py`
- Create: `src/ontology_poc_generator/models.py`
- Create: `src/ontology_poc_generator/errors.py`

- [ ] Write a failing test that constructs a scenario with industry, scene, decision, owner, trigger, two objects and one acceptance question.
- [ ] Run `PYTHONPATH=src python -m unittest tests.test_generator -v` and confirm the missing-module failure.
- [ ] Implement immutable `ScenarioParameters.from_dict()` and `ScenarioValidationError`.
- [ ] Reject blank required strings, fewer than two objects, and an empty acceptance-question list with field-specific messages.
- [ ] Rerun the focused test and confirm it passes.

### Task 2: Decision-centered proposal model

**Files:**
- Modify: `tests/test_generator.py`
- Create: `src/ontology_poc_generator/methodology.py`
- Create: `src/ontology_poc_generator/generator.py`

- [ ] Write a failing test asserting that the proposal contains one primary decision, a trigger, owner, object types, proposed relations, decision loop and acceptance criteria.
- [ ] Confirm the failure is caused by the missing generator.
- [ ] Implement `generate_proposal(params)` as a pure function.
- [ ] Derive relations from object order only as explicit candidates and mark them for business confirmation.
- [ ] Add fixed responsibility boundaries for LLM extraction, ontology control, specialist models, Agent orchestration and human decision.
- [ ] Rerun the focused test and confirm it passes.

### Task 3: Evidence and synthetic-demo boundary

**Files:**
- Modify: `tests/test_generator.py`
- Modify: `src/ontology_poc_generator/generator.py`

- [ ] Write a failing test asserting `synthetic_demo` when `customer_data_available` is false.
- [ ] Write a failing test asserting that missing data-source status appears as a data gap rather than a confirmed integration.
- [ ] Implement the minimal evidence-status logic.
- [ ] Run all generator tests and confirm they pass.

### Task 4: Markdown and JSON renderers

**Files:**
- Modify: `tests/test_generator.py`
- Create: `src/ontology_poc_generator/renderers.py`

- [ ] Write a failing test for all twelve required Markdown sections.
- [ ] Write a failing test proving repeated rendering of the same proposal is byte-identical.
- [ ] Implement `render_markdown()` and `render_json()` without embedding current timestamps.
- [ ] Run all tests and confirm deterministic output.

### Task 5: CLI and sample scenario

**Files:**
- Create: `src/ontology_poc_generator/cli.py`
- Create: `src/ontology_poc_generator/__main__.py`
- Create: `examples/dairy_rnd.json`
- Create: `tests/test_cli.py`

- [ ] Write a failing CLI test using a temporary output directory.
- [ ] Implement input loading, format selection, stdout output and `--output` file writing.
- [ ] Return exit code 2 and a concise validation message for invalid input.
- [ ] Run the CLI test, then generate the dairy sample.

### Task 6: Second-industry contract check

**Files:**
- Create: `examples/supply_chain_exception.json`
- Create: `tests/test_examples.py`
- Modify: `docs/PRODUCT_SPEC.md` only if the second example exposes a missing field.

- [ ] Write a test that loads and generates every JSON file under `examples/`.
- [ ] Add a supply-chain exception scenario centered on one fulfillment-risk decision.
- [ ] If a new field is required, first add a failing validation/generation test, then update the contract and both examples.
- [ ] Run the full test suite and confirm both industries generate without special-case code.

### Task 7: MVP verification and living records

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `docs/DISCOVERY_LOG.md`

- [ ] Run `PYTHONPATH=src python -m unittest discover -s tests -v`.
- [ ] Generate both example proposals into a temporary directory and inspect their section structure.
- [ ] Run `git diff --check` and inspect `git status --short`.
- [ ] Update Stage 1 status only with the fresh test and sample-generation evidence.
- [ ] Do not create a Git commit unless the user explicitly asks for one.
