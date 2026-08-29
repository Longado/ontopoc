# PRD：渐进式新 EIP

**产品代号：** Ontology EIP Studio
**仓库：** `ontology-poc-generator`  
**版本：** v0.1  
**状态：** Re-anchored product direction; detailed requirements under review
**日期：** 2026-08-29

> 当前实施顺序以 [渐进式 EIP 重建总计划](superpowers/plans/2026-08-29-incremental-eip-reconstruction.md) 和 [路线图](ROADMAP.md) 为准。本文后半部原有的 Studio/EIP 适配型功能清单保留为候选需求，不再代表已承诺顺序。

## 1. 执行摘要

Ontology EIP Studio 从当前的确定性 POC 方案 CLI 出发，逐步长成一套新的 EIP。用户围绕一个业务决策形成 `DecisionPack`，系统随后逐步提供有来源的建模建议、本体规格编译、确定性验证、人工裁决、版本发布、数据血缘和受控行动。

它借鉴旧 EIP 已经验证过的产品纪律，但重新拥有自己的领域契约和运行内核。旧 `nano-ontoprompt` 仅作为只读行为参考，不作为源码、数据库、运行依赖或产品终局。

## 2. 产品问题

### 2.1 用户问题

当前工业本体 POC 方案普遍存在五个问题：

1. 从平台功能出发，而不是从一个具体业务决策出发；
2. 业务对象、关系、规则、数据和行动分散在不同文档中，彼此不能校验；
3. PRD、技术方案、数据清单和验收表由不同人重复编写，口径容易漂移；
4. 顾问经验停留在个人文档中，无法沉淀为可复用方法；
5. 合成演示、POC 能力、生产能力和客户效果经常被写成同一种确定性。

### 2.2 根因

项目材料没有共享的结构化事实源。每份文档都在重新解释：

```text
业务问题是什么
-> 谁在什么时点做什么决策
-> 决策依赖哪些对象、关系、规则和数据
-> 系统、模型、Agent 和人分别做什么
-> 如何演示和验收
```

只做模板生成无法解决这个问题。需要先把“本体项目方案”本身建模。

### 2.3 不解决的代价

- 售前需要反复从空白文档开始；
- 技术和业务对同一术语理解不同；
- POC 范围在讨论中持续扩大；
- 数据缺口到实施阶段才暴露；
- 演示看起来完整，却无法回答客户的验收问题；
- 项目修正不能沉淀为下一次可复用资产。

## 3. 产品定位

### 3.1 一句话定位

把一个工业业务决策编译成可审查、可测试、可版本化、可运行和可修正的决策本体包。

### 3.2 产品不是什么

- 不是通用文案写作工具；
- 不是完整 OWL 编辑器；
- 不是旧 EIP 代码和数据库的复制品；
- 不是自动替代业务专家的“AI 顾问”；
- 不是自动承诺工期、报价或客户效果的投标工具；
- 不是未经审查就发布生产本体的生成器。

### 3.3 从生成器到新 EIP

```text
当前 Proposal CLI
-> 有来源的 DecisionPack
-> 新仓自有 OntologySpec
-> 无状态验证运行时
-> 版本、审查与发布
-> 数据映射与血缘
-> 决策裁决与受控行动
-> 服务化 EIP
```

设计期和运行期仍保持领域边界，但由本仓库逐步实现同一套可追踪契约。旧 EIP 后续最多作为兼容适配目标和差异测试参考，不能替代新仓自己的验证内核。

## 4. 目标用户与核心任务

### 4.1 主要用户

| 用户 | 当前任务 | 主要痛点 | Studio 提供的价值 |
|---|---|---|---|
| 售前/解决方案顾问 | 快速形成客户化 POC 方案 | 方案依赖个人经验，容易大而全 | 用决策闭环约束范围，分钟级形成初稿 |
| FDE/架构师 | 把方案转成可实施结构 | PRD、数据、本体和验收口径不一致 | 从同一蓝图生成全部项目材料 |
| 业务专家 | 纠正对象、规则和决策逻辑 | 技术文档难审，修改无法定位影响 | 按决策卡和差异项逐条确认 |
| 数据负责人 | 判断数据是否支持 POC | 数据需求描述抽象、缺口暴露晚 | 得到对象—字段—规则—验收问题映射 |
| 产品/项目经理 | 控制范围和验收 | POC 完成标准模糊 | 得到有来源的 PRD、范围和验收矩阵 |

