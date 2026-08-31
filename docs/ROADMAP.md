# Persistent AI FDE / Decision Compiler 滚动路线图

最后更新：2026-08-31

## 产品锚点

本仓库从当前可运行的 POC 方案 CLI 出发，逐步构建一条 **Persistent AI FDE** 生产线：

> 把客户的一个业务决策，编译成有来源、可验证、可审查、可发布并能持续修正的决策资产。

产品机制是 **AI FDE Decision Compiler**，核心资产是不可变 `DecisionPack`，首个垂直场景是供应链订单决策变更，首个必须验证的产品瞬间是 **DecisionDelta**。

黄金主决策严格收敛为：

> 哪些订单进入优先干预队列？

“采取哪种处置动作”不是该 `DecisionPack` 的主决策；它属于 Loop 6 的受控行动范围。乳品研发样例只保留为跨行业 regression，用来防止核心出现行业特判，不证明跨行业知识有效。

当前默认 CLI 的 Markdown/JSON 是 `Proposal` 渲染；只有显式传入 `--decision-pack-output` 才写出 canonical `DecisionPack`。两者都不是产品终点。旧 `nano-ontoprompt` 是第一方经验库和行为参考，不是代码来源、运行依赖或必须兼容的架构底座。

详细执行计划见 [渐进式 EIP 重建总计划](superpowers/plans/2026-08-29-incremental-eip-reconstruction.md)。

## 开发闭环

```text
选择一个真实决策
-> 写出本轮可证伪假设
-> 先写失败测试
-> 实现最小纵向能力
-> 跑黄金合成场景
-> 对照旧 EIP 或一个外部机制
-> 记录发现与差异
-> 小步 commit / push
-> 决定进入、重做或停止下一 Loop
```

维护规则：

1. 同一时间只有一个 Loop 为 `in_progress`；
2. 每个 commit 只回答一个行为问题并保持全量测试通过；
3. 不复制旧 EIP 的模块、ORM、迁移、路由、页面或数据库；
4. 借鉴旧 EIP 时必须记录“问题、机制、本仓测试、不复制内容”；
5. 每个 Loop 都要让同一个黄金场景多走一步，不能只新增孤立类型；
6. 新发现先进入 `DISCOVERY_LOG.md`，只有影响当前出口门时才改变当前范围；
7. 文档、fixture 或类存在不等于能力已实现；
8. 合成演示、POC、生产运行和客户效果始终分开表达。

## 已实现基线

### Stage 0 — 产品与方法论草案

**状态：complete_with_unvalidated_product_hypotheses**

已有产品定义、方法论元模型、输入输出契约、乳品研发与供应链异常两个合成场景。它们证明问题和模型假设已被写出，不证明真实用户价值或跨行业有效。

### Stage 1 — 确定性 Proposal CLI

**状态：complete_as_template_baseline**

当前已有 JSON 输入、严格基础校验、`Proposal`、Markdown/JSON、CLI 和 25 项 unittest。它只投影已声明的显式关系，未提供关系时返回信息不足；仍不能称为知识辅助建模或新 EIP 内核。

## 已完成 Loop

### Loop 0 — 可信基线修正

**状态：complete**

**核心问题：** Loop 0 修正前的代码会按对象数组顺序推导关系，弱化 `unavailable` 状态，并在交付物中混入尚未实现的规则、Agent、任务和版本能力。

**最小范围：**

- 严格 JSON boolean 与数据源状态；
- 不可变数据源值对象；
- 删除相邻对象关系推导；
- 无显式或知识来源时输出信息不足；
- `available / to_confirm / unavailable` 原样传播；
- 当前能力与计划能力分开渲染。

**出口门：**

- 对象列表重排不改变语义关系；
- `unavailable` 不会显示成“待确认”；
- 无来源时不补造关系；
- 输出不声称已经运行规则、Agent、行动、版本或回执；
- 双样例和全量测试通过。

**实际证据：**

- 代码基线由 `0a709f1`、`2b8659f`、`0fc2538`、`43ec41e` 四个小提交建立：分别保留数据源状态、要求显式关系语义、将未实现能力标为计划项、使关系风险表述与显式输入一致；
- 2026-08-29 运行 `PYTHONPATH=src python -m unittest discover -s tests -v`，结果为 **25 tests, OK**；
- 通过 CLI 将 `examples/dairy_rnd.json` 与 `examples/supply_chain_exception.json` 生成到临时目录。两份 Markdown 都保留 `synthetic_demo` 边界；未提供显式关系时明确写出“关系信息不足”；供应链样例的“物流节点状态”仍显示 `unavailable` / “数据源不可用”；规则、Agent、任务和版本写为 POC 计划或待验证项，且未出现把回执写成已运行结果的表述。

**仍未解决的限制：**

