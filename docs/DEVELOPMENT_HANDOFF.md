# OntoPoc 开发接力文档

最后更新：2026-08-30

远端仓库：`https://github.com/Longado/ontopoc`

远端主分支基线：`e632590`

产品需求：[PRD](PRD.md)

## 1. 一句话接力

OntoPoc 已经从静态本体 Demo 推进到可运行的确定性规则内核。下一步不要再新增抽象能力，直接把后端生成的真实 `ValidationReceipt` 接入 PC Demo 的 Validation 页面，再完成可分享的预览部署。

## 2. 当前产品范围

首个业务问题固定为：

> 哪些订单应该进入优先干预队列，为什么？

当前产品是 PC-first 的 `synthetic_demo`：

```text
业务材料
→ Recognition candidate
→ DecisionPack
→ OntologySpec
→ categorical_all_of_v1 规则验证
→ ValidationReceipt
→ 人工审查（下一阶段）
```

当前不做手机端、生产数据库、客户真实数据、自动发布、Action、外部系统写回和多人协作。

## 3. 已实现能力

### 3.1 后端领域内核

- 严格 JSON 场景输入；
- 确定性 Proposal CLI；
- opt-in 知识单元与来源闭包；
- 不可变 `DecisionPack` 及 canonical hash；
- `DecisionPack → OntologySpec` 编译；
- entity、relation、property、rule 的稳定身份；
- spec schema、引用闭包和 blocking issue 校验；
- OpenAI-compatible 模型识别入口；
- 受控 Recognition candidate，模型不能注入事实、Action 或执行结果；
- 不可变 `ValidationReceipt`；
- 内存 `SyntheticFactSet` 和 canonical facts hash；
- `categorical_all_of_v1` 四态求值：
  - `pass / in_queue`
  - `fail / not_in_queue`
  - `not_evaluable / information_insufficient`
  - `unsupported / unsupported`
- 回执绑定 pack、spec、facts hash、rule ID、fact refs 和 evidence refs；
- 缺少条件事实时生成稳定 `not_evaluable` 回执；
- 所有回执固定：
  - `draft_created=false`
  - `published=false`
  - `actions_executed=false`
  - `external_write=false`

关键文件：

- `src/ontology_poc_generator/decision_pack.py`
- `src/ontology_poc_generator/ontology_spec.py`
- `src/ontology_poc_generator/spec_compiler.py`
- `src/ontology_poc_generator/recognition.py`
- `src/ontology_poc_generator/recognition_cli.py`
- `src/ontology_poc_generator/validation_receipt.py`
- `src/ontology_poc_generator/rule_runtime.py`
- `tests/test_rule_runtime.py`

### 3.2 固定供应链验证场景

规则仅支持 `categorical_all_of_v1`。固定四笔事实为：

| 场景 | baseline | candidate |
|---|---|---|
| `missed + none` | `pass / in_queue` | `pass / in_queue` |
| `at_risk + none` | `fail / not_in_queue` | `pass / in_queue` |
| `on_track + available` | `fail / not_in_queue` | `fail / not_in_queue` |
| `missed + qualification unavailable` | `not_evaluable / information_insufficient` | 同左 |

固定输入：

- `knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json`
- `tests/fixtures/knowledge/order_priority_policy_synthetic_candidate_v2.json`
- `tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json`

### 3.3 PC Demo

当前前端已经有：

- `/` 和 `/demo` 独立工作台；
- `/landing` 产品介绍页；
- 三个固定文档建模场景；
- 录制式 Recognition candidate；
- candidate 确认步骤；
- DecisionPack 展示；
- OntologySpec 图、详情和 deterministic artifact 问答；
- spec hash、closure 和 compilation status；
- PC 宽屏布局。

关键文件：

- `landing-page/public/artifacts/supply-chain-recognition.json`
- `landing-page/src/StandaloneDemo.jsx`
- `landing-page/src/TrialWorkspace.jsx`
- `landing-page/src/trialWorkspaceModel.js`
- `landing-page/src/OntologyWorkspace.jsx`
- `landing-page/src/ontologyWorkspaceModel.js`

## 4. 尚未实现或尚未接通

