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

- [x] Copy only the existing runtime allowlist; exclude `node_modules`, `dist`, audit images, QA images, the dirty root README, and the stale handoff document.
- [x] Run `npm ci`, `npm run test:unit`, `npm run build`, and `npm run test:sites`.
- [x] Confirm `git status --short --ignored` contains no generated or audit material.
- [x] Commit with `chore: add ontopoc demo foundation` and push the branch.

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

- [x] Write failing Node tests for artifact schema, `synthetic_demo` scope, backend-owned hashes, candidate governance, and the Validation `not_implemented` boundary.
- [x] Run `npm run test:unit` and confirm the new tests fail because the adapter does not exist.
- [x] Implement the smallest artifact adapter that returns four read-only stages: Recognition, DecisionPack, OntologySpec, and Validation.
- [x] Generate the fixture with `recognize_scenario`, `compile_decision_pack`, and `compile_ontology_spec`; use a deterministic gateway and the existing synthetic knowledge units.
- [x] Replace only the Trial modal body with the new workspace while preserving modal focus management, language switching, Esc/overlay close, and the existing design system.
- [x] Show `complete` only as compilation status and `is_closed` only as reference-closure evidence. Show Validation as contract-only with no receipt.
- [x] Remove Trial approval, publish, Action, and writeback controls from the mounted Demo path.
- [x] Run focused tests, all frontend tests, production build, Sites tests, backend full unittest, `git diff --check`, and scope/status checks.
- [x] Verify desktop and 390 px mobile interaction in a browser with no console errors.
- [x] Commit with `feat: connect ontopoc demo workspace` and push the branch.
- [ ] Request one independent P1/P2 review and open a PR to `main` (outside this implementation handoff).

### Task 3: Add the ontology graph and grounded demo chat

**Files:**
- Create: `landing-page/src/ontologyWorkspaceModel.js`
- Create: `landing-page/src/ontologyWorkspaceModel.test.js`
- Create: `landing-page/src/OntologyWorkspace.jsx`
- Modify: `landing-page/src/trialWorkspaceModel.js`
- Modify: `landing-page/src/trialWorkspaceModel.test.js`
- Modify: `landing-page/src/TrialWorkspace.jsx`
- Modify: `landing-page/src/styles.css`
- Modify: `landing-page/tests/landing-story.test.mjs`
- Modify: `docs/FRONTEND_BACKEND_CAPABILITY_MAP.md`

- [x] Write failing Node tests for deterministic graph projection, grounded answers, evidence references, and unsupported-question refusal.
- [x] Project entity types, declared domain/range relations, and the candidate rule from the existing `OntologySpec`; do not add customer instances, Action nodes, or invented facts.
- [x] Add a PC-first `Graph / Details` view inside the existing `OntologySpec` stage using the existing React Flow dependency, with a selectable canvas and a persistent evidence inspector; keep the four compiler stages unchanged.
- [x] Match the supplied desktop reference's operational hierarchy while preserving the current warm-paper, ink, cobalt, thin-rule design system.
- [x] Add a chatbot-style drawer that answers only from the loaded artifact, attaches graph evidence, and refuses instance/runtime questions the artifact cannot answer. Label it as deterministic demo Q&A, not a live model call.
- [x] Keep the current Validation boundary unchanged: evaluator not run, receipt null, and delivery flags false.
- [x] Run focused model tests, all frontend tests, production build, Sites tests, backend full unittest, `git diff --check`, browser desktop/390 px checks, and design QA against the supplied reference.
- [x] Commit with `feat: add ontology graph demo`, push, request one independent P1/P2 review, and update the PR.

### Task 4: Add document-to-modeling demo scenarios

**Files:**
- Create: `landing-page/src/documentModelingDemoModel.js`
- Create: `landing-page/src/documentModelingDemoModel.test.js`
- Create: `landing-page/src/DocumentModeler.jsx`
- Modify: `landing-page/src/TrialWorkspace.jsx`
- Modify: `landing-page/src/styles.css`
- Modify: `landing-page/tests/landing-story.test.mjs`
- Modify: `docs/FRONTEND_BACKEND_CAPABILITY_MAP.md`

- [x] Write failing Node tests for exactly three synthetic document presets, deterministic request resolution, the single compiled-artifact route, two preview-only routes, and unsupported edited input.
- [x] Define three small presets: supply-chain order intervention (`compiled_artifact`), supplier qualification change (`scenario_preview`), and dairy R&D fallback (`scenario_preview`). Each preset contains only synthetic document text, candidate entity types, candidate relation types, and its explicit capability boundary.
- [x] Resolve only an unchanged preset document. The supply-chain preset may call the existing committed artifact path; both other presets must remain frontend-only candidate previews. Edited or unknown text returns `unsupported` and must not silently map to a nearby scenario.
- [x] Replace the idle launch body with a PC-first two-column document modeler: scenario/document controls stay on the left; read-only candidate graph or boundary explanation stays on the right. Reuse the current warm-paper, ink, cobalt, thin-rule design and the existing React Flow dependency.
- [x] Make scenario selection, document text, Generate action, preview graph selection, and Start compiled demo work with mouse and keyboard. Keep the existing four-stage compiler workspace unchanged after the real supply-chain artifact starts.
- [x] Label every preset `synthetic_demo`; label the two non-compiled results `SCENARIO PREVIEW / NOT COMPILED`; label the parser `DETERMINISTIC DEMO PARSER / NO LIVE MODEL`. Do not add API, file upload, persistence, customer facts, validation receipt, Action, publish, or writeback behavior.
- [x] Run focused model/story tests, all frontend tests, production build, Sites tests, backend full unittest, `git diff --check`, scope/status checks, and 1440×900 plus 390×900 browser checks with no console errors.
- [x] Self-review the assigned diff, fix any findings, commit with `feat: add document modeling demos`, and push the branch.

### Task 5: Integrate the demo branch

- [ ] Run one fresh final frontend/backend/build/Sites verification and `git diff --check` on the complete branch.
- [ ] Confirm the original checkout's untracked `landing-page/`, dirty `README.md`, and handoff document were not modified, added, deleted, or committed.
- [ ] Create or update one GitHub pull request from `codex/demo-workspace` to `main`, wait for required checks, merge the pull request, and verify `origin/main` contains the merge.
