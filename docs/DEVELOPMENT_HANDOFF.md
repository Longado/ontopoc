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

内核、validation artifact 和前端只读回执投影已经接通,但**产品还没有随输入变化的输出**:LLM 只能填一张闭集表单,本体和规则来自常量模板,prompt 从未对真模型跑过。下一步不是再加一层可信度,是先做一次能证伪它的实验,再把"材料口"和"知识口"打开。validation 完成不代表产品价值通过,J1 / J2 / J3 和 Step A / C 仍是主线。

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
- **决策问题只有一个**:写死的 `order_priority_intervention` 是否对应现役客户的真实诉求,仓库里没有任何证据(没有客户材料、没有实验记录)。见 §6 Step A。
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

## 6. 下一步执行顺序(v2.2,经三镜片评审后重排)

> **8-30 三方辩论收敛(产品 / 架构 / 砍手三视角,两轮):** 唯一共识是问题 1(输出等于模板)第一;"先建人工审查"(架构)被否——材料口和知识口都锁在同一份 S-1 数据上,审查建了也没变量可审,设计可以先定、代码等 J1 出信号;"先改开发节奏"(砍手)升为并列根因,落地闸只有一条:每个 PR 描述注明服务 J1 / J2 / J3 哪条或标"非主线"。**第一步三方一致:Step A + Step C 合并做,零新代码**——真模型 + 真材料跑现有 CLI,挂上已验证的知识单元,产出 FDE 能直接读的 markdown(`generator.py` / `renderers.py` 早已把知识建议渲染进方案,导出通道现成),记入 `docs/experiments/`。顺手项:把 S-1 在 `recognition.py` 与 `knowledge.py` 的两份手抄常量合并成一个共享模块(几行,不是新抽象)。

> v2 只有一条判据("两段材料 → 本体不同 + 一处追问")。评审发现它可以被知识口单边撑过——材料口什么都没干,只要有一个宽适用的知识单元,判据照样过。所以拆成三条,各自独立可证伪。

### 判据(三条独立)

| 编号 | 测什么 | 怎么量 | 过线 |
|---|---|---|---|
| J1 材料口 | 输出是否真的来自材料 | 一次识别里,来自真实抽取(非写死兜底)的 role binding 数 / 总数;两段材料的 **binding 数量或规则命中路径**不同(label 字符串不同不算) | 兜底占比 < 50%,结构层可区分 |
| J2 知识口 | 顾问追问是否命中 | 先把 CQ(competency question)写成显式清单,每条知识单元对应一个"这份材料该不该触发"的断言;跑真实材料看命中/误触 | 命中 ≥ 3 条,误触 0 |
| J3 值不值 | 管道 vs Eddie 手写 | 同一份材料:Eddie 手写 5 条 bullet 的耗时与覆盖 vs 管道产出的耗时与覆盖 | 管道覆盖 ≥ 手写且没慢 3 倍以上 |

J3 是 11-29 结算线的直接证据。J1、J2 全过但 J3 不过,退回 Markdown 清单 + 知识单元 JSON,不做产品。

另外一条贯穿 B 的硬约束:**识别边界的重跑稳定率**。现有架构已把 LLM 隔在 `recognize_scenario` 外、候选 JSON 落定后下游全确定(hash 不受影响),但打开材料口后同一材料重跑 5 次的 binding 集合一致率要记录,< 80% 就说明 prompt 或词表要收紧。

### Step A:半天,不写代码——先看开放抽取在真材料上有没有信号

v2 的 Step A 打算用真模型跑现有 CLI。评审指出那是在验证一个代码里已写死的事实(prompt 禁止输出对象,结果必然是模板),没有信息量。改为:

1. 手写一版开放式抽取 prompt(就是 Step B 要用的那份初稿,带 reasoning、evidence_span、闭集 role 词表),**不接任何校验和转换代码**,直接对真材料跑,肉眼看输出;
2. 材料选择由 Eddie 指定(哪个客户、哪份材料,本文档不预设——评审时曾误引一份 2026 年上半年的温州客户笔记,那批客户已不在现役,已删)。跑三份:
   - 一份正例:目标客户的脱敏材料,且**先确认它的真实诉求确实是"订单优先干预队列"**——不是的话先决定加第二个 profile 还是换材料,否则真实材料永远只能当负例;
   - 一份负例:明显不属于这个决策的材料,应判 `unsupported`;判成 `matched` 说明识别边界有洞;
   - 一份对照:现有 `examples/supply_chain_exception.json` 对应的叙述。