以下内容不能写成已完成：

1. PC Demo 的 Validation 页面仍显示 `receipt = null`；
2. 后端真实 `ValidationReceipt` 尚未写入前端 artifact；
3. 前端没有调用 Python 领域内核；
4. 模型识别 CLI 尚未连接浏览器输入；
5. 没有人工 review/version/publication；
6. 没有 `DecisionDelta`；
7. 没有数据库、账号、持久化和生产 API；
8. 没有真实客户事实和业务效果证据；
9. 没有正式公网部署地址。

仓库中的 README 和 ROADMAP 对 Loop 3 的描述落后于代码。更新它们之前，应先完成 Validation artifact 与 PC 页面接通，并以一次完整黄金场景验证作为 Loop 3 出口证据。

## 5. Git 与本地 Workspace 状态

### 5.1 严禁直接修改的主目录

主目录：

```text
/Users/eddie/Desktop/Workspace/ontology-poc-generator
```

该目录仍停在旧本地 `main`，并含用户内容：

```text
M  README.md
?? docs/HANDOFF_FRONTEND_BACKEND_ALIGNMENT.md
?? landing-page/
```

不要 stash、clean、reset、删除、移动或提交这些内容。

### 5.2 当前隔离开发目录

```text
/Users/eddie/Desktop/Workspace/ontology-poc-generator/.worktrees/pc-agent-modeling-demo
```

历史 worktree 已经收起。开始新能力时，应先：

```bash
git fetch origin
git status --short
git worktree list
git branch -vv
git switch -c codex/<small-capability> origin/main
```

每个小能力完成后：focused test、一次 full test、`git diff --check`、scope/status 检查、commit、push、独立 P1/P2 review、PR、CI、merge。

### 5.3 Workspace 归档

2026-08-30 已归档：

```text
/Users/eddie/Desktop/Workspace/archive/2026-08-30-inactive
```

其中 `llm-wiki-local` 的未提交状态被完整保留；没有 reset 或删除。

## 6. 本地运行与验证

### 6.1 后端全量测试

```bash
cd /Users/eddie/Desktop/Workspace/ontology-poc-generator/.worktrees/pc-agent-modeling-demo
PYTHONPATH=src python -m unittest discover -s tests -v
```

当前主分支证据：`249 tests, OK`。

### 6.2 Loop 3 focused test

```bash
PYTHONPATH=src python -m unittest tests.test_rule_runtime -v
```

当前证据：`6 tests, OK`。

### 6.3 生成 DecisionPack 与 OntologySpec

输出目录建议使用临时目录，不要把生成物提交进仓库：

```bash
PYTHONPATH=src python -m ontology_poc_generator.cli \
  examples/supply_chain_exception.json \
  --knowledge-unit knowledge/supply_chain/supplier_evidence_boundary_v1.json \
  --knowledge-unit knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json \
  --decision-pack-output /tmp/ontopoc-decision-pack.json \
  --ontology-spec-output /tmp/ontopoc-ontology-spec.json \
  --output /tmp/ontopoc-proposal.md
```

### 6.4 模型识别 CLI

模型密钥只通过环境变量提供，不能写进命令、文档或仓库：

```bash
EIP_MODEL_API_BASE=<openai-compatible-base> \
EIP_MODEL_NAME=<model-name> \
EIP_MODEL_API_KEY=<secret> \
PYTHONPATH=src python -m ontology_poc_generator.recognition_cli \
  /path/to/business-description.txt \
  --knowledge-unit knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json \
  --output /tmp/ontopoc-recognition.json
```

当前只是 CLI，不是浏览器实时模型能力。

### 6.5 PC Demo

```bash
cd landing-page
npm ci
npm run test:unit
npm run test:sites
npm run build
npm run dev -- --host 127.0.0.1 --port 5174
```

当前验证证据：`58` 个 unit tests、`4` 个 Sites tests 通过，生产构建完成 `1973` 个 modules transformed。

本地地址：

- 工作台：`http://localhost:5174/`
- Demo：`http://localhost:5174/demo`
- Landing：`http://localhost:5174/landing`

