# Five-System Quality Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn read-only ERP, MES, QMS, WMS, and PLM evidence into a deterministic temporary-control scope plus an evidence-bound Agent recommendation that still requires human confirmation.

**Architecture:** Each source remains authoritative and is read through one small JSON contract over local files or HTTP GET. Python normalizes and hashes the source snapshot, computes the four impact states from explicit relations, and then reuses the existing three-Agent modeling flow; a fourth Agent converts the computed scope into reviewable include, exclude, or needs-evidence recommendations. No write-back, workflow engine, graph database, or new dependency is introduced.

**Tech Stack:** Python 3.11 standard library, existing OpenAI-compatible gateway and DecisionPack/OntologySpec compiler, `unittest`.

---

### Task 1: Five-system read-only source intake

**Files:**
- Create: `tests/test_enterprise_sources.py`
- Create: `src/ontology_poc_generator/enterprise_sources.py`
- Create: `tests/fixtures/enterprise_sources/manifest.json`
- Create: `tests/fixtures/enterprise_sources/{erp,mes,qms,wms,plm}.json`

- [x] Write tests requiring exactly one ERP, MES, QMS, WMS, and PLM source, stable snapshot ordering/hash, duplicate-record rejection, and HTTP GET with credentials read only from an environment variable.
- [x] Run the tests and verify RED because the intake module does not exist.
- [x] Implement the smallest file/HTTP JSON loader and canonical source-text renderer.
- [x] Run the focused tests and verify GREEN.

### Task 2: Derive the four impact states from facts

**Files:**
- Modify: `tests/test_investigation_scope.py`
- Modify: `src/ontology_poc_generator/investigation_scope.py`
- Modify: `tests/fixtures/quality/quality_investigation_source_snapshot_v1.json`
- Modify: `scripts/generate_quality_investigation_artifact.py`
- Modify: `tests/test_quality_investigation_artifact.py`
- Regenerate: `landing-page/public/artifacts/quality-investigation.json`

- [x] Write tests proving confirmed impact from exact batch reachability, possible impact from version-only reachability, exclusion from explicit normal controls, and not-evaluable from a missing required link.
- [x] Run the tests and verify RED; retain the existing test that forbids computed answers inside source snapshots.
- [x] Implement the bounded quality-scope evaluator and move all derived statuses out of the source fixture.
- [x] Regenerate the browser artifact and run focused tests to verify GREEN.

### Task 3: Add the Agent decision advisory and one product entry point

**Files:**
- Create: `tests/test_connected_assessment.py`
- Create: `src/ontology_poc_generator/connected_assessment.py`
- Create: `tests/test_connected_assessment_cli.py`
- Create: `src/ontology_poc_generator/connected_assessment_cli.py`
- Modify: `src/ontology_poc_generator/agent_modeling.py`
- Modify: `pyproject.toml`
- Modify: `README.md`

- [x] Write tests for four served roles, exact evidence-reference closure, status-to-recommendation guardrails, prompt-injection isolation, and explicit no-action boundaries.
- [x] Run the tests and verify RED because the connected assessment does not exist.
- [x] Implement the fourth decision-advisor prompt, deterministic validator, orchestration, and `ontopoc-connected-assess` CLI.
- [x] Strengthen existing modeling prompts with source-system authority and no-unproven-join rules; keep Python validation authoritative.
- [x] Run focused tests and verify GREEN.

### Task 4: Verify the complete product slice

**Files:**
- Modify only documentation already listed above if observed behavior differs.

- [x] Run all backend tests, frontend unit tests, artifact check, build, and `git diff --check`.
- [x] If configured, run one synthetic DeepSeek assessment without customer material and report the served model separately from test success.
- [x] Compare the final diff to this plan and remove only unrelated changes introduced during this task.
