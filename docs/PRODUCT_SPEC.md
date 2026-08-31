# 产品定义：Persistent AI FDE Decision Compiler

## 0. 产品锚点

- 愿景：**Persistent AI FDE**；
- 产品机制：**AI FDE Decision Compiler**；
- 核心资产：不可变 `DecisionPack`；
- 首个垂直场景：供应链订单优先干预；
- 核心产品瞬间：`DecisionDelta`。

> 把客户的一个业务决策，编译成有来源、可验证、可审查、可发布并能持续修正的决策资产。

首个黄金主决策只有一个：“哪些订单进入优先干预队列？”“采取哪种处置动作”属于后续受控行动，不进入该黄金 `DecisionPack` 的主决策。乳品研发样例只作为跨行业 regression，不证明跨行业知识有效。

## 1. 要解决的问题

工业本体 POC 的前期方案高度依赖少数顾问经验。常见结果是：

- 先列平台功能，再寻找业务问题；
- 对象、关系、规则很多，但没有落到谁在什么时点做什么决策；
- 数据条件、人工确认、系统动作和验收问题没有连成闭环；
- 不同行业方案重复从空白文档开始，修正经验无法复用；
- 演示、POC、生产和已验证效果被混写。

本产品把 AI FDE 对业务问题的理解编译成 `DecisionPack`，再逐步形成可执行规格、验证回执和业务变化说明。当前 POC Markdown/JSON 是 `DecisionPack` 的兼容投影，固定 Demo 还会编译 draft/candidate `OntologySpec`，并记录 baseline/candidate 的合成验证回执；这些都不等于人工确认或发布。

## 2. 核心用户

MVP 唯一主要用户：把客户业务理解转成可执行模型并负责修正影响的 FDE。

验证参与者：供应链业务负责人负责判断 `DecisionDelta` 是否可理解、可纠正；售前、解决方案架构师、数据负责人、产品经理和实施负责人暂不作为 MVP 独立用户流程。

## 3. 方法论元模型

```text
Industry
  HAS_SCENE -> BusinessScene
BusinessScene
  SUPPORTS_DECISION -> Decision
Decision
  TRIGGERED_BY -> Trigger
  OWNED_BY -> Actor
  USES_OBJECT -> ObjectType
  CONSTRAINED_BY -> Constraint
  SUPPORTED_BY -> Evidence
  PRODUCES -> DecisionOutput
DecisionOutput
  MAY_CREATE -> Action
Action
  ASSIGNED_TO -> Actor
  WRITES_TO -> SystemBoundary
POC
  DEMONSTRATES -> DecisionLoop
  VERIFIED_BY -> AcceptanceQuestion
  DELIVERS -> Deliverable
```

元模型约束：

1. 一个 POC 只能有一个主决策，可有多个辅助判断；
2. 每个主决策必须有触发条件、决策者、输入对象和输出；
3. 每条规则必须绑定所需数据，缺数据时标记无法验证；
4. 处置行动不混入订单入队主决策；只有进入受控行动 Loop 后，行动才必须说明责任人和系统边界；
5. POC 验收问题必须能由演示结果回答；
6. 没有真实客户数据时，只能生成 `synthetic_demo` 路径；
7. 方案必须区分 LLM、确定性本体规则、专业模型、Agent 和人工决策的职责。

## 4. 输入契约

必填：

- `industry`：行业；
- `scene_name`：场景名称；
- `business_decision`：需要支持的一个核心决策；
- `decision_owner`：最终做决定的人；
- `trigger`：何时触发决策；
- `objects`：至少两个业务对象；
- `acceptance_questions`：至少一个 POC 验收问题。

选填：

- `participants`：参与角色；
- `relations`：可选显式关系列表；每项为 `{source, predicate, target}`，其中 `source` 和 `target` 必须引用 `objects` 中已有对象；
- `constraints`：稳定规则、限制或状态；
- `data_sources`：数据源名称、类型、状态；
- `desired_actions`：决策后可能产生的任务或动作；
- `customer_data_available`：是否已有客户可用数据；
- `notes`：其他业务背景。

未提供 `relations` 时，生成器不得按对象顺序或其他输入顺序推断关系，输出必须报告关系信息不足；只有显式输入或后续有来源的知识建议才能贡献候选关系。

## 5. 当前兼容输出契约

第一版输出 Markdown，必须包含：

1. POC 摘要；
2. 业务决策卡；
3. 决策闭环；
4. 本体对象与关系草案；
5. 规则、约束与状态；
6. 数据映射与缺口；
7. 技术职责边界；
8. 演示剧本；
9. 分阶段实施范围；
10. 验收问题与通过条件；
11. 交付物；
12. 风险和待确认事项。

## 6. 目标 MVP 成功标准

- 当前 25 项基线测试持续通过，默认 CLI 未指定知识包时保持 Loop 0 行为；
- 显式选择知识单元后，系统能输出带固定来源 snapshot、适用条件、输入绑定和 candidate 状态的知识建议；
- `DecisionPack` 能编译为引用闭合、字节稳定且保留 candidate 状态的 draft `OntologySpec`；
- 合成事实验证产生绑定内容 hash 的 `ValidationReceipt`；
- 候选版与已发布版回执可比较为 `DecisionDelta`，显示订单进入优先队列、退出优先队列、仍在优先队列或变为信息不足，并能追到规则与证据；
- 一名真实 FDE 和一名供应链业务验证参与者共同形成可记录的 `go`：保存 delta/receipt hash、纠正/批准/复用证据、理由和时间；否则 MVP 验证失败，不进入数据接入、行动和 API。

当前本地分支已完成知识建议、`DecisionPack → OntologySpec` 和固定合成验证：`validation_run.v1` 含 4 个 case、8 个带 canonical receipt hash 并绑定 pack/spec/facts hash 的 `ValidationReceipt.v1`，前端只读投影为 `receipt_recorded`。规则 `pass` 只代表合成规则匹配，review、version、publication、`DecisionDelta`、action、真实客户数据和外部写回仍未实现。

这次 validation 完成没有改变核心产品风险：输出结构仍大部分模板化，J1 / J2 / J3 与 Step A / C 仍是优先验证项；在真实 FDE 与业务验证参与者形成可记录的判断前，不得把页面、回执或测试快照写成产品价值已经通过。

## 7. 非目标

- 自动完成客户需求调研；
- 自动承诺 POC 工期和商业报价；
- 自动生成生产本体并发布；
- 替代业务专家审查；
- 直接写入客户业务系统；
- 在 MVP 中建设通用 OWL 编辑器或图数据库。
- 在 Loop 1 计算最终订单队列、风险分数或处置动作；
- 在 Loop 4 用户验证前进入数据映射、Action 或 API。