目标视口为 1280×720 及以上，不验收手机端。

## 7. 下一步执行顺序

### Task 1：生成包含真实回执的固定 artifact

目标：由 Python 领域内核为 baseline/candidate 四笔事实生成真实 `ValidationReceipt`，形成稳定 JSON artifact。

要求：

- artifact 字段来自后端 canonical projection；
- 不在前端重新实现规则；
- 同一输入字节和 hash 稳定；
- 不包含客户事实、Action 或发布状态；
- focused/full unittest 和 diff-check 通过。

建议提交：

```text
feat: record synthetic validation receipts
```

### Task 2：接入 PC Validation 页面

目标：替换当前 `receipt = null` 空状态，展示四笔事实及 baseline/candidate 结果。

要求：

- 展示 status、decision result、rule ID、fact/evidence refs 和三个内容 hash；
- 明确显示四个零副作用字段；
- `at_risk + none` 清楚展示 baseline fail → candidate pass；
- 不新增前端 evaluator；
- 保持其他三阶段和旧 artifact hash 校验；
- 运行前端 unit/Sites/build，并在 PC 浏览器验证。

建议提交：

```text
feat: show validation receipts in pc demo
```

### Task 3：关闭 Loop 3 文档状态

只有 Task 1–2 完整通过后，才能更新 README、ROADMAP 和 PRD 的能力状态。

记录：

- 后端与前端真实测试数；
- golden artifact hash；
- 四笔事实结果；
- PR 与 merge commit；
- 明确没有 review/version/publication/Action/writeback。

### Task 4：发布可分享预览

在本地 PC 验证完成后，再发布静态预览。发布前确认：

- `/`、`/demo`、`/landing` 均可直接访问；
- 刷新深层路由不返回 404；
- artifact 可以加载；
- Validation 不再为空；
- 页面无密钥、客户数据或虚构生产结果；
- 保留上一可用构建作为回退版本。

## 8. 开发边界

继续坚持：

- `candidate` 不自动变成 `confirmed`；
- `suggestion` 不自动变成业务事实；
- `pass` 只表示合成规则匹配，不表示客户批准；
- workflow 只能汇总已有领域状态，不能维护第二套真相；
- 不把前端演示状态冒充后端执行结果；
- 不自动 review、publish、创建任务或写回；
- 不提前增加数据库、通用 Agent 框架、RAG、向量库、图数据库或行业模板市场。

## 9. 最近已合并提交

| 能力 | PR | Merge commit |
|---|---|---|
| PC Demo 与 Agent candidate | `#7` | `e05a455` |
| OntologySpec 窄屏空白修复 | `#8` | `6ca917f` |
| 正式产品 PRD v0.2 | `#9` | `17a9b94` |
| Loop 3 synthetic rule runtime | `#10` | `e632590` |

Loop 3 代码提交：

- `92263e4 feat: evaluate synthetic decision rules`
- `3206450 fix: preserve incomplete fact receipts`

## 10. 可直接复制给下一位开发者的 Prompt

```text
接手开发 /Users/eddie/Desktop/Workspace/ontology-poc-generator。

先阅读 docs/DEVELOPMENT_HANDOFF.md 和 docs/PRD.md。远端 main 基线至少为 e632590。

严禁修改主目录中用户已有的 README.md、docs/HANDOFF_FRONTEND_BACKEND_ALIGNMENT.md 和未跟踪 landing-page/。只在 .worktrees 下的干净隔离 worktree 工作。

当前后端已实现 categorical_all_of_v1 四态运行时和 hash-bound ValidationReceipt，249 tests 通过；前端 Validation 页面仍是 receipt=null。

下一步只完成：
1. 用 Python 内核为固定四笔 synthetic facts 生成真实 baseline/candidate ValidationReceipt artifact；
2. 将真实 receipt 接入 PC Demo Validation 页面；
3. 不在前端重写 evaluator；
4. 不增加数据库、Action、发布、外部写回或手机端。

每个小能力执行 focused test、一次 full test、git diff --check、scope/status 检查、独立 P1/P2 review、commit、push、PR、CI、merge。报告真实测试数、commit、PR 和尚未实现的边界。
```