- 当前只重排并投影已声明输入；没有知识单元、来源匹配或输入外建议，知识增益仍为零；
- 双样例只是 smoke / regression 证据，不能证明跨行业有效，也不能证明真实客户数据质量、业务效果或运行能力；
- 在 Loop 0 出口时，规则求值、Agent 编排、任务创建、版本记录、回执和外部写入均未实现；后续 Loop 3 已在当前本地分支补齐窄范围合成验证与回执，其他项仍未实现。

### Loop 1 — 有来源的供应链知识辅助 DecisionPack

**状态：complete**

详细实施与出口证据见 [Loop 1：供应链证据语义知识单元](superpowers/plans/2026-08-29-loop1-sourced-supply-chain-knowledge.md)。代码按小提交建立来源契约、固定知识单元、通用匹配、payload profile 校验、不可变 `DecisionPack`、opt-in CLI 投影和投影加固：`f49087e`、`341a8bd`、`e670a9a`、`6ad3eb9`、`d339885`、`d40e9a2`、`2744ccb`。Task 4 与 Task 5 的 spec review 和 quality review 均为 APPROVED。

建立稳定身份的 `SourceRef / KnowledgeUnit / KnowledgeSuggestion / KnowledgeOutcome` 和不可变 `DecisionPack`，用知识包内声明的确定性匹配规则贡献 candidate 建议。第一份知识单元只区分 `QUALIFIED_TO_SUPPLY` 与 `HAS_SUPPLIED` 的证据语义；核心 Python 不得出现供应链分支。

**实际证据：**

- 2026-08-29 运行全量 unittest，结果为 **107 tests, OK**；默认不加载知识单元的 JSON/Markdown 与 Loop 0 golden 保持一致，pack canonical hash 可重复；
- 供应链样例显式加载知识单元后仍为 `synthetic_demo`，匹配为 `applicable`，输出 7 条 candidate 建议和 3 个 source snapshot；
- 乳品研发样例加载同一单元后为 `not_applicable`，输出 0 条建议和 0 个来源；缺少订单—物料桥接时为 `insufficient_information` 且无建议；
- 入队政策为 pending 时保留 7 条建议，其中包含结构化 readiness gap；政策为 ready 时输出 6 条建议且不再包含该 gap；
- 所有建议都能追到固定 snapshot、知识单元版本/hash、适用条件和稳定语义绑定；Markdown 来源字段经过结构防注入处理。

**仍未解决的限制：**

- 客户入队政策仍是 readiness gap；当前只有 synthetic candidate rule，不计算风险分数、不输出最终队列、不提出处置动作；
- 在 Loop 1 出口时，尚未实现事实校验、`ValidationReceipt`、review、version、publication 或外部写入；当前本地分支已补齐前两项的固定 `synthetic_demo` 路径，后五项仍未实现；
- `synthetic_demo` 和跨行业 regression 不能证明客户适用性、真实数据质量或生产效果。

## NOW

### Loop 2 — 可执行本体内核

**状态：complete**

详细实施计划见 [Loop 2：Draft OntologySpec](superpowers/plans/2026-08-29-loop2-draft-ontology-spec.md)。集成点 `fbc0f33` 的全量测试 **198/198** 通过；黄金 CLI 以供应链 source unit 和 synthetic policy 写出 canonical spec，hash 为 `31b00f3432281459d71615fa7ba4733a522332987d26632aeeb50737a7ecfed3`。输出包含 3 个 entity、3 个 relation（其中 2 个来自 knowledge suggestion）、2 个 symbolic property 和 1 条 `categorical_all_of_v1` candidate rule；引用闭包为 `is_closed=true`，检查 36 个引用，产生 5 个 `requires_review` suggestion-bound issue 和 0 个 blocking issue。

出口已满足：同一 pack 产生 canonical draft/candidate `OntologySpec`，并保留 `synthetic_demo` 边界；稳定 identity、引用闭包、状态保留和规则输入绑定均由测试覆盖。

Loop 2 完成不等于 publication 或 production；Loop 2 出口当时没有 receipt、version、review、publication、action 或 writeback。当前本地分支只补齐了固定合成 receipt，其他边界未变。

## 当前本地验证状态

### Loop 3 — 无状态验证运行时

**状态：complete_on_current_local_branch（尚未 merge / push）**

当前本地分支已实现 `categorical_all_of_v1` 的 `pass / fail / not_evaluable / unsupported` 四态运行时，并将固定 4 个 `synthetic_demo` case 分别对 baseline/candidate 求值，记录为 `validation_run.v1` 中 8 个真实 `validation_receipt.v1`。每个回执带 canonical receipt hash，并绑定 pack/spec/facts 内容 hash、rule、fact refs 和 evidence refs；四个副作用字段均固定为 `false`。

固定 artifact 以顶层 baseline pack/spec 为唯一权威，validation authority 只保存 JSON refs + hash；candidate 具有独立 pack/spec。PC Validation 页面以 `receipt_recorded` 投影 4 cases / 8 receipts、证据、hash 与边界，不重算 SHA、不实现 evaluator；结构、引用或绑定不一致时 fail closed。