3. 把输入 sha256、模型名、prompt 版本、原始输出存 `docs/experiments/2026-MM-DD-open-extraction.md`。不存密钥,不存客户原文。

出口:输出里有没有足够多"材料里有、模板里没有"的对象和关系,值不值得写 B 的转换代码。

### Step B:打开材料口(1–2 天,A 有信号才做)

候选 schema(reasoning 在前,逐项 evidence_span,显式 unknown 出口):

```json
{
  "reasoning": "2-4 句:材料里出现了哪些候选对象/关系,为什么判成这个 role",
  "extracted_objects": [
    {"raw_label": "供应商交期承诺", "evidence_span": "供应商承诺的交期发生变化时",
     "candidate_role_key": "supplier", "confidence": "medium"}
  ],
  "extracted_relations": [
    {"source_raw_label": "客户订单", "predicate_key": "REQUIRES", "target_raw_label": "物料",
     "evidence_span": "..."}
  ],
  "unmatched_objects": [{"raw_label": "...", "reason": "no_closed_role_fits"}]
}
```

四条护栏,全在代码层:

1. **role 闭集**:`candidate_role_key` 只能从已发布角色词表选(= 全部知识单元 `applicability.required_role_keys` 的并集,现为 customer_order / material / supplier);不在词表 → 整条 reject,不做模糊匹配。`raw_label` 只作证据展示,不参与门控。这样 `knowledge.py:788-800` 的匹配逻辑一行不用改。
2. **predicate 闭集**:来自知识单元 `relation_semantics` 的谓词表,模型不得自造谓词。evidence_span 只证明"这句话在原文里",不证明"这条关系是对的"——它是必要不充分条件,不能当唯一护栏。
3. **span 子串校验**:推广 `recognition.py:392` 那一招到每个 span;非子串整条丢弃。
4. **`semantic_key` 由代码 `stable_binding_id` 生成**,模型不编 ID。

其他:prompt 抽到 `src/ontology_poc_generator/prompts/recognition_v2.py`,`PROMPT_VERSION` 升 v2;写死的 3+1 保留为兜底但**计入 J1 的兜底占比**;材料进 prompt 前做一次去噪预筛(无关文档混入会带歪抽取,见闻歌方案写作的"数据污染陷阱");`FakeGateway` 测试覆盖:伪造 span 被拒、词表外 role 被拒、两段材料产出不同 binding。

建议提交:`feat: extract evidence-bound candidates with closed role vocabulary`

### Step C:知识口内容(1 天,可与 A 并行,不依赖 B)

机制已在(`knowledge.py` 六种贡献类型),**格式已验证**:8-30 按 `supplier_evidence_boundary_v1` 格式写了 `decoupling_point_v1.json`(解耦点未声明 → readiness_gap + acceptance_question,来源 Olhager 2003 IJPE 85(3) + Hopp & Spearman《Factory Physics》),`load_knowledge_unit` 一次通过,对 `examples/supply_chain_exception.json` 跑出 `applicable`、两条追问浮出。它应作为 Step C 的第一个 PR 进仓库。

再写 4 个,取材原则是"材料里通常不会写、资深计划员一定会问",且来源须可引用(非 synthetic):

| 触发(材料缺什么) | 类型 | 内容 |
|---|---|---|
| 只有需求预测、没有交期方差 | `data_requirement` | 安全库存里交期方差压倒需求方差,须提供供应商交期分布 |
| 多物料齐套 | `acceptance_question` | 100 个物料各 99% 到货,齐套率 37%;风险是否按齐套而非单件评估 |
| 利用率已在 85–90% 以上 | `constraint` | VUT 的 u/(1-u):任何排序算法都压不回交期;"提利用率 + 缩交期"须先让客户取舍 |
| 部门 KPI 未声明 | `readiness_gap` | 销售 / 工厂利用率 / 采购单价 / 期末库存四项 KPI 是否声明及是否对立;未声明则优先队列会被隐性冲突吸收 |

可选第 6 个:牛鞭四成因 → `acceptance_question`。便宜的加项:模板加一个 `confidence` 字段(逐事实不确定度的第一层)。已知风险:多个单元命中同一决策时,`knowledge_compiler.py` 只做同 ID 去重报 `duplicate_*_identity`,没有证据合并逻辑——单元超过 5 个前不用管。

CQ 清单与知识单元同 PR:`tests/golden/competency_questions.md`,每条对应一个断言测试。

建议提交:`feat: add decoupling point knowledge unit` → `feat: add supply chain planning knowledge units`

