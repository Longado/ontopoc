# Ontology POC Generator → 新 EIP 滚动路线图

最后更新：2026-08-29

## 新定位

本仓库从当前可运行的 POC 方案 CLI 出发，逐步重建一套新的 EIP：

> 把一个业务决策编译为有来源、可审查、可测试、可版本化、可运行和可修正的 `DecisionPack`。

POC Markdown 是 `DecisionPack` 的一个投影，不再是产品终点。旧 `nano-ontoprompt` 是第一方经验库和行为参考，不是代码来源、运行依赖或必须兼容的架构底座。

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

当前已有 JSON 输入、基础校验、`Proposal`、Markdown/JSON、CLI 和 7 项 unittest。它可以稳定重排输入，但当前候选关系仍由对象顺序生成，不能称为知识辅助建模或新 EIP 内核。

## NOW

### Loop 0 — 可信基线修正

**状态：planned**

**核心问题：** 当前代码会按对象数组顺序推导关系，弱化 `unavailable` 状态，并在交付物中混入尚未实现的规则、Agent、任务和版本能力。

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

## NEXT

### Loop 1 — 有来源的知识辅助 DecisionPack

**状态：entry_blocked_by_loop_0**

建立版本化 `SourceRef / KnowledgeUnit / KnowledgeSuggestion`，用确定性适用性规则贡献候选对象、关系、规则、数据需求和验收问题；自动建议始终为 candidate。第一份知识单元只覆盖一个窄场景，核心代码不得出现乳品或供应链分支。

出口：输出包含输入中没有的结构化建议，且每条建议都能追到来源、适用条件、输入绑定和版本；无匹配时返回信息不足。

### Loop 2 — 可执行本体内核

**状态：entry_blocked_by_loop_1**

把 confirmed `DecisionPack` 编译成新仓拥有的 `OntologySpec`，建立稳定 ID、显式 domain/range、属性、规则输入绑定、引用闭包和规范化 JSON。

出口：同一 pack 产生字节稳定 spec；改 label 不改变已有 ID；悬空引用、候选泄漏和未绑定规则响亮失败。

### Loop 3 — 无状态验证运行时

**状态：entry_blocked_by_loop_2**

在内存中加载 `synthetic_demo` facts，完成 T-Box 校验、首批确定性规则、`pass / fail / not_evaluable / unsupported` 四态和 checksum 绑定的 `ValidationReceipt`。

出口：黄金乳品场景产生可追到规则与事实的回执，且明确 `draft_created=false`、`published=false`、`actions_executed=false`、`external_write=false`。

### Loop 4 — 不可变版本、人工审查与发布门

**状态：entry_blocked_by_loop_3**

先创建不可变 draft snapshot 与 checksum，再让 review 绑定精确版本；随后提供 stable-ID semantic diff、stale-base 拒绝、Draft Review Package 和 confirmed-only Publication Package。

出口：退回—修订—再审—发布可重放；旧 review 不会套用到新内容；只有 confirmed 且可验证的内容能发布。

完成 Loop 4 后，仓库形成第一个可演示的新 EIP 产品闭环，而不是只能向旧 EIP 请求回执的 Studio。

## LATER

### Loop 5 — 数据映射与行级血缘

**状态：entry_blocked_by_loop_4**

先支持本地 CSV/JSON 数据版本、显式 source table/key/property/relation mapping、确定性事实展开和 row → fact → rule result → finding 正反向血缘；不接生产数据库。

### Loop 6 — 决策裁决与受控行动

**状态：entry_blocked_by_loop_5**

分离 rule result、candidate finding、human verdict 和 action task；行动必须有合同、审批、责任人、before/after、结果或失败回执。首版只生成内部任务，不写 ERP/MES/CRM。

### Loop 7 — 服务化与扩展边界

**状态：entry_blocked_by_loop_6**

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

前端、自由式 LLM 自动建模、RAG、向量库、Neo4j、生产连接器、多租户、复杂 RBAC、后台任务、RDF/OWL/SHACL、自动外部行动和行业模板市场均不在当前授权内。只有已完成 Loop 暴露明确阻塞，并形成新的可证伪计划后才进入。
