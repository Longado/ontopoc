# Gate 1 Real Material Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用三次受控模型调用判断一份现役脱敏材料能否产生固定模板之外、带精确原文证据的业务对象或关系，并形成是否进入 Gate 2 的 `go / no-go`。

**Architecture:** 本计划不修改仓库代码、candidate schema、CLI 或前端。实验通过用户批准的模型接口运行，所有客户材料、人工基线、prompt、原始输出和判定只写入 workspace `.local-sensitive/` 下的一份 evidence JSON；Gate 1 通过后另立 Gate 2 schema 变更计划。

**Tech Stack:** 现有仓库样例、用户批准的模型接口、`shasum -a 256`、`jq`；不新增依赖。

---

## Scope contract

**Outcome**

- 正例返回 `matched`，并至少包含一个不在当前固定对象标签集合中的对象，或一条不同于固定 `客户订单 → REQUIRES → 物料` bridge 的关系；该候选必须带原文逐字子串 `evidence_span`。
- 负例返回 `unsupported`。
- 合成对照返回 `matched`。
- evidence JSON 记录三份输入、模型、prompt、原始输出、人工基线、核验结果和 `go / no-go`。

**Non-goals**

- 不修改 `src/`、`tests/`、`landing-page/`、knowledge unit 或 committed artifact。
- 不调用当前闭集 Recognition prompt 证明材料抽取有效。
- 不设计 `scenario_intake_candidate.v2`、关系转换、`threshold_v1`、Review、DecisionDelta、API 或持久化。
- 不创建实验框架、评测框架、通用 prompt 管理器或新测试基础设施。

**Repository files changed during execution:** none.

**Local-sensitive artifact created during execution:**

`/Users/eddie/Desktop/Workspace/.local-sensitive/ontology-poc-generator/experiments/2026-09-01-gate1-evidence.json`

**Proof**

- evidence JSON 通过本文的 `jq` 结构与状态检查。
- 每个对象和关系的 `evidence_span` 都通过逐字子串检查。
- 正例至少有一个 `novel_to_fixed_template=true` 的 evidence-bound 候选。
- 用户在看模型输出前完成 5 条人工判断并记录耗时。
- `assessment.decision` 明确为 `go` 或 `no_go`，并记录理由。

## Fixed comparison inputs

- Negative: `/Users/eddie/Desktop/Workspace/ontology-poc-generator/.worktrees/pc-agent-modeling-demo/examples/dairy_rnd.json`
- Synthetic control: `/Users/eddie/Desktop/Workspace/ontology-poc-generator/.worktrees/pc-agent-modeling-demo/examples/supply_chain_exception.json`
- Fixed object labels used only for novelty comparison: `客户订单`、`订单行`、`物料`、`供应商`、`采购承诺`、`生产任务`、`物流节点`、`履约风险`、`处置任务`
- Fixed bridge used only for novelty comparison: `客户订单 → REQUIRES → 物料`

## Open extraction prompt

对三个 case 使用完全相同的以下 prompt；每个 case 只调用一次模型：

```text
你正在判断一份业务材料是否明确支持这个决策：哪些客户订单应该进入优先人工干预队列，为什么？

只输出一个 JSON 对象，不要输出 Markdown、解释过程或代码围栏。对象必须严格符合：
{
  "schema": "gate1_open_extraction.v1",
  "match_status": "matched | insufficient_information | unsupported",
  "extracted_objects": [
    {
      "raw_label": "材料中的对象称谓",
      "candidate_role_key": "customer_order | material | supplier | unknown",
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
1. 只有材料明确讨论订单优先人工干预决策时才输出 matched。
2. 明确属于其他业务决策时输出 unsupported；看似相关但缺少决策、负责人或触发条件时输出 insufficient_information。
3. 不得补写材料中没有的对象或关系。每个 evidence_span 必须是输入材料中的逐字连续子串。
4. candidate_role_key 无法可靠映射到闭集时使用 unknown，不做最近匹配。
5. 不输出规则阈值、评分、订单结论、Action、发布状态或写回指令。

待分析材料：
把当前 case 的完整材料正文直接附加在本行之后。
```

### Task 1: Confirm execution authority and inputs

**Files:**

- Read: active execution-state relay in the current conversation
- Read: user-selected positive source under `/Users/eddie/Desktop/Workspace/.local-sensitive/`
- Modify: none

- [ ] **Step 1: Confirm the four required values are explicit**

The active relay must contain all four values:

1. exact positive UTF-8 text or Markdown source path under `/Users/eddie/Desktop/Workspace/.local-sensitive/`;
2. exact approved provider, model name and model settings; use `provider_default` when the approved interface exposes no setting controls;
3. approval for exactly three model calls;
4. five manual judgment bullets plus elapsed minutes, written before model output is shown.

If any value is absent, stop. Report only the missing value; do not create the evidence file and do not call a model.

- [ ] **Step 2: Confirm repository isolation and clean state**

Run:

```bash
cd /Users/eddie/Desktop/Workspace/ontology-poc-generator/.worktrees/pc-agent-modeling-demo
git status --short --branch
git rev-parse HEAD
```