这里的 `validation=completed` / `receipt_recorded` 只表示固定合成验证已经求值并记录；单条规则 `pass` 只表示输入满足候选规则。人工 review、version、publication、action 和外部 writeback 仍为 `not_started`，所有 write/action 标志仍为 `false`。本地提交不代表已经合并、交付或具备生产能力。

## NEXT

### Loop 4 — 不可变版本、人工审查与发布门

**状态：not_started**

先把首份 candidate/draft receipt 审查、确认并发布为 baseline；再对 revised candidate pack/spec/receipt 建立不可变 version/base，让 review 绑定精确内容 hash，并同时提供结构 `semantic diff` 和业务 `DecisionDelta`。`DecisionDelta` 比较 published baseline 与 candidate receipt，报告订单进入优先队列、退出优先队列、仍在优先队列或变为信息不足，并逐项附上规则与证据依据。

出口：退回—修订—再审—发布可重放；旧 review 不会套用到新内容；只有 confirmed 且可验证的内容能发布；一名真实 FDE 和一名供应链业务验证参与者共同理解并纠正、批准或复用至少一份 `DecisionDelta`。

Loop 4 是产品验证闸，不是自动通往平台建设的里程碑。当前虽已完成窄范围合成 validation，但输出结构仍大部分模板化；J1 / J2 / J3 与 Step A / C 仍优先于 review/publication 扩张。若真实 FDE 和供应链业务验证参与者不能共同纠正、批准或复用 `DecisionDelta`，停止扩张并重新锚定，不得进入 Loop 5–7。

进入门必须由可检查的产品验证记录证明：保存被评估的 delta/receipt hash、参与者角色、实际纠正/批准/复用证据、`go / no_go`、理由和时间；只有一名真实 FDE 与一名供应链业务验证参与者共同形成 `go`，才解除 Loop 5–7 的阻塞。

## LATER

### Loop 5 — 数据映射与行级血缘

**状态：entry_blocked_by_loop_4_user_validation**

先支持本地 CSV/JSON 数据版本、显式 source table/key/property/relation mapping、确定性事实展开和 row → fact → rule result → finding 正反向血缘；不接生产数据库。

### Loop 6 — 决策裁决与受控行动

**状态：entry_blocked_by_loop_4_user_validation_and_loop_5**

分离 rule result、candidate finding、human verdict 和 action task；此时才处理“采取哪种内部处置动作”。行动必须有合同、审批、责任人、before/after、结果或失败回执。首版只生成内部任务，不写 ERP/MES/CRM。

### Loop 7 — 服务化与扩展边界

**状态：entry_blocked_by_loop_4_user_validation_and_loop_6**

把已验证 use case 提炼为 application service 和 repository port，再增加 capability-derived API。CLI 与 API 必须共享领域内核；没有测试覆盖的能力不得进入 capability manifest。

## 参考路线

| 参考 | 借鉴机制 | 进入点 | 不复制内容 |
|---|---|---|---|
| 旧 EIP / nano-ontoprompt | OntologySpec、四态规则、T-Box、lineage、verdict、version、action approval 的行为纪律 | 每轮最多一个机制 | ORM、迁移、router、数据库、页面、历史兼容层 |
| WebProtégé | 修订、讨论和审查关口 | Loop 4 后复审 | 完整协作 UI |
| VocBench 3 | 受管词表和角色治理 | Loop 1/4 按需 | 词表平台整体 |
| TerminusDB | commit、diff、历史查询 | Loop 4 | 存储引擎替换 |
| Ontop | 映射契约和源端查询思想 | Loop 5 | 当前底座迁移 |
| Jena/RDF4J | RDF、SPARQL、SHACL 标准能力 | Loop 7 后另立计划 | 过早标准栈扩张 |
| TypeDB | 关系角色和继承语义 | 本地模型表达不足时 | 数据底座迁移 |

## 提交节奏

计划重锚本身作为独立文档 commit。进入代码后，每个 Loop 通常拆为：

1. `test:` 写清行为契约；
2. `feat:` 或 `fix:` 最小实现；
3. `test:` 黄金 fixture 与回归；
4. `docs:` 记录验证证据、被推翻假设和下一进入门。

不设行数指标，但禁止一次 commit 同时引入完整建模、验证、版本、数据库和 API。root agent 负责最终集成、测试和 commit；子 Agent 按文件或职责独立工作，不直接扩大当前 Loop。

## 暂缓

除当前只读 PC Demo 外的前端扩展、自由式 LLM 自动建模、RAG、向量库、Neo4j、生产连接器、多租户、复杂 RBAC、后台任务、RDF/OWL/SHACL、自动外部行动和行业模板市场均不在当前授权内。只有已完成 Loop 暴露明确阻塞，并形成新的可证伪计划后才进入。
