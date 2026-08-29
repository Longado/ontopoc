# 产品定义：本体建设 POC 方案生成器

## 1. 要解决的问题

工业本体 POC 的前期方案高度依赖少数顾问经验。常见结果是：

- 先列平台功能，再寻找业务问题；
- 对象、关系、规则很多，但没有落到谁在什么时点做什么决策；
- 数据条件、人工确认、系统动作和验收问题没有连成闭环；
- 不同行业方案重复从空白文档开始，修正经验无法复用；
- 演示、POC、生产和已验证效果被混写。

本产品把“如何设计一个本体 POC”本身建模为一套方法论本体，并用规则把场景输入展开成结构化方案。

## 2. 核心用户

第一优先用户：工业 AI / 数据智能 / 本体平台的售前、解决方案架构师和 FDE。

协作用户：业务专家、数据负责人、产品经理、实施负责人和客户决策者。

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
4. 每个行动必须说明责任人和系统边界；
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

## 5. 输出契约

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

## 6. MVP 成功标准

- 用户能用一个 JSON 文件描述场景；
- 生成器在本地秒级输出完整 Markdown；
- 输出围绕一个业务决策，而不是平台功能清单；
- 每个对象、规则、数据源和行动都能连接到决策闭环；
- 缺少客户数据时明确输出合成演示边界；
- 相同输入产生相同输出；
- 关键输入缺失时给出明确错误，不生成看似完整的空方案。

## 7. 非目标

- 自动完成客户需求调研；
- 自动承诺 POC 工期和商业报价；
- 自动生成生产本体并发布；
- 替代业务专家审查；
- 直接写入客户业务系统；
- 在 MVP 中建设通用 OWL 编辑器或图数据库。