### 4.2 Jobs to Be Done

当我收到一个工业客户场景时，我希望快速把模糊需求收敛成一个可验证的决策闭环，从而在和客户讨论前得到一份结构一致、边界诚实、可以被逐项修正的 POC 与实施方案。

当业务专家纠正对象、关系或规则时，我希望所有关联材料同步变化，从而避免 PRD、数据清单、演示脚本和验收标准互相矛盾。

## 5. 产品原则

1. **一个方案，一个主决策。** 辅助判断必须服务主决策；
2. **DecisionPack 先于文档。** `ProjectBlueprint` 是其设计部分，所有输出来自同一结构化事实源；
3. **建议不是确认。** 自动生成的对象、关系、规则保持 candidate 状态；
4. **事实有来源。** 从材料抽取的内容保留 source reference；
5. **信息不足可见。** 缺数据时标记 `not_evaluable`，不补成确定结论；
6. **设计与运行分层但契约同源。** 新仓分别实现编译、验证和治理，不能用 renderer 代替运行证据；
7. **人工审查是产品步骤。** AI 不能绕过业务确认和发布关口；
8. **同一输入稳定输出。** 确定性内核不嵌入当前时间或随机内容；
9. **演示边界诚实。** 无客户数据时强制使用 `synthetic_demo`；
10. **成功看修正闭环。** 不以对象数、页面数或生成字数作为主要价值指标。

## 6. 统一项目蓝图

### 6.1 蓝图是唯一事实源

```text
ScenarioInput
  -> ProjectBlueprint
       ├── POCProposal
       ├── ProductRequirementsDocument
       ├── OntologySpecification
       ├── DataRequirementMatrix
       ├── RuleTestPlan
       ├── DemoStoryboard
       └── AcceptanceMatrix
```

### 6.2 ProjectBlueprint 核心对象

| 对象 | 含义 | 来自 EIP 的启发 |
|---|---|---|
| `BusinessScene` | 业务背景和边界 | 本体必须服务一个真实决策场景 |
| `Decision` | 主决策、触发、owner、输出 | 决策队列和人工裁决 |
| `Actor` | 决策者、参与者、责任人 | 审批人与行动负责人 |
| `ObjectType` | 业务对象及标识 | T-Box entity class |
| `RelationType` | 对象之间的业务语义 | domain/range 和命名关系 |
| `Constraint` | 规则、限制和状态 | 四态规则求值 |
| `DataSource` | 来源、状态、授权和字段映射 | Dataset、mapping、lineage |
| `Evidence` | 支持对象和判断的证据 | 行级血缘和来源强度 |
| `Finding` | 规则产生的候选结论 | EIP finding/verdict 分层 |
| `Action` | 决策后的任务或内部动作 | 参数、审批、before/after、回执 |
| `AcceptanceQuestion` | POC 要回答的问题 | 验收门而不是功能清单 |
| `Deliverable` | 方案、规格、数据和测试材料 | 同一蓝图的多种投影 |

### 6.3 核心关系

```text
BusinessScene SUPPORTS Decision
Decision TRIGGERED_BY Trigger
Decision OWNED_BY Actor
Decision USES ObjectType
ObjectType CONNECTED_BY RelationType
Decision CONSTRAINED_BY Constraint
Constraint REQUIRES DataSource
Evidence SUPPORTS Finding
Finding REVIEWED_BY Actor
Decision PRODUCES Action
Action ASSIGNED_TO Actor
POC VERIFIED_BY AcceptanceQuestion
ProjectBlueprint GENERATES Deliverable
```

### 6.4 状态语义

蓝图元素使用：

```text
candidate     自动建议或尚未业务确认
confirmed     已被相应责任人确认
rejected      已否决并保留理由
insufficient  信息不足，不能进入正式结论
```

