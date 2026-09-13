# Gate 1 Real Material Signal Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Do not delegate unless the user explicitly asks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用三次受控模型调用判断一份脱敏历史质量事件能否支持“质量信号尚未定因时的临时控制/复检决策”，并产生固定决策模板之外、带精确原文证据的业务对象或关系，形成是否进入 Gate 2 的 `go / no-go`。

**Architecture:** 本计划不修改仓库代码、candidate schema、CLI 或前端。实验通过用户批准的模型接口运行，所有客户材料、人工基线、prompt、原始输出和判定只写入 workspace `.local-sensitive/` 下的一份 evidence JSON；Gate 1 通过后另立 Gate 2 schema 变更计划。

**Tech Stack:** 现有仓库样例、用户批准的模型接口、`shasum -a 256`、`jq`；不新增依赖。

---

## Scope contract

**Outcome**

- 正例返回 `matched`，并至少包含一个不在质量控制固定对象标签集合中的对象，或一条不同于固定 `质量信号 → MAY_AFFECT → 受影响对象` bridge 的关系；该候选必须带原文逐字子串 `evidence_span`。
- 负例返回 `unsupported`。
- 合成对照返回 `matched`。
- evidence JSON 记录三份输入、模型、prompt、原始输出、人工基线、核验结果和 `go / no-go`。

**Non-goals**

- 不修改 `src/`、`tests/`、`landing-page/`、knowledge unit 或 committed artifact。
- 不调用当前闭集 Recognition prompt 证明材料抽取有效。
- 不设计 `scenario_intake_candidate.v2`、关系转换、`threshold_v1`、Review、DecisionDelta、API 或持久化。
- 不创建实验框架、评测框架、通用 prompt 管理器或新测试基础设施。
- 不把用户指定的内部客户案例、路径或正文写入仓库、evidence JSON 或任何模型请求；该案例只用于离线确定决策契约。
- 不自动确认根因，不执行停产、冻结、发运拦截、客户通知或外部系统写回。

**Repository files changed during execution:** none.

**Local-sensitive artifact created during execution:**

`<workspace>/.local-sensitive/ontology-poc-generator/experiments/2026-09-02-gate1-quality-control-evidence.json`

**Proof**

- evidence JSON 通过本文的 `jq` 结构与状态检查。
- 每个对象和关系的 `evidence_span` 都通过逐字子串检查。
- 正例至少有一个 `novel_to_fixed_template=true` 的 evidence-bound 候选。
- 用户在看模型输出前完成 5 条人工判断并记录耗时。
- `assessment.decision` 明确为 `go` 或 `no_go`，并记录理由。

## Fixed comparison inputs

- Negative: `examples/dairy_rnd.json`
- Synthetic control (`source_kind=inline_synthetic`; exact UTF-8 text, no trailing newline): `某组件在终检中出现泄漏率异常，原因尚未确认。质量负责人决定将使用批次 B-17 的在制品和待发运件列入临时复检队列；已发运件因客户项目映射缺失暂不能判断。`
- Fixed object labels used only for novelty comparison: `质量信号`、`受影响对象`、`质量证据`、`临时控制任务`
- Fixed bridge used only for novelty comparison: `质量信号 → MAY_AFFECT → 受影响对象`
- The internal customer case used to derive this decision contract is excluded from all three model inputs.

## Open extraction prompt

对三个 case 使用完全相同的以下 prompt；每个 case 只调用一次模型：

```text
你正在判断一份业务材料是否明确支持这个决策：当质量信号出现且原因尚未确认时，哪些库存、在制、待发运、在途或客户侧对象应该进入临时控制或复检队列，依据是什么，还有哪些信息无法确认？

只输出一个 JSON 对象，不要输出 Markdown、解释过程或代码围栏。对象必须严格符合：
{
  "schema": "gate1_quality_control_extraction.v1",
  "match_status": "matched | insufficient_information | unsupported",
  "extracted_objects": [
    {
      "raw_label": "材料中的对象称谓",
      "candidate_role_key": "quality_signal | affected_object | evidence | decision_owner | unknown",
      "evidence_span": "从材料逐字复制的最短充分片段"
    }
  ],
  "extracted_relations": [
    {
      "source_raw_label": "材料中的源对象称谓",
      "predicate_text": "材料表达的关系",
      "target_raw_label": "材料中的目标对象称谓",
      "evidence_span": "从材料逐字复制的最短充分片段"
    }
  ],
  "unknowns": ["材料不足以确认的内容"]
}

规则：
1. 只有材料明确讨论质量信号尚未定因时的临时控制范围或复检优先级时才输出 matched。
2. 明确属于其他业务决策时输出 unsupported；虽与质量相关但缺少质量触发、待控制对象范围或判断依据时输出 insufficient_information。
3. 不得补写材料中没有的对象或关系。每个 evidence_span 必须是输入材料中的逐字连续子串。
4. candidate_role_key 无法可靠映射到闭集时使用 unknown，不做最近匹配。
5. 不确认最终根因，不输出规则阈值、评分、最终处置结论、Action、发布状态或写回指令。

待分析材料：
把当前 case 的完整材料正文直接附加在本行之后。
```