### Step D:规则口加 `threshold_v1`(1 天)

第一刀先拆 `knowledge.py:66-77` 的 `_DECISION_RULE_FIXED_FIELDS` / `_ALLOWED_VALUES`——不拆,任何新规则单元都进不来。现状:`ontology_spec.py:154-177` `RuleConditionSpec.allowed_values` 只支持 in 集合;`rule_runtime.py:203` `operator != "in"` 直接 `unsupported`;`knowledge_compiler.py:310` 硬编码 `operator="in"`;`knowledge.py:66-77` 锁死 S-1 规则的字段。改动约 90–120 行:knowledge.py 加 threshold_v1 payload profile(~40)、knowledge_compiler.py 加 `_compile_threshold_rule`(~30,阈值放单元素 allowed_values,`RuleConditionSpec` 不动)、rule_runtime.py 加数值比较分支(~15)。不动 `models.py`。单条件、`> >= < <=`,`not_evaluable` 语义同现有。不做通用表达式引擎。

建议提交:`feat: evaluate threshold rules`

### Step E:顺手活(各自独立 PR,随时可做)

1. **v1 Task 1–2:已在当前本地分支实现,尚未 merge / push。** Python 内核已为四笔合成事实生成真实 baseline/candidate `ValidationReceipt` 写入 artifact;前端 Validation 页展示 status / decision result / rule ID / fact & evidence refs / pack/spec/facts/receipt hash 与 lifecycle 边界,并在投影前严格校验 candidate identity/reference closure 和四个 receipt 副作用字段为 `false`,且没有在前端重写 evaluator。对应实现提交为 `df89bb6^..3848af3`。
2. **Golden set + eval**:`tests/golden/recognition_cases.jsonl` 15–20 条(matched / insufficient / unsupported 各 5+);CI 默认用 `FakeGateway` 跑 Layer A(< 10 s,阻断);真模型 judge 只在有 API key 时跑,结果落 `docs/experiments/`,不阻断合并。识别结果信封已带 provider / model / prompt_version,够用;`--model` 改为必填并在实验记录里钉死版本。
3. **卫生 PR**:CI 加前端 job;`App.jsx` 等过 prettier;删 14 条已合并本地分支。
4. **文档收口**:当前已先修正 validation 生命周期事实;A–D 的产品方向变化仍应在各自完成后单独更新。

### 明确不做(J1–J3 达成前)

DecisionDelta、review / version / publication、数据库、账号、公网部署、通用 Agent 框架、RAG、向量库、图数据库、手机端、跨提及实体解析(那是 Altana 砸 3 亿美元的地方,不是 POC 的活)。

### 未纳入计划但必须记一笔:EIP 对接

原构想的 Loop 5(把 OntologySpec 送进 EIP 拿回执)不在 v2 计划里。原因是双向都没打通:EIP 侧 versioning 模块建了表但没挂 router;OntoPoc 侧也没有 EIP 期望输入的契约。这仍是全部构想里最值钱的一针,J1–J3 达成后第一件要重新评估的事。

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
- Step B 打开材料口后,新增的硬规则:**没有原文 span 的候选不得进入 ScenarioParameters**。

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

按第 6 节顺序做:A 用真模型跑一次脱敏真实材料并记录;B 让模型提取带 evidence_span 的候选对象/关系,代码校验 span 是原文子串;C 按 supplier_evidence_boundary_v1 格式写 3–5 个供应链顾问判断知识单元;D 加 threshold_v1 规则。ValidationReceipt 接入已在当前本地分支完成;CI 加前端、清分支仍未做。

四个门槛必须分别验收:
J1 材料口:真实抽取的 role binding 兜底占比 < 50%,且两段材料的 binding 数量或规则命中路径不同(label 字符串不同不算)。
J2 知识口:显式 CQ 断言中命中 ≥ 3 条、误触 0。
J3 值不值:同一材料与 Eddie 手写 5 条 bullet 对照,管道覆盖不低于手写且耗时不超过 3 倍;J1/J2 通过但 J3 不过就退回 Markdown 清单 + 知识单元 JSON,不做产品。
稳定重跑:同一材料跑 5 次,binding 集合一致率必须 ≥ 80%;低于门槛先收紧 prompt 或词表。上述门槛达成前不做 DecisionDelta、review、部署。

每个小能力:focused test、full test、git diff --check、commit、push、PR、CI、merge。报告真实测试数、commit、PR 和尚未实现的边界。
```