规则验证使用：

```text
pass | fail | not_evaluable | unsupported
```

两组状态不能混用：前者表示人的治理状态，后者表示机器求值状态。

## 7. 工具组合

### 7.1 P0：当前产品主线

#### A. Scene Intake / 决策场景定义器

将行业、场景、主决策、触发、角色、对象、约束、数据和验收问题收敛成合法输入。

#### B. POC Proposal Generator / POC 方案生成器

当前已具备首版：生成决策卡、本体草案、数据缺口、演示脚本、阶段范围、交付物和风险。

#### C. PRD Generator / 本体项目 PRD 生成器

从蓝图生成问题、用户、范围、用户故事、功能需求、非功能需求、验收标准和风险。PRD 不重新推导方法论，只读取蓝图。

#### D. Acceptance Matrix Generator / 验收矩阵生成器

把每个验收问题展开为场景、输入、操作、预期结果、证据和责任人，防止“演示完成”等同“POC 验收”。

### 7.2 P1：实施准备工具

#### E. Ontology Blueprint Builder

可视化编辑对象、关系、规则、状态、数据和行动，运行结构验证，导出 EIP-compatible spec。

#### F. Data Readiness Checker

生成源系统、表、字段、自然键、更新频率、权限、样例和数据缺口清单；把规则所需输入与数据字段对应。

#### G. Rule Test Case Generator

针对每条规则生成 pass、fail、not_evaluable、unsupported 测试样例和期望结果。

#### H. Demo Storyboard Generator

生成“触发—证据—候选结论—人工修正—任务”的演示剧本，不以页面游览代替业务故事。

### 7.3 P2：协作与运营工具

#### I. Blueprint Review Workbench

提供版本、diff、逐项评论、confirmed/rejected/insufficient 审查和发布历史。

#### J. Domain Pack Builder

把经过验证的对象模式、关系模式、规则、数据需求、验收样例和适用边界沉淀成行业包。

#### K. 新 EIP Validation Runtime

把 confirmed `DecisionPack` 编译为新仓 `OntologySpec`，先在内存合成数据上完成 T-Box、规则四态和校验回执，再逐步加入版本、映射、血缘与治理。旧 EIP 适配器不是运行内核的前置条件。

## 8. MVP 范围

### 8.1 当前已有

- JSON 场景输入；
- 必填字段和最小对象数量校验；
- 决策中心型 POC 方案；
- Markdown/JSON 输出；
- `synthetic_demo` 和数据缺口；
- 显式关系语义与关系信息不足提示；
- 乳品研发与供应链异常两个样例；
- CLI；
- 25 项自动化测试。

### 8.2 下一 MVP 增量

1. 引入独立 `ProjectBlueprint`，把当前 Proposal 从核心模型降为输出投影；
2. 增加 PRD renderer；
3. 增加验收矩阵 renderer；
4. 增加结构一致性检查；
5. 增加 Web 表单和蓝图预览；
6. 保持 CLI 和已有 JSON 输入兼容。

### 8.3 MVP 明确不包含

- 用户登录和多人实时协作；
- LLM 文档抽取；
- Office 文档排版；
- EIP 在线依赖；
- 外部系统连接和写回；
- 通用 OWL/RDF 编辑；
- 商业报价与项目工期自动估算。

## 9. 用户流程

```text
新建项目
-> 选择从空白场景或行业样例开始
-> 填写一个主决策及触发条件
-> 补充角色、对象、约束、数据源和验收问题
-> 系统生成 ProjectBlueprint
-> 查看缺失项、冲突和 candidate 建议
-> 人工确认或退回具体元素
-> 预览 POC / PRD / 数据 / 验收等输出
-> 导出 Markdown / JSON
-> 后续可导出 EIP spec 进入验证
```

## 10. 功能需求

### 10.1 P0 需求

