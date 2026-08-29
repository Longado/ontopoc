# OntoPoc Demo Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Trial modal into a runnable, evidence-bounded browser demo for model recognition, DecisionPack compilation, OntologySpec compilation, and the unexecuted Validation boundary.

**Architecture:** Keep the existing Vite/React landing page and visual language. Generate one committed `model_recognition_demo.v1` artifact through the Python domain pipeline using a deterministic demo gateway, then load and validate that artifact in a small frontend adapter. The browser never recomputes hashes and exposes no review, publish, Action, or writeback control.

**Tech Stack:** Python 3.11 standard library, React 19, Vite 6, Node test runner, existing Lucide icons.

---

### Task 1: Import the existing prototype foundation

**Files:**
- Add: `landing-page/` runtime source, assets, package lock, build scripts, and tests
- Modify: `.gitignore`

- [ ] Copy only the existing runtime allowlist; exclude `node_modules`, `dist`, audit images, QA images, the dirty root README, and the stale handoff document.
- [ ] Run `npm ci`, `npm run test:unit`, `npm run build`, and `npm run test:sites`.
- [ ] Confirm `git status --short --ignored` contains no generated or audit material.
- [ ] Commit with `chore: add ontopoc demo foundation` and push the branch.

### Task 2: Add the real compiler-artifact workspace

**Files:**
- Create: `scripts/generate_demo_artifact.py`
- Create: `landing-page/public/artifacts/supply-chain-recognition.json`
- Create: `landing-page/src/trialWorkspaceModel.js`
- Create: `landing-page/src/trialWorkspaceModel.test.js`
- Create: `landing-page/src/TrialWorkspace.jsx`
- Modify: `landing-page/src/App.jsx`
- Modify: `landing-page/src/styles.css`
- Modify: `landing-page/package.json`
- Modify: `landing-page/tests/landing-story.test.mjs`
- Create: `docs/FRONTEND_BACKEND_CAPABILITY_MAP.md`

- [ ] Write failing Node tests for artifact schema, `synthetic_demo` scope, backend-owned hashes, candidate governance, and the Validation `not_implemented` boundary.
- [ ] Run `npm run test:unit` and confirm the new tests fail because the adapter does not exist.
- [ ] Implement the smallest artifact adapter that returns four read-only stages: Recognition, DecisionPack, OntologySpec, and Validation.
- [ ] Generate the fixture with `recognize_scenario`, `compile_decision_pack`, and `compile_ontology_spec`; use a deterministic gateway and the existing synthetic knowledge units.
- [ ] Replace only the Trial modal body with the new workspace while preserving modal focus management, language switching, Esc/overlay close, and the existing design system.
- [ ] Show `complete` only as compilation status and `is_closed` only as reference-closure evidence. Show Validation as contract-only with no receipt.
- [ ] Remove Trial approval, publish, Action, and writeback controls from the mounted Demo path.
- [ ] Run focused tests, all frontend tests, production build, Sites tests, backend full unittest, `git diff --check`, and scope/status checks.
- [ ] Verify desktop and 390 px mobile interaction in a browser with no console errors.
- [ ] Commit with `feat: connect ontopoc demo workspace`, push, request one independent P1/P2 review, and open a PR to `main`.