Expected: branch `rico/handoff-v2`, no modified or untracked files before the experiment. A different clean commit is acceptable only when the active relay explicitly names it.

- [ ] **Step 3: Validate the positive source boundary**

Confirm the resolved positive source path starts with:

`/Users/eddie/Desktop/Workspace/.local-sensitive/`

If it resolves inside any git repository, `.data`, or the OntoPoc worktree, stop and request a safe copy under `.local-sensitive/`.

Confirm the source is already a redacted UTF-8 text or Markdown file. If it is a PDF, Office document, image or non-UTF-8 file, stop and request a redacted UTF-8 text export; document conversion is outside this plan.

### Task 2: Establish immutable inputs and the human baseline

**Files:**

- Read: user-selected positive source
- Read: `examples/dairy_rnd.json`
- Read: `examples/supply_chain_exception.json`
- Create: `/Users/eddie/Desktop/Workspace/.local-sensitive/ontology-poc-generator/experiments/2026-09-01-gate1-evidence.json`

- [ ] **Step 1: Create the evidence directory**

Run:

```bash
mkdir -p /Users/eddie/Desktop/Workspace/.local-sensitive/ontology-poc-generator/experiments
```

- [ ] **Step 2: Hash all three exact inputs**

Run `shasum -a 256` separately for the user-selected positive source and the two fixed comparison inputs. Record each absolute source path and digest in the evidence JSON. Do not copy the positive source into the repository.

- [ ] **Step 3: Record the human baseline before model execution**

Create the evidence JSON with schema `ontopoc_gate1_evidence.v1`. Record:

- run date `2026-09-01`;
- approved provider, exact model name and call limit `3`;
- the Open extraction prompt verbatim;
- three cases with IDs `positive`, `negative`, `control`, their source paths, SHA-256 digests, full source text and expected statuses `matched`, `unsupported`, `matched`;
- exactly five user-authored manual bullets and a positive elapsed-minute number;
- empty `raw_output_text`, `parse_status` and `parsed_output` values until Task 3;
- an assessment with `decision` set to `not_evaluated` until Task 4.

Because this file contains customer text, use `apply_patch` and keep it only under `.local-sensitive/`; never stage it with git.

### Task 3: Run exactly three open-extraction calls

**Files:**

- Modify: `/Users/eddie/Desktop/Workspace/.local-sensitive/ontology-poc-generator/experiments/2026-09-01-gate1-evidence.json`
- Modify in repository: none

- [ ] **Step 1: Run the positive case once**

Use the approved provider, exact model and settings recorded in Task 2. Submit the fixed prompt with the positive source text. Copy the complete response without correction into the positive case `raw_output_text`. Set `parse_status` to `valid_json` and `parsed_output` to the parsed object only when the response is valid JSON; otherwise set `parse_status` to `invalid_json` and `parsed_output` to `null`.

- [ ] **Step 2: Run the negative case once**

Use the same provider, model, prompt and model settings. Submit `examples/dairy_rnd.json` as the material and record `raw_output_text`, `parse_status` and `parsed_output` using the same rule as the positive case.

- [ ] **Step 3: Run the control case once**

Use the same provider, model, prompt and model settings. Submit `examples/supply_chain_exception.json` as the material and record `raw_output_text`, `parse_status` and `parsed_output` using the same rule as the positive case.

- [ ] **Step 4: Enforce the call limit**

Confirm exactly three model calls were made. Do not retry malformed output or change the prompt during this Gate. A malformed response is Gate 1 evidence and contributes to `no_go`.

### Task 4: Validate evidence and make the gate decision

**Files:**

- Modify: `/Users/eddie/Desktop/Workspace/.local-sensitive/ontology-poc-generator/experiments/2026-09-01-gate1-evidence.json`
- Modify in repository: none

- [ ] **Step 1: Validate the evidence record structure**

Run:

```bash
jq -e '
  .schema == "ontopoc_gate1_evidence.v1"
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
' /Users/eddie/Desktop/Workspace/.local-sensitive/ontology-poc-generator/experiments/2026-09-01-gate1-evidence.json
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
' /Users/eddie/Desktop/Workspace/.local-sensitive/ontology-poc-generator/experiments/2026-09-01-gate1-evidence.json
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
cd /Users/eddie/Desktop/Workspace/ontology-poc-generator/.worktrees/pc-agent-modeling-demo
git status --short --branch
```

Expected: the same clean repository state observed in Task 1. Do not run backend or frontend test suites because this experiment changes no repository behavior.

- [ ] **Step 6: Overwrite the relay state**

If `no_go`, set the next minimum action to “stop product expansion and review the failed Gate 1 condition”; do not create a Gate 2 plan.

If `go`, set the next minimum action to “request approval for the candidate schema version strategy”; create no code and make no schema decision inside this plan.

## Completion boundary

This plan is complete when the local-sensitive evidence JSON passes the structural checks, contains the unedited three-call outputs and manual baseline, records a single `go / no-go`, and the OntoPoc repository remains unchanged. Passing repository tests is not a substitute for this evidence.