| ID | 需求 | 验收标准 |
|---|---|---|
| FR-001 | 创建项目场景 | 保存行业、场景、主决策、owner、trigger 和验收问题 |
| FR-002 | 校验主决策闭环 | 缺 owner、trigger、对象或验收问题时禁止形成 confirmed 蓝图 |
| FR-003 | 生成 ProjectBlueprint | 相同输入生成相同结构化蓝图 |
| FR-004 | 管理 candidate 状态 | 自动建议默认 candidate，不能显示成已确认 |
| FR-005 | 显示数据缺口 | 未确认或不可用数据源进入明确缺口清单 |
| FR-006 | 生成 POC 方案 | 输出十二个必要章节并保持 synthetic demo 边界 |
| FR-007 | 生成 PRD | 从同一蓝图输出范围、用户故事、需求、验收和风险 |
| FR-008 | 生成验收矩阵 | 每个验收问题关联输入、步骤、预期、证据和责任人 |
| FR-009 | 导出 Markdown/JSON | 输出可重复、可 diff，不嵌入随机值或当前时间 |
| FR-010 | 保持现有 CLI 兼容 | 当前两个示例命令继续成功 |

### 10.2 P1 需求

| ID | 需求 | 验收标准 |
|---|---|---|
| FR-101 | 蓝图可视化编辑 | 用户可编辑对象、关系、规则和状态并立即重新验证 |
| FR-102 | 数据需求矩阵 | 规则所需输入可追到数据源、表、字段和状态 |
| FR-103 | 规则测试计划 | 每条规则至少生成 pass/fail/not_evaluable 样例 |
| FR-104 | 行业样例与模板 | 模板建议带适用条件和版本，不修改生成核心 |
| FR-105 | EIP 规格导出 | confirmed 元素可转换为 EIP spec，candidate 不进入发布规格 |

### 10.3 P2 需求

| ID | 需求 | 验收标准 |
|---|---|---|
| FR-201 | 版本和结构 diff | 可比较两版蓝图的对象、关系、规则、数据和验收变化 |
| FR-202 | 人工审查 | 审查记录追加保存并包含 actor、verdict、reason 和 time |
| FR-203 | 来源引用 | AI 抽取元素可导航到输入材料位置 |
| FR-204 | EIP 验证回执 | 可关联 EIP 版本、validation report 和发布状态 |

## 11. 用户故事

### US-001：快速形成可讨论 POC

作为售前顾问，我希望输入客户的一个核心决策和已有材料后生成 POC 初稿，从而在首次方案讨论前获得结构完整但边界诚实的材料。

验收：方案包含主决策、对象关系、数据缺口、演示剧本和验收问题；无客户数据时显示 `synthetic_demo`。

### US-002：生成一致的 PRD

作为产品经理，我希望 PRD 与 POC 来自同一蓝图，从而避免范围、术语和验收标准互相冲突。

验收：修改主决策或验收问题后，POC 和 PRD 同步变化；未经确认的候选关系在两份输出中状态一致。

### US-003：提前发现数据不可用

作为数据负责人，我希望看到每条规则需要的数据及状态，从而在 POC 启动前确认哪些结论能算、哪些不能算。

验收：缺失数据对应的规则显示 `not_evaluable`，而不是 pass 或 fail。

### US-004：业务专家逐项纠正

作为业务专家，我希望按决策、对象、关系和规则逐项确认或否决，从而让我的修正成为蓝图事实，而不是散落在会议纪要里。

验收：每次审查保留 verdict、reason 和关联元素；新输出使用最新 confirmed 投影。

### US-005：进入 EIP 验证

作为解决方案架构师，我希望把确认后的蓝图导出成 EIP 规格，从而用真实数据验证 T-Box、规则、血缘和决策闭环。

验收：只有 confirmed 元素进入导出；EIP 返回的版本和验证报告可以关联回蓝图版本。

## 12. 非功能需求

| 维度 | MVP 要求 |
|---|---|
| 确定性 | 相同规范化输入必须产生字节稳定的 JSON；Markdown 语义和顺序稳定 |
| 性能 | 不使用 LLM 时，两个现有样例在普通本地环境中秒级完成 |
| 可解释性 | 每个输出章节能定位到蓝图元素，不能只返回整段不可追踪文本 |
| 可移植性 | 核心继续使用 Python 标准库；Web/API 是适配层 |
| 数据安全 | 本地模式默认不上传输入材料；未来 LLM 连接需显式配置 |
| 兼容性 | Python 3.11+；现有 CLI 和 JSON 示例作为回归契约 |
| 可测试性 | 生成、校验和渲染保持纯函数；外部模型和 EIP 使用端口适配器 |
| 诚实性 | suggestion、confirmed、synthetic、verified、published 使用不同状态和措辞 |

