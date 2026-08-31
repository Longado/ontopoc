# OntoPoc 开发接力文档

最后更新:2026-08-31(v2.2,按当前本地 validation artifact 与前端投影实现收口)

远端仓库:`https://github.com/Longado/ontopoc`(私有)

远端主分支基线:`9b251d0`(PR #11 合并点)

产品需求:[PRD](PRD.md) · 路线:[ROADMAP](ROADMAP.md)

## 0. 接手第一步:对账

本文档以远端已合并基线 `9b251d0` 加当前本地分支 9 个 validation 实现提交(`df89bb6^..3848af3`)为依据。这 9 个实现提交和当前文档收口均尚未 merge / push,不要把本文状态当成远端或已交付状态。接手时先对当前 checkout 对账:

```bash
cd /Users/eddie/Desktop/Workspace/ontology-poc-generator/.worktrees/pc-agent-modeling-demo
git status --short --branch
git log --oneline 9b251d0..HEAD
```

先确认工作树状态,再读新增提交；本文只描述当前本地 checkout,不证明远端已同步。

当前本地快照的快速核验命令:

```bash
PYTHONPATH=src python -m unittest discover -s tests 2>&1 | tail -3       # Ran 257 tests ... OK
PYTHONPATH=src python scripts/generate_demo_artifact.py --check          # exit 0,不写文件
cd landing-page && npm run test:unit 2>&1 | grep -E "^ℹ (tests|fail)"   # tests 84 / fail 0
npm run test:sites 2>&1 | grep -E "^ℹ (tests|fail)"                     # tests 4 / fail 0
npm run build 2>&1 | grep "modules transformed"                         # 1973 modules transformed
```

## 1. 一句话接力

内核、validation artifact 和前端只读回执投影已经接通,但**产品还没有随输入变化的输出**:LLM 只能填一张闭集表单,本体和规则来自常量模板,prompt 从未对真模型跑过。现有内核和演示全部冻结;下一步只按 Gate 1–3 验证材料贡献、知识命中和相对人工的价值。任一 Gate 失败即停止扩张。

## 2. 项目是什么

OntoPoc 帮 FDE 把一段业务材料收敛成可审查的决策资产。首个也是唯一的业务问题:

> 哪些订单应该进入优先干预队列,为什么?

管道:

```text
业务材料(文本)
→ recognition.py:LLM 输出 scenario_intake_candidate.v1(闭集表单)
→ ScenarioParameters(models.py)
→ compile_decision_pack + 知识单元匹配(compiler.py / knowledge.py)→ DecisionPack(hash)
→ compile_ontology_spec(provided_compiler.py + knowledge_compiler.py)→ OntologySpec(hash + 引用闭包)
→ evaluate_synthetic_rule(rule_runtime.py)→ ValidationReceipt(hash,四态,零副作用)
→ 人工审查(未做)
```

前端是一个只读工作台,把后端事先生成的 artifact JSON 投影成四个阶段页面。Validation 阶段为 `receipt_recorded`;前端不调用 Python,不做规则求值,也不重算 SHA。

## 3. 真实状态诊断(v2 新增,接手人最该读的一节)

### 3.1 做得好的

- 边界在代码里不在 prompt 里:`rule_runtime.py:243-246` 把四个零副作用字段写死 `False`;`recognition.py:203` 起的 `_validate_candidate` 拒绝一切额外字段;`decision_owner` 必须是原文子串(`recognition.py:392`)。
- 一切可 hash、可重放:同一输入两次运行 DecisionPack / OntologySpec 文件 md5 完全一致(8-30 实测)。
- 当前本地快照为后端 257 个测试、前端 unit 84 个测试、Sites 4 个测试和 Vite build 1973 modules;不支持的 `rule_kind` 在编译期(`knowledge_compiler.py:125`,blocking issue)和求值期(`rule_runtime.py:203`,`unsupported`)两道都拦。

### 3.2 三个信息入口,现在各开多大

产品要有价值,输出里得有"输入没写、模板也没写死"的东西。它只能来自三个口:

| 入口 | 机制在不在 | 现在开多大 | 代码位置 |
|---|---|---|---|
| **材料口**(从业务文本提取对象/关系/事实) | 在,但被 prompt 关上 | 模型只准填:match_status 3 选 1、参与者 4 勾、约束 4 勾、数据源 3×3、动作 3 勾、决策人逐字抄、trigger 一句话。≈20 bit + 一句话 | `recognition.py:78-101`(`_SYSTEM_PROMPT` 明令"不要输出对象、关系、规则")、`_scenario_from_candidate` L296-374(role binding / bridge / readiness 全写死,`relations: []`) |
| **知识口**(顾问经验以知识单元注入) | 五类追问型贡献(`constraint / data_requirement / acceptance_question / readiness_gap / relation_semantics`)是真通用的,按 decision_key + role + bridge 门控;**但 `decision_rule` 这一类是单条硬编码**:`knowledge.py:66-77` 把 S-1 规则的字段名和允许值(`{"missed","at_risk,missed"}` / `{"none"}`)全锁死,语义不同的规则单元加载即拒 | **只有 1 个真单元** `supplier_evidence_boundary_v1`(7 条模板,"采购历史≠供应商资质"是真顾问判断)+ 1 条合成规则单元。S-1 的事实在 `recognition.py` 和 `knowledge.py` 各手抄一份,无共享源 | `knowledge.py:66-77`、`knowledge.py:775`(`match_knowledge_unit`)、`knowledge/supply_chain/*.json` |
| **规则口**(可求值的规则形态) | 在 | 只有 `categorical_all_of_v1`(两个枚举条件都命中)。任何带阈值的真实政策(延期 > N 天、金额 > M)表达不了 | `knowledge_compiler.py:49`、`rule_runtime.py:203` |

结论:**任何被判 `matched` 的材料 → 同样 3 个实体(来自 3 条写死的 role binding)、同样 1 条 REQUIRES(写死的 bridge)、同样 1 条规则。** 8-30 检查 `landing-page/public/artifacts/supply-chain-recognition.json`:entity_types 3、relation_types 3、rules 由知识单元给。

注意一个容易看错的地方:`_PROFILE_OBJECTS` 那 9 个中文标签(客户订单、订单行、物料……)**不进 OntologySpec**,只进 `generator.py` 的 markdown 叙事层(`generator.py:36`)。Spec 里的实体只由 `object_role_bindings` 决定(`provided_compiler.py:46`)。

### 3.3 PRD 与代码自相矛盾的一处

PRD FR-003"展示候选决策、对象、关系、规则及对应证据片段"和 FR-017"每个关键候选包含原文片段"要求模型提取并定位证据;`recognition.py` 的 `_SYSTEM_PROMPT` 禁止模型输出对象和关系。两边只能留一个。本文档第 6 节按"打开材料口、用代码校验证据片段"来解,PRD 不用改。

### 3.4 从未对真模型验证

- Demo 里的 candidate 是 `scripts/generate_demo_artifact.py` 用 `DeterministicDemoGateway` 造的,artifact 里 `provider="recorded_demo_gateway"`、`realtime_model_call:false`。
- 22 个 `test*.py` 文件里没有一个碰真模型或真网络(`test_model_gateway.py` 用内存 `FakeResponse`,`test_recognition_cli*.py` mock 掉 gateway)。
- 没有 golden set。`PROMPT_VERSION = "order_priority_intervention.v1"` 从未被任何真实输出检验过。

### 3.5 其他已知债务

- CI(`.github/workflows/tests.yml`)只跑后端 unittest,前端 84/4/build 不在 CI 里。
- `landing-page/src/App.jsx` 有 50 行超过 300 字符(整段 JSX 和双语文案压成一行),`TrialWorkspace.jsx` 5 行、`styles.css` 5 行同样。可维护性差,过一遍 prettier 即可。
- 前端问答(`ontologyWorkspaceModel.js:446-536`)是一段手写正则意图分类器(含 prompt-injection 关键字表),只对这一个固定 artifact 有效。它是演示道具,不是能力,不要在此基础上扩展。
- 前端适配器(`trialWorkspaceModel.js`)校验 hash 格式、baseline/candidate identity coherence、candidate entity/relation/property/rule/suggestion/source 引用闭包、receipt rule/fact/evidence 引用闭包和四个副作用字段,但不重算 SHA。任何缺字段或绑定不一致都会抛错并落到通用 error 页,即 fail closed;前端不维护第二套 evaluator 或 authority。
- **决策问题只有一个**:写死的 `order_priority_intervention` 是否对应现役客户的真实诉求,仓库里没有任何证据(没有客户材料、没有实验记录)。见 §6 Gate 1。
- 本地有 14 条已合并的 `codex/*` 分支未删。
- `knowledge.py` 的 `applicability.readiness_requirement_keys` 只做结构校验,`match_knowledge_unit` 里没有用它做门控;真正起作用的是 `readiness_gap` 模板级过滤(`knowledge.py:845`)。

## 4. 架构地图

### 4.1 后端(`src/ontology_poc_generator/`,5084 行,零第三方依赖,Python ≥ 3.11)

| 模块 | 行 | 职责 | 关键符号 |
|---|---|---|---|
| `models.py` | 597 | 输入契约与全部输入校验 | `ScenarioParameters`, `ObjectRoleBinding`, `DeclaredBridge`, `ReadinessDeclaration` |
| `knowledge.py` | 882 | 知识单元 schema、适用性门控、匹配 | `KnowledgeUnit`, `load_knowledge_unit`, `match_knowledge_unit`, `KnowledgeOutcome` |
| `compiler.py` | 79 | Scenario + 知识单元 → DecisionPack | `compile_decision_pack` |
| `decision_pack.py` | 268 | 不可变 DecisionPack + canonical hash | `DecisionPack`, `decision_pack_content_hash` |
| `provided_compiler.py` | 94 | role binding / bridge → 实体、关系 | `compile_provided_spec` |
| `knowledge_compiler.py` | 336 | 适用建议 → 关系 / 属性 / 规则 / 编译问题 | `compile_knowledge_profiles` |
| `spec_compiler.py` | 33 | 拼装 + 引用闭包 | `compile_ontology_spec` |
| `ontology_spec.py` | 542 | OntologySpec 各子类型、序列化、hash | `OntologySpec`, `RuleDeclarationSpec`, `ontology_spec_content_hash` |
| `validation.py` | 428 | Spec 对 Pack 的引用闭包校验 | `validate_reference_closure` |
| `identity.py` | 94 | sha256 稳定 ID | `stable_*_id` |
| `rule_runtime.py` | 247 | 单条规则对合成事实求值 | `SyntheticFactSet`, `evaluate_synthetic_rule` |
| `validation_receipt.py` | 165 | 回执契约 + hash | `ValidationReceipt`, `EvaluationStatus`, `DecisionResult` |
| `recognition.py` | 451 | LLM 识别契约、候选校验 | `_SYSTEM_PROMPT`, `recognize_scenario`, `build_recognition_demo_envelope` |
| `model_gateway.py` | 87 | OpenAI-compatible JSON-mode HTTP 客户端 | `OpenAICompatibleGateway` |
| `recognition_cli.py` | 140 | 文本 → 识别 → demo 信封 | `ontopoc-recognize` |
| `cli.py` | 248 | 场景 JSON → Proposal / Pack / Spec 文件 | `ontopoc` |
| `generator.py` / `renderers.py` | 61 / 304 | markdown 叙事层(与 Spec 管道平行,不在其下游) | `generate_proposal`, `render_markdown` |
| `errors.py` | 18 | 错误分类 | — |

计算 vs 常量,按 Spec 的三类元素:

| Spec 元素 | 来源 | 随输入变化的部分 | 写死的部分 |
|---|---|---|---|
| `entity_types` | `object_role_bindings` | 有几条 binding 就几个实体 | binding 本身在 `recognition.py` 写死 3 条 |
| `relation_types` | `declared_bridges` + 知识单元 `relation_semantics` | 无 | bridge 写死 1 条;知识单元的 predicate/description 是 JSON 常量 |
| `rule_declarations` | 知识单元 `decision_rule` | `subject_type_id`、`rule_id` | rule_kind、条件、结论值全来自知识单元 JSON |

### 4.2 前端(`landing-page/`,Vite 6 + React 19 + @xyflow/react,无路由库)

| 文件 | 行 | 职责 |
|---|---|---|
| `main.jsx` / `appSurfaceModel.js` | 14 / 4 | `/landing` → `App`,其余一切路径 → `StandaloneDemo` |
| `App.jsx` | 451 | 营销页,双语文案内联 |
| `StandaloneDemo.jsx` | 47 | `/` 与 `/demo` 的壳 |
| `TrialWorkspace.jsx` | 282 | 四阶段工作台;读取 artifact 并展示 4 cases / 8 receipts、证据、hash 与边界 |
| `trialWorkspaceModel.js` | 714 | `adaptTrialArtifact`:严格校验 schema、baseline/candidate identity coherence、candidate/reference closure 和回执绑定;Validation stage=`receipt_recorded` |
| `OntologyWorkspace.jsx` / `ontologyWorkspaceModel.js` | 469 / 536 | React Flow 图、节点详情、正则问答 |
| `DocumentModeler.jsx` / `documentModelingDemoModel.js` | 218 / 67 | 三个写死的场景;只有第一个走真 artifact,另两个是纯前端静态图 |
| `agentModelingSession.js` | 161 | "确认"步骤的会话内 hash 交叉检查,不持久化 |
| `worker/index.js` + `.openai/hosting.json` | — | SPA 回退 worker;宿主是 OpenAI Sites(`d1`/`r2` 声明为 null 未用) |

数据流:`public/artifacts/supply-chain-recognition.json`(后端 `scripts/generate_demo_artifact.py` 生成)→ `adaptTrialArtifact` → `projectOntologyWorkspace` / Validation 投影 → 页面。baseline 顶层 pack/spec 是唯一权威,validation authority 只存 JSON refs + hash;candidate 独立携带 pack/spec。前端不做规则求值或 SHA 重算。

## 5. 已实现 / 未实现(修正版)

已实现:第 3.1 节 + 后端固定 `validation_run.v1` 与前端只读回执投影。后端以固定 4 个 case 分别求值 baseline/candidate,生成 8 个真实 `validation_receipt.v1`;每个回执带 canonical receipt hash,并绑定 pack/spec/facts hash、rule、fact refs 和 evidence refs,四个副作用字段固定为 `false`。artifact 默认写入采用同目录 temp + fsync + 单次 `os.replace`,保留 existing artifact 的 permission bits,新文件固定为 `0644`;`--check` 只读比较 canonical bytes,相同返回 0,missing/stale 返回 1 且不写。

未实现,不能写成已完成:

1. 前端不调用 Python 内核,模型识别 CLI 未连浏览器;
2. **模型从未提取过对象或关系**(3.2);
3. **知识单元只有一个真单元**(3.2);
4. **只有一种规则形态**(3.2);
5. prompt 从未对真模型验证,无 golden set(3.4);
6. review / version / publication / `DecisionDelta` / action 都是 `not_started`;
7. 没有数据库、账号、持久化、生产 API;
8. 没有真实客户事实和业务效果证据;
9. 没有正式公网地址。

生命周期必须分开读:`validation=completed` 表示后端固定合成求值已完成,前端 `receipt_recorded` 表示这些回执已被投影;单条 `pass` 只表示输入满足规则。三者都不等于人工 review、publication、action、客户确认或生产运行。

## 6. 下一步执行顺序(v3,收枝版)

### 6.1 决策原则

当前问题不是可信度层不够,而是系统尚未证明能从真实材料产生模板外信息。现有内核、固定 validation artifact、前端影子校验、Agent confirmation session 和正则问答全部冻结,不删除也不扩展。后续工作最多只有三个 Gate,每个 Gate 都有停止条件;通过一个 Gate 不会自动授权下一个平台能力。

| Gate | 测什么 | 过线 | 失败后 |
|---|---|---|---|
| J1 材料贡献 | 输出是否真的来自材料 | 硬编码兜底占比 < 50%;两份材料 binding 结构可区分;同材料 5 次 binding 一致率 ≥ 80% | 停止转换代码,退回人工 Markdown |
| J2 知识命中 | 现有知识是否产生准确追问 | CQ 命中 ≥ 3 条,误触 0 | 不批量增加知识单元,先修适用性问题或停止 |
| J3 相对价值 | 管道是否比用户手写值得 | 覆盖不低于手写且耗时不超过 3 倍;真实 FDE 与业务参与者共同 `go` | 退回 Markdown 清单 + KnowledgeUnit JSON,不做产品平台 |

### 6.2 Gate 1:零代码材料信号

**状态:`blocked_by_user_selected_redacted_material`。**

1. 材料由用户指定:一份现役决策正例、一份明确负例和当前合成对照。正例必须先确认真实诉求就是“哪些订单进入优先干预队列”。
2. 使用开放式 prompt 独立运行,不接现有 candidate schema、转换代码或 CLI;检查是否出现材料中存在、模板中不存在且可定位原文的对象或关系。
3. 用户对正例先手写 5 条判断并记录耗时,作为 J3 基线。
4. 客户原文、开放 prompt 原始输出和人工基线只保存到 workspace `.local-sensitive/ontology-poc-generator/experiments/`;仓库最多保存经用户确认可公开的脱敏指标、输入 hash、模型和 prompt 版本。

通过:正例决策匹配;出现模板外结构;负例为 `unsupported`;初步覆盖不低于人工。任一不满足即停止,不进入 Gate 2。

### 6.3 Gate 2:单纵切材料口

**状态:`blocked_by_gate_1`。**

只实现 `extracted_object + evidence_span + closed role vocabulary + code-generated stable ID`。代码范围默认限制为 `recognition.py` 和 Recognition tests;不改前端,不做关系抽取、predicate 聚合、去噪框架、`threshold_v1`、批量知识单元或通用 schema 框架。

代码护栏:

1. `candidate_role_key` 只能来自已发布闭集;
2. `evidence_span` 必须是原文子串,否则整条拒绝;
3. stable ID 由代码生成,模型不编 ID;
4. 负例继续走 `unsupported`,未知对象显式保留 unknown,不做最近匹配。

验证:J1 与 J2 分开计量,知识口不得替材料口撑过判据。最多允许一次 prompt 或词表修正;仍不过线即停止。

### 6.4 Gate 3:真实使用价值

**状态:`blocked_by_gate_2`。**

使用现有 Markdown 输出与用户手写 5 条判断对照,不先建设 review/version 系统。记录两边耗时、覆盖、错误、遗漏和实际有用的知识追问;由一名真实 FDE 与一名供应链业务参与者判断是否能理解、纠正或复用。

只有 J3 通过且两名参与者共同形成 `go`,才根据真实阻塞另立一个最小计划。数值政策确实阻塞时才评估 `threshold_v1`;反复比较修订影响时才评估 `DecisionDelta`;重复运行出现保存与恢复问题时才评估 Application Service/Repository。

### 6.5 明确不做(Gate 1–3 达成前)

批量知识单元、`threshold_v1`、前端问答扩展、Agent session/confirmation 扩展、前端 receipt/schema 框架、DecisionDelta、review/version/publication、Application Service 抽象、数据库、账号、公网部署、API/EIP、通用 Agent 框架、RAG、向量库、图数据库、手机端和外部行动。

## 7. 本地运行与验证

### 7.1 后端

```bash
cd /Users/eddie/Desktop/Workspace/ontology-poc-generator/.worktrees/pc-agent-modeling-demo
PYTHONPATH=src python -m unittest discover -s tests -v        # 当前本地快照:257 OK
PYTHONPATH=src python -m unittest tests.test_rule_runtime -v  # 6 OK
PYTHONPATH=src python scripts/generate_demo_artifact.py --check # canonical artifact 相同则 0,只读
```

生成 DecisionPack / OntologySpec(输出放临时目录,不进仓库;两次运行 md5 应一致):

```bash
PYTHONPATH=src python -m ontology_poc_generator.cli \
  examples/supply_chain_exception.json \
  --knowledge-unit knowledge/supply_chain/supplier_evidence_boundary_v1.json \
  --knowledge-unit knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json \
  --decision-pack-output /tmp/ontopoc-decision-pack.json \
  --ontology-spec-output /tmp/ontopoc-ontology-spec.json \
  --output /tmp/ontopoc-proposal.md
```

模型识别 CLI(密钥只走环境变量,不进命令、文档、仓库):

```bash
EIP_MODEL_API_BASE=<openai-compatible-base> \
EIP_MODEL_NAME=<model-name> \
EIP_MODEL_API_KEY=<secret> \
PYTHONPATH=src python -m ontology_poc_generator.recognition_cli \
  /path/to/business-description.txt \
  --knowledge-unit knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json \
  --output /tmp/ontopoc-recognition.json
```

### 7.2 前端

```bash
cd landing-page
npm ci
npm run test:unit    # 当前本地快照:84
npm run test:sites   # 4
npm run build        # 1973 modules transformed
npm run dev -- --host 127.0.0.1 --port 5174
```

`http://localhost:5174/`、`/demo`、`/landing`。目标视口 1280×720 以上,不验收手机端。

### 7.3 固定供应链场景(四笔合成事实)

| 场景 | baseline | candidate |
|---|---|---|
| `missed + none` | `pass / in_queue` | `pass / in_queue` |
| `at_risk + none` | `fail / not_in_queue` | `pass / in_queue` |
| `on_track + available` | `fail / not_in_queue` | `fail / not_in_queue` |
| `missed + qualification unavailable` | `not_evaluable / information_insufficient` | 同左 |

输入:`knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json`、`tests/fixtures/knowledge/order_priority_policy_synthetic_candidate_v2.json`、`tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json`。

### 7.4 Artifact 恢复决策

| 观察到的状态 | 最小处置 | 不应做什么 |
|---|---|---|
| artifact missing / stale | 用脚本内同一组固定输入运行 `PYTHONPATH=src python scripts/generate_demo_artifact.py`,再用 `--check` 核对 canonical bytes | 不手改 committed JSON,不把 stale 当可继续投影 |
| hash / binding mismatch | 前端 fail closed;回到后端 authority 和固定输入重新生成,定位 pack/spec/facts/receipt 或引用闭包的差异 | 不在前端放宽校验,不重算另一套结果 |
| `not_evaluable` | 固定黄金第四 case 的 `not_evaluable` 是合法验收结果,应保留并核对 missing/unavailable fact 与 evidence refs；只有某个受测输入按预期本应可求值时,才通过受测 fixture / 输入变更补齐后重新生成 | 不把合法信息不足当故障,不常规重写固定 artifact,不对同一份缺失事实盲重试 |
| `unsupported` | 记录为 evaluator / rule contract 的能力缺口,另行设计并测试支持范围 | 不把它降级成 `fail` 或 `pass` |
| 写入中断 / `os.replace` 失败 | 旧 artifact 及其 permission bits 仍保留;排除文件系统问题后用同一固定输入重跑。成功替换保留 existing mode,新文件为 `0644` | 不把临时文件或部分内容当新权威 |

这张表只处理单文件本地 artifact 的确定性再生成和 fail-closed 展示,不是 Saga,也不提供外部系统补偿。当前没有数据库事务、账号状态、Action、publication 或外部 writeback 可补偿。

## 8. Git 与本地目录

### 8.1 严禁改动的主目录

`/Users/eddie/Desktop/Workspace/ontology-poc-generator` 停在旧本地 `main`(`e75da63`),且是**设计 QA 的工作现场**:未跟踪的 `landing-page/` 与仓库版差 49 处(多出 `AGENTS.md`、`audit-*`、`qa-*` 截图目录、`ontopoc-lockup.png`)。状态:

```text
 M README.md
?? docs/HANDOFF_FRONTEND_BACKEND_ALIGNMENT.md
?? landing-page/
```

不要 stash、clean、reset、删除、移动或提交。

### 8.2 开发目录

`/Users/eddie/Desktop/Workspace/ontology-poc-generator/.worktrees/pc-agent-modeling-demo`。当前 validation 链必须先继续这个 worktree 的 `rico/handoff-v2` 精确 HEAD:

```bash
git switch rico/handoff-v2
git status --short --branch
git rev-parse HEAD
```

当前 `origin/main` 尚不含 `df89bb6^..3848af3` 及后续文档收口,不得从它开分支继续 validation 链。只有这些提交落地且更新后的 `origin/main` 已包含它们后,才执行 `git switch -c <owner>/<small-capability> origin/main`。

每个小能力:focused test → 一次 full test → `git diff --check` → scope/status 检查 → commit → push → 独立 review → PR → CI → merge。

### 8.3 归档

`/Users/eddie/Desktop/Workspace/archive/2026-08-30-inactive`(含 `llm-wiki-local` 未提交状态,未 reset)。

## 9. 开发边界(不变)

- `candidate` 不自动变 `confirmed`;`suggestion` 不自动变业务事实;
- `validation=completed` 只表示固定合成求值完成;`receipt_recorded` 只表示前端记录式投影可见;
- `pass` 只表示合成规则匹配,不表示客户批准;
- 前端只投影后端状态,不维护第二套真相,不冒充执行结果;
- 不自动 review、publish、创建任务或写回;
- Gate 2 打开材料口后,新增的硬规则:**没有原文 span 的候选不得进入 ScenarioParameters**。

## 10. 已合并提交

| 能力 | PR | Merge |
|---|---|---|
| PC Demo 与 Agent candidate | #7 | `e05a455` |
| OntologySpec 窄屏空白修复 | #8 | `6ca917f` |
| 产品 PRD v0.2 | #9 | `17a9b94` |
| Loop 3 synthetic rule runtime | #10 | `e632590` |
| 开发接力文档 v1 | #11 | `9b251d0` |

当前本地分支另有 9 个尚未 merge / push 的 validation artifact / 前端投影提交:`df89bb6`、`9cd4cc6`、`4d42f74`、`1c3babe`、`dd48f1a`、`beacec1`、`d77ed4f`、`51ad39e`、`3848af3`。它们是本地实现证据,不是远端合并或交付证明。

## 11. 可直接复制给下一位开发者的 Prompt

```text
接手开发 /Users/eddie/Desktop/Workspace/ontology-poc-generator。

先读 docs/DEVELOPMENT_HANDOFF.md 第 0 节做对账,确认当前 checkout 和本地新增提交,再读第 3 节诊断。当前本地快照是后端 257、前端 unit 84、Sites 4、build 1973 modules;这些数字不代表 CI 或远端已经同步。

严禁修改主目录里的 README.md、docs/HANDOFF_FRONTEND_BACKEND_ALIGNMENT.md 和未跟踪的 landing-page/。先在现有 `.worktrees/pc-agent-modeling-demo` 中继续 `rico/handoff-v2` 的精确 HEAD;当前 `origin/main` 尚缺 validation 与文档收口提交,不得从它开新分支。只有这些提交落地且更新后的 `origin/main` 已包含它们后,才从该远端基线开新分支。

现状:内核、hash、四态、零副作用边界已实现;固定 validation_run.v1 含 4 cases / 8 receipts,前端只读投影为 receipt_recorded,不重算 SHA、不实现 evaluator。但 LLM 只填闭集表单(recognition.py 禁止输出对象和关系),知识单元只有一个真单元,规则只有 categorical_all_of_v1,任何 matched 的材料都产出同一份本体。

按第 6 节 Gate 1–3 顺序执行。当前先等待用户指定一份现役、可脱敏的正例材料;同时准备明确负例和现有合成对照。Gate 1 只运行开放式 prompt 并建立人工 5 条判断基线,不改代码;客户原文和原始输出只进 workspace `.local-sensitive/`。

Gate 1 有信号后,Gate 2 只实现 `extracted_object + evidence_span + closed role + code-generated stable ID`,默认只改 recognition 与对应测试,不改前端。J1 要求真实抽取兜底占比 < 50%、两份材料 binding 结构不同、同材料 5 次一致率 ≥ 80%;J2 要求现有 CQ 命中 ≥ 3 条、误触 0。最多允许一次 prompt/词表修正。

Gate 3 用同一材料比较管道 Markdown 与用户手写 5 条判断:J3 要求覆盖不低于手写且耗时不超过 3 倍,并由真实 FDE 与业务参与者共同 `go`。任一 Gate 失败即停止;Gate 1–3 前不做批量知识、threshold、DecisionDelta、review、部署或平台抽象。

每个小能力:focused test、full test、git diff --check、commit、push、PR、CI、merge。报告真实测试数、commit、PR 和尚未实现的边界。
```