### Task 1: Confirm execution authority and inputs

**Files:**

- Read: active execution-state relay in the current conversation
- Read: user-selected positive source under `<workspace>/.local-sensitive/`
- Modify: none

- [ ] **Step 1: Confirm the five required values are explicit**

The active relay must contain all five values:

1. exact positive UTF-8 text or Markdown source path under `<workspace>/.local-sensitive/`;
2. exact approved provider, model name and model settings; use `provider_default` when the approved interface exposes no setting controls;
3. approval for exactly three model calls;
4. five manual judgment bullets plus elapsed minutes, written before model output is shown.
5. confirmation that the positive source is a redacted historical quality event, not the internal customer design-reference case.

If any value is absent, stop. Report only the missing value; do not create the evidence file and do not call a model.

- [ ] **Step 2: Confirm repository isolation and clean state**

Run:

```bash
cd .worktrees/pc-agent-modeling-demo
git status --short --branch
git rev-parse HEAD
```

Expected: branch `rico/handoff-v2`, no modified or untracked files before the experiment. A different clean commit is acceptable only when the active relay explicitly names it.

- [ ] **Step 3: Validate the positive source boundary**

Confirm the resolved positive source path starts with:

`<workspace>/.local-sensitive/`

If it resolves inside any git repository, `.data`, or the OntoPoc worktree, stop and request a safe copy under `.local-sensitive/`.

Confirm the source is already a redacted UTF-8 text or Markdown file describing a historical quality event and the information available around its temporary-control or reinspection decision. If it is a design proposal, product plan, PDF, Office document, image or non-UTF-8 file, stop and request a redacted UTF-8 historical-event export; document conversion is outside this plan.

### Task 2: Establish immutable inputs and the human baseline

**Files:**

- Read: user-selected positive source
- Read: `examples/dairy_rnd.json`
- Use: the exact inline synthetic control text fixed in this plan
- Create: `<workspace>/.local-sensitive/ontology-poc-generator/experiments/2026-09-02-gate1-quality-control-evidence.json`

- [ ] **Step 1: Create the evidence directory**

Run:

```bash
mkdir -p <workspace>/.local-sensitive/ontology-poc-generator/experiments
```

- [ ] **Step 2: Hash all three exact inputs**

Run `shasum -a 256` separately for the user-selected positive source and the negative file. Hash the inline synthetic control as exact UTF-8 bytes without a trailing newline:

```bash
printf '%s' '某组件在终检中出现泄漏率异常，原因尚未确认。质量负责人决定将使用批次 B-17 的在制品和待发运件列入临时复检队列；已发运件因客户项目映射缺失暂不能判断。' | shasum -a 256
```

Record each source kind, absolute path when present, exact source text and digest in the evidence JSON. Use `source_path: null` and `source_kind: inline_synthetic` for the control. Do not copy the positive source into the repository.

- [ ] **Step 3: Record the human baseline before model execution**

Create the evidence JSON with schema `ontopoc_gate1_evidence.v1`. Record:

- actual run date;
- decision contract `quality_signal_temporary_control.v1`;
- approved provider, exact model name and call limit `3`;
- the Open extraction prompt verbatim;
- three cases with IDs `positive`, `negative`, `control`, their source kinds, source paths when present, SHA-256 digests, full source text and expected statuses `matched`, `unsupported`, `matched`;
- exactly five user-authored manual bullets and a positive elapsed-minute number;
- each bullet states one material-supported object, relation or unresolved information item relevant to the temporary-control/reinspection decision; recommendations, future actions and general business commentary do not count toward coverage;
- empty `raw_output_text`, `parse_status` and `parsed_output` values until Task 3;
- an assessment with `decision` set to `not_evaluated` until Task 4.

Because this file contains customer text, use `apply_patch` and keep it only under `.local-sensitive/`; never stage it with git. Do not include the internal customer design-reference case in this file.

### Task 3: Run exactly three open-extraction calls

**Files:**

- Modify: `<workspace>/.local-sensitive/ontology-poc-generator/experiments/2026-09-02-gate1-quality-control-evidence.json`
- Modify in repository: none