## 13. 信息架构与关键页面

### 13.1 项目首页

- 最近项目；
- 当前阶段与缺口；
- 从空白或行业样例创建；
- 不显示未经真实使用验证的虚构 KPI。

### 13.2 场景与决策卡

- 行业、场景、主决策、trigger、owner；
- 参与角色；
- 决策输出和后续行动；
- 主决策完整性提示。

### 13.3 蓝图工作台

- 对象；
- 关系；
- 规则与状态；
- 数据源和映射；
- 验收问题；
- candidate/confirmed/rejected/insufficient 状态。

### 13.4 输出中心

- POC 方案；
- PRD；
- 数据需求矩阵；
- 本体规格；
- 规则测试计划；
- 演示剧本；
- 验收矩阵。

### 13.5 审查与版本

MVP 后提供结构 diff、评论、审查时间线和导出历史。

## 14. 技术架构

```text
CLI / Web Form / Document Extractor
                |
                v
        ScenarioParameters
                |
                v
       Blueprint Compiler
     validate -> infer -> normalize
                |
                v
         ProjectBlueprint
        /       |        \
       v        v         v
 POC renderer  PRD renderer  Acceptance renderer
       |        |         |
       +--------+---------+
                |
       Markdown / JSON / EIP spec
```

模块边界：

```text
models.py          输入与蓝图值对象
methodology.py     元模型、约束和推导规则
compiler.py        Scenario -> ProjectBlueprint
validators.py      结构、状态和完整性检查
renderers/         各类交付物投影
adapters/          CLI、Web、LLM、EIP
```

关键约束：renderers 不做业务推导；adapter 不复制校验；LLM 不直接创建 confirmed 元素。

## 15. EIP 能力复用映射

| EIP 能力 | Studio 吸收的语义 | Studio MVP 实现 | 后续连接方式 |
|---|---|---|---|
| `modeling/spec` | 规格是概念层和实例层共同来源 | ProjectBlueprint 单一事实源 | 导出 EIP spec |
| T-Box | 类、domain/range、基数和违规 | 蓝图结构校验 | EIP 独立验证回执 |
| `rule_eval` | 四态求值 | 规则测试计划与数据缺口 | 真实数据运行 |
| lineage | 每个结论有来源 | source reference / evidence | 关联行级血缘 |
| verdict | 人的确认不能被机器结果替代 | candidate/confirmed/rejected/insufficient | 追加式审查同步 |
| versioning | 草稿、diff、stale base、发布 | 蓝图版本放在协作阶段 | 关联 EIP spec version |
| action approval | 行动有参数、审批和回执 | 方案中声明 action contract | EIP 内部行动执行 |
| checkup | 已定义不等于在跑 | 输出数据与验证缺口 | EIP 运行体检 |

不直接复用：EIP 数据库表、React 页面、Neo4j 运行环境、客户数据和 demo 结论。

## 16. 成功指标与验证方式

MVP 使用可直接验证的产品指标，不设未经用户研究支持的商业数字：

| 指标 | MVP 目标 | 验证方式 |
|---|---|---|
| 结构完整性 | 100% 输出通过蓝图必填约束 | 自动化测试 |
| 双样例回归兼容性 | 乳品研发、供应链异常两个样例均通过同一生成入口 | example contract test；不证明跨行业知识有效 |
| 输出一致性 | 相同输入 JSON 输出稳定 | deterministic test |
| 状态诚实性 | 无客户数据必定显示 synthetic_demo | 单元测试与样例检查 |
| 数据缺口可见 | 非 available 数据源全部进入缺口 | 单元测试 |
| 跨文档一致性 | POC、PRD、验收矩阵读取同一蓝图 | 修改传播测试 |
| 用户价值信号 | 业务人员能指出并修正对象、关系、规则或验收问题 | 方案评审记录 |

第一阶段不使用“生成字数”“对象数量”“页面数量”作为成功指标。

## 17. 风险与处置

| 风险 | 触发信号 | 处置 |
|---|---|---|
| 退化为套模板写作 | 不同输入只替换行业名 | 蓝图元素驱动章节，增加双行业差异测试 |
| 关系语义无来源 | 缺少显式关系或可追溯知识来源 | 当前输出关系信息不足；Loop 1 才能以有来源知识建议产生 candidate 关系，并由业务审查确认 |
| PRD 与 POC 漂移 | renderer 内出现业务推导 | 推导只在 compiler，renderer 只投影 |
| AI 生成内容被误认为事实 | 无 source/status 的自动文本进入方案 | AI 输出默认 candidate，并绑定来源 |
| 过早依赖 EIP | 本地生成需要 EIP/Neo4j 在线 | EIP 作为可选 adapter，不进入核心依赖 |
| 工具过多导致产品分散 | 每个文档单独建设输入流程 | 所有工具共享 ProjectBlueprint 和输出中心 |
| 方案承诺超过证据 | synthetic demo 被写成客户效果 | 固定状态词和边界审查 |
| 自动估算引发商业风险 | 系统输出未经确认的工期或报价 | MVP 不生成工期和报价 |

## 18. 交付阶段

### Milestone 1：ProjectBlueprint

- 把当前 Proposal 重构为统一蓝图投影；
- 保持现有 CLI 与两个示例兼容；
- 增加 candidate 状态和结构验证；
- 建立 POC renderer 回归。

出口：现有 25 项测试及新增蓝图测试通过，两个样例输出保持业务语义。

### Milestone 2：PRD 与验收矩阵

- PRD renderer；
- acceptance matrix renderer；
- 修改传播测试；
- Markdown/JSON 导出。

出口：修改一个主决策或验收问题，三种输出同步更新且状态一致。

### Milestone 3：Web 工作台

- 场景表单；
- 决策卡；
- 蓝图元素编辑；
- 缺口与冲突；
- 输出预览与下载。

出口：首次用户不编辑 JSON 即可生成、修改和导出三类材料。

### Milestone 4：行业包与数据准备

- 乳业研发、乳业合规、供应链履约；
- 数据需求矩阵；
- 关系模式建议；
- 规则测试用例。

出口：新增场景包不修改编译器核心。

### Milestone 5：AI 抽取与审查

- 文档候选抽取；
- source reference；
- candidate 审查；
- 版本和 diff。

出口：未经人工确认的抽取内容不能进入 confirmed 蓝图或 EIP 导出。

### Milestone 6：EIP 验证适配器

- EIP spec 导出；
- validation request；
- 版本和报告关联；
- 运行差异回写到 Studio 项目。

出口：一份 confirmed 蓝图在 EIP 合成数据上完成结构与规则验证，并可追到蓝图版本。

## 19. 当前产品决定

当前推荐顺序是：

```text
现有 POC Generator
-> ProjectBlueprint
-> PRD + Acceptance Matrix
-> Web Workbench
-> Domain Packs
-> AI Extraction
-> EIP Validation Adapter
```

原因：先解决“多种方案材料共用一份结构化事实源”，再建设界面和 AI。若先做 Web 或 LLM，每种输出很容易形成独立逻辑，重现当前项目材料口径漂移的问题。

## 20. 产品发现问题

以下问题用于下一轮用户访谈和样例评审，不阻断 ProjectBlueprint 实现：

1. 用户最先需要导出的是 PRD、数据清单还是验收矩阵；
2. 一份客户材料中出现多个决策时，用户更愿意拆成多个项目还是建立决策组合；
3. 售前和技术负责人分别愿意确认哪些蓝图元素；
4. 客户最常纠正的是对象分类、关系语义、规则还是数据口径；
5. 哪些字段可以成为通用模板，哪些必须保持项目私有；
6. EIP spec 导出应服务现有 EIP，还是优先定义中立交换格式。