- [ ] **Step 1: Run the positive case once**

Use the approved provider, exact model and settings recorded in Task 2. Submit the fixed prompt with the positive source text. Copy the complete response without correction into the positive case `raw_output_text`. Set `parse_status` to `valid_json` and `parsed_output` to the parsed object only when the response is valid JSON; otherwise set `parse_status` to `invalid_json` and `parsed_output` to `null`.

- [ ] **Step 2: Run the negative case once**

Use the same provider, model, prompt and model settings. Submit `examples/dairy_rnd.json` as the material and record `raw_output_text`, `parse_status` and `parsed_output` using the same rule as the positive case.

- [ ] **Step 3: Run the control case once**

Use the same provider, model, prompt and model settings. Submit the exact inline synthetic control text fixed in this plan and record `raw_output_text`, `parse_status` and `parsed_output` using the same rule as the positive case.

- [ ] **Step 4: Enforce the call limit**

Confirm exactly three model calls were made. Do not retry malformed output or change the prompt during this Gate. A malformed response is Gate 1 evidence and contributes to `no_go`.

### Task 4: Validate evidence and make the gate decision

**Files:**

- Modify: `<workspace>/.local-sensitive/ontology-poc-generator/experiments/2026-09-02-gate1-quality-control-evidence.json`
- Modify in repository: none

- [ ] **Step 1: Validate the evidence record structure**

Run:

```bash
jq -e '
  .schema == "ontopoc_gate1_evidence.v1"
  and .decision_contract == "quality_signal_temporary_control.v1"
  and .model.call_limit == 3
  and (.model.settings | type == "object")
  and (.cases | length == 3)
  and ([.cases[].id] == ["positive", "negative", "control"])
  and all(.cases[];
    (.raw_output_text | type == "string")
    and (.parse_status == "valid_json" or .parse_status == "invalid_json")
    and (if .parse_status == "valid_json"
         then (.parsed_output | type == "object")
         else .parsed_output == null
         end)
  )
  and (.manual_baseline.bullets | length == 5)
  and (.manual_baseline.elapsed_minutes > 0)
' <workspace>/.local-sensitive/ontology-poc-generator/experiments/2026-09-02-gate1-quality-control-evidence.json
```

Expected: `true`, exit 0.

- [ ] **Step 2: Validate all evidence spans as exact substrings**

Run:

```bash
jq -e '
  all(.cases[] | select(.parse_status == "valid_json");
    .source_text as $source
    | all((.parsed_output.extracted_objects // [])[];
        .evidence_span as $span | $source | contains($span))
    and all((.parsed_output.extracted_relations // [])[];
        .evidence_span as $span | $source | contains($span))
  )
' <workspace>/.local-sensitive/ontology-poc-generator/experiments/2026-09-02-gate1-quality-control-evidence.json
```

Expected: `true`, exit 0. Any false or malformed case yields `no_go`; do not repair the model output.

- [ ] **Step 3: Score novelty and coverage**

For each positive object and relation, record:

- `span_is_substring`;
- `novel_to_fixed_template` by comparing against the fixed labels and bridge listed in this plan;
- whether it contributes to one of the user's five manual bullets.

Record whether model coverage is below, equal to or above the manual baseline. Do not count label paraphrases as new structure.

- [ ] **Step 4: Apply the gate rule exactly once**

Set `assessment.decision` to `go` only when all conditions hold:

1. all three `parse_status` values are `valid_json`;
2. positive status is `matched`;
3. negative status is `unsupported`;
4. control status is `matched`;
5. every emitted object and relation has a valid exact span;
6. the positive case contains at least one evidence-bound candidate with `novel_to_fixed_template=true`;
7. positive model coverage is not below the five manual bullets.

Otherwise set it to `no_go`. Record the failed condition IDs and a short factual reason.

- [ ] **Step 5: Confirm no repository mutation occurred**

Run:

```bash
cd .worktrees/pc-agent-modeling-demo
git status --short --branch
```

Expected: the same clean repository state observed in Task 1. Do not run backend or frontend test suites because this experiment changes no repository behavior.

- [ ] **Step 6: Overwrite the relay state**

If `no_go`, set the next minimum action to “stop product expansion and review the failed Gate 1 condition”; do not create a Gate 2 plan.

If `go`, set the next minimum action to “request approval for the candidate schema version strategy”; create no code and make no schema decision inside this plan.

## Completion boundary

This plan is complete when the local-sensitive evidence JSON passes the structural checks, contains the unedited three-call outputs and manual baseline, records a single `go / no-go`, and the OntoPoc repository remains unchanged. Passing repository tests is not a substitute for this evidence.
