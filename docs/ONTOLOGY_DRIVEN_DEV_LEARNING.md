# ontology-driven-dev 学习审计与 Adapt 取舍

> 审计对象：[`sharptoolbox/ontology-driven-dev`](https://github.com/sharptoolbox/ontology-driven-dev/tree/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb)
>
> 审计快照：`0fc4f9d28667e05339ef5acaa4e8396cffdb40cb`（2026-09-02）
>
> 审计日期：2026-09-03

## 1. 结论

这个项目值得完整学习，但不适合作为 OntoPoc 的新底座，也不能直接证明“七份 YAML 可以确定性生成完整业务系统”。

它最有价值的部分是四种产品方法：

1. 用分阶段问题把模糊需求收敛为可确认的业务契约；
2. 用对象、行为、规则、主体、流程、查询和界面七个视角检查遗漏；
3. 用稳定标识把需求、模型、代码和验收串起来；
4. 用一个完整黄金案例验证端到端业务闭环，而不是只展示模型文件。

它当前没有证明的部分也很明确：

- DDL、业务服务、种子数据、前端页面和路由需要开发者或 Agent 按指导书编写，不是仓库内生成器的确定性产物；
- 本体注册表主要负责加载和查询元数据，没有执行完整的 schema、引用闭包、版本、哈希或一致性校验；
- 七模型之间仍存在可机械发现、但样例“47/47 自检”没有发现的引用缺口；
- 流程、权限、只读 SQL 和 AI 助理是可运行样例能力，不等同于生产安全能力。

因此，对 OntoPoc 的正确 Adapt 是：

```text
吸收需求发现、覆盖检查、追溯和黄金案例方法
                    ↓
将七模型变成“可编辑 DecisionPack → 编译 OntologySpec”的派生覆盖视图
                    ↓
保持事实、规则、Agent 与人工决定的现有权威边界
                    ↓
用制造业质量异常临时控制场景验证遗漏是否被提前暴露
```

本阶段不改产品代码，也不接受此前 `74363b3` spike 为正式 Adapt 结果。

## 2. 审计范围与方法

本次阅读了以下公开材料：

- [`README.md`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/README.md) 与 [`SKILL.md`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/SKILL.md)；
- `references/` 下需求探索、七模型规范、开发指导、技术架构和 UI 规范；
- [`reference-example/`](https://github.com/sharptoolbox/ontology-driven-dev/tree/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/reference-example) 的需求文档及七份 YAML；
- [`techbase/`](https://github.com/sharptoolbox/ontology-driven-dev/tree/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/techbase) 和 [`code-app-example/`](https://github.com/sharptoolbox/ontology-driven-dev/tree/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example) 的实现；
- Python 3.11 临时环境下的后端 smoke test，以及前端 Vite build。

判断标准不是“文档是否写了”，而是：

- 是否存在可定位的运行时代码；
- 是否存在从模型到产物的确定性转换；
- 是否存在自动一致性检查和失败样例；
- 是否由实际测试覆盖所宣称的行为。

运行验证全部在临时目录完成，没有写入源仓库，也没有使用 OntoPoc 或客户材料。

## 3. 主要主张审计

| 源项目主张 | 代码和文档证据 | 判断 |
| --- | --- | --- |
| 数据库、接口、菜单、权限、流程和规则全部由七模型 YAML 生成 | README 明确作出该主张；但开发指导要求手写 DDL、service、seed、页面和路由 | **表述过强**。实际是“模型指导开发并保持标识对齐”，不是仓库内确定性 codegen |
| 模型是唯一语义来源 | registry 会加载七模型；流程定义和部分元数据会被运行时消费 | **部分成立**。业务规则、报表 SQL、页面和路由仍以代码为实际执行源，流程定义还可进入数据库形成第二状态 |
| 需求、模型与代码严格可追溯 | 需求和 YAML 广泛使用稳定 ID，开发指导提供模型到实现映射 | **方法有价值，机制不完整**。没有全链路自动验证或构建失败门禁 |
| 八阶段人工确认不可跳过 | `SKILL.md` 把八次暂停写成强制纪律 | **流程约束成立**。但对单一决策产品过重，应按风险压缩，而不是照搬仪式数量 |
| 七模型一致性门禁能保证完整性 | 文档列出引用、流程和报表检查；黄金需求声称 47/47 通过 | **未被实现证明**。样例仍有权限、UI action 和跨聚合同步引用问题 |
| 流程引擎支持业务协作 | 样例能跑用户任务、网关、审批和历史记录 | **样例级成立**。system/behavior 节点没有真正调用业务行为，subflow 被跳过 |
| 强制 AI 对话和只读 SQL具有安全边界 | 样例有 prompt、工具和 SELECT 白名单过滤 | **演示级成立**。基于正则的 SQL 过滤和静态配置不足以支持生产安全结论 |
| 黄金合同案例完整可运行 | Python 3.11 smoke test 的 13 个业务步骤通过；前端能构建 | **已验证为可运行样例**。但 smoke test 没覆盖 AI、SQL 安全、前端交互或七模型一致性 |

关键证据：

- README 对“全部由 YAML 生成”的主张见 [`README.md#L12-L18`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/README.md#L12-L18)。
- 技能中的三阶段、八个门禁与构建纪律见 [`SKILL.md#L22-L80`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/SKILL.md#L22-L80)。
- 实际开发步骤要求追加 DDL、编写 service、修改 seed 和创建页面，见 [`本体模型业务功能开发指导书.md#L444-L482`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/references/%E6%9C%AC%E4%BD%93%E6%A8%A1%E5%9E%8B%E4%B8%9A%E5%8A%A1%E5%8A%9F%E8%83%BD%E5%BC%80%E5%8F%91%E6%8C%87%E5%AF%BC%E4%B9%A6.md#L444-L482)。
- registry 的实际注册逻辑见 [`registry.py#L33-L93`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/ontology/registry.py#L33-L93)。
- 黄金需求的 47/47 自检结论见 [`合同管理需求规格说明书-V9.md#L1267-L1319`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/reference-example/%E5%90%88%E5%90%8C%E7%AE%A1%E7%90%86%E9%9C%80%E6%B1%82%E8%A7%84%E6%A0%BC%E8%AF%B4%E6%98%8E%E4%B9%A6-V9.md#L1267-L1319)。

## 4. 真正的运行机制

### 4.1 七模型不是同等程度的运行时模型

| 模型 | 样例中的实际作用 | 成熟度判断 |
| --- | --- | --- |
| M1 对象 | 提供字典、聚合元数据、AI prompt 和 SQL 表白名单；数据库表仍需手写 | 部分运行时消费 |
| M2 行为 | 提供行为元数据、AI 工具说明和权限名称；实际业务行为由 service 实现 | 元数据为主 |
| M3 规则 | registry 可加载；通用表达式工具存在；合同业务规则主要写在 `domain_rules.py` | 声明与执行分离 |
| M5 主体 | 角色和权限可被首次 seed；Actor、继承和数据范围没有完整落地 | 部分映射 |
| M6 流程 | YAML 中的 `nodeGraph` 可写入数据库并由流程引擎执行用户任务和网关 | 七模型中最强的运行时路径 |
| M7 查询/报表 | 可注册查询定义；实际报表 SQL 在 `report_service.py` 手写 | 注册为主 |
| MU 界面 | 菜单和 screen 可注册；React 页面、路由和操作绑定仍手写 | 设计契约为主 |

对应代码：

- M1 字典读取接口：[`api/meta.py#L15-L26`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/api/meta.py#L15-L26)。
- M1/M2/M5/M7 注入 AI prompt：[`ai/prompt.py#L28-L85`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/ai/prompt.py#L28-L85)。
- AI 工具到行为/API 的手工分派：[`ai/tools.py#L131-L182`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/ai/tools.py#L131-L182)。
- 业务规则的实际 Python 实现：[`domain_rules.py#L1-L77`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/services/domain_rules.py#L1-L77)。
- 报表的实际 SQL 实现：[`report_service.py#L1-L103`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/services/report_service.py#L1-L103)。
- 前端路由的手写映射：[`router/index.tsx#L49-L88`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/frontend/src/router/index.tsx#L49-L88)。

### 4.2 Registry 是目录，不是编译器

`registry.py` 会读取 manifest 中列出的 YAML，并按 ID 放入多个内存字典。这个机制适合元数据发现，但当前没有：

- YAML schema 校验；
- 跨模型引用闭包校验；
- 重复 ID 拒绝；
- 模型版本、内容哈希或 semantic diff；
- 编译回执或可复现生成产物；
- 缺失文件的失败门禁。

缺失文件会被直接跳过，同 ID 后加载项会覆盖前项。ACTOR 分支只注册 role 和 permission，没有把 actor 注册进已初始化的 actors 集合。证据见 [`registry.py#L33-L93`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/ontology/registry.py#L33-L93)。

因此，OntoPoc 不应把 registry 模式升级为新的语义权威。未来若第二个真实消费者需要统一读模型，可以增加只读投影，但它必须沿“可编辑 DecisionPack → 编译 OntologySpec”的现有权威链派生。

源项目自己也保留了两套合同模型副本：`reference-example/` 和 `code-app-example/models/`。其中 M1、M5、M6、MU 内容不同，各文件版本号和 manifest 版本却相同；尤其参考 M6 使用 `activities + branches`，运行副本已经改写为 `nodeGraph`。这说明“建模规格”和“运行模型”之间的转换既未被 manifest 表达，也没有版本、哈希或生成回执可追踪。对照见 [`reference-example/m6-flow-model.yaml`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/reference-example/m6-flow-model.yaml)、[`code-app-example/models/m6-flow-model.yaml`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/models/m6-flow-model.yaml) 和相同的 [`manifest.json`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/reference-example/manifest.json)。

### 4.3 流程引擎能演示审批，但不是完整行为编排器

样例能够创建流程实例、执行用户任务、判断网关、记录历史并结束流程。但 `system_task` 和 `behavior_call` 节点只记录并继续，subflow 也被明确跳过；规则执行异常会被折叠为 `False`。证据见：

- [`flow_engine.py#L262-L284`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/engine/flow_engine.py#L262-L284)；
- [`flow_engine.py#L330-L361`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/engine/flow_engine.py#L330-L361)；
- 流程定义只在 code 不存在时写入数据库：[`seed.py#L165-L183`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/seed.py#L165-L183)。

这说明它适合学习“人在哪个节点确认、失败后去哪”，不适合当前就引入一个新的持久化工作流引擎。

### 4.4 AI 与只读 SQL 只能作为演示能力理解

SQL 入口会拒绝非 SELECT、禁止部分关键词、校验表白名单并补默认 LIMIT，见 [`sql_readonly/query.py#L12-L42`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/sql_readonly/query.py#L12-L42)。

但其边界主要依赖正则和字符串匹配，尚未证明：

- AST 级 SQL 约束；
- 列级权限和当前用户数据范围；
- 已显式给出的超大 LIMIT 上限；
- 查询超时的实际执行约束；
- 工具执行与用户身份的一致绑定。

这足以支持本地样例，不足以把“AI 可查询业务数据库”列为 OntoPoc 当前产品能力。

### 4.5 一条合同规则的端到端追溯

以“合同金额达到 100 万元后增加总经理审批”为例，链路可以人工追通：

| 层 | 对应内容 | 证据 |
| --- | --- | --- |
| 需求 | `R-01` 定义金额门槛，`B-APP-01` 财务审批后决定是否进入 `B-APP-02` | [`需求文档#L473-L474`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/reference-example/%E5%90%88%E5%90%8C%E7%AE%A1%E7%90%86%E9%9C%80%E6%B1%82%E8%A7%84%E6%A0%BC%E8%AF%B4%E6%98%8E%E4%B9%A6-V9.md#L473-L474)、[`#L512`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/reference-example/%E5%90%88%E5%90%8C%E7%AE%A1%E7%90%86%E9%9C%80%E6%B1%82%E8%A7%84%E6%A0%BC%E8%AF%B4%E6%98%8E%E4%B9%A6-V9.md#L512) |
| M3 | `RULE-CONTRACT-APPROVAL-LEVEL` 表达式为 `totalAmount >= 1000000` | [`m3-rule-model.yaml#L7-L23`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/reference-example/m3-rule-model.yaml#L7-L23) |
| 参考 M6 | `activities + branches` 描述财务审批、金额网关和总经理审批 | [`reference-example/m6-flow-model.yaml#L211-L251`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/reference-example/m6-flow-model.yaml#L211-L251) |
| 运行 M6 | 同一流程被人工改写为引擎消费的 `nodeGraph`；没有生成器、版本提升或转换回执 | [`code-app-example/models/m6-flow-model.yaml#L22-L42`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/models/m6-flow-model.yaml#L22-L42) |
| 运行时 | 流程引擎读取 `rule_ref`；合同 service 根据当前待办角色同步“待总经理审批”等业务状态 | [`flow_engine.py#L312-L361`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/engine/flow_engine.py#L312-L361)、[`contract_service.py#L259-L290`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/services/contract_service.py#L259-L290) |
| 前端 | 通用待办页调用 approve/reject/return API，没有从 M6 自动生成专用页面 | [`Todo.tsx#L19-L77`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/frontend/src/pages/workbench/Todo.tsx#L19-L77) |
| 验证 | smoke test 同时断言小额合同一次审批完成、大额合同进入总经理待办并最终完成 | [`smoke_test.py#L88-L115`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/smoke_test.py#L88-L115) |

这条链证明“稳定 ID + 黄金路径”能形成可理解的人工追溯，也同时暴露了机制边界：需求中的 `R-01` 与 YAML 的 `RULE-CONTRACT-APPROVAL-LEVEL` 并非同一稳定 ID，且前端与状态同步依赖手写映射。OntoPoc 应学习追溯链，但把它升级为机器可检验、带实现状态的派生视图。

## 5. 黄金案例验证结果

在干净临时目录中，按项目声明的 Python 3.10+ 条件使用 Python 3.11 安装公开依赖后：

- 后端 smoke test 的 13 个步骤通过，包括主数据、合同创建、两级审批、驳回、开票、收款、冲销、流程记录和报表；
- 前端 Vite build 成功，构建器给出大 chunk 警告；
- smoke test 没有调用 AI、动态 SQL 或浏览器交互，也没有执行七模型一致性校验。

复现入口与本次结果摘要：

```text
cd code-app-example/backend && <Python 3.11 venv>/python smoke_test.py
→ 13 个业务步骤完成，无断言失败

cd code-app-example/frontend && npm run build
→ vite build 成功；2361 modules transformed；产生大 chunk 警告
```

第一次用系统默认 Python 3.9 运行时在 `hashlib.scrypt` 处失败，但项目声明 Python 3.10+，所以这不是源项目缺陷。本次通过结果只证明公开样例在上述环境可运行，不证明其为生产系统或通用生成器。

样例验证入口见 [`code-app-example/README.md`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/README.md) 和 [`smoke_test.py`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/backend/smoke_test.py)。

## 6. 可机械发现的一致性缺口

对 `reference-example` 和 `code-app-example/models` 做 ID 引用核对，两套模型出现相同问题：

1. 10 处 M2 `requiredPermissions` 引用了 3 个 M5 未定义权限：
   - `PERM-CONTRACT-CREATE`；
   - `PERM-INVOICE-ISSUE`；
   - `PERM-MASTERDATA-MAINTAIN`。
2. 5 个 `USER_ACTION` 行为没有对应 MU action：
   - `Contract_ApproveGeneralManager`；
   - `Contract_Resubmit`；
   - `Contract_VoidOrArchive`；
   - `Invoice_Resubmit`；
   - `Invoice_Void`。
3. `PaymentStage_UpdateInvoiceStatus` 同步到 `Contract_UpdateSettlementStatus`，两者都属于 `AGG-CONTRACT-001`，与框架“跨独立聚合使用 syncTrigger”的边界不一致。

模型原文可在 [`reference-example`](https://github.com/sharptoolbox/ontology-driven-dev/tree/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/reference-example) 和 [`code-app-example/models`](https://github.com/sharptoolbox/ontology-driven-dev/tree/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/code-app-example/models) 复核。

稳定标识也没有贯穿全部层级：需求规范要求 REF、INV、R 使用全局稳定编号，但 M1 的 `refRules` 和 `invariants` 字段没有 `id`；需求中的 `R-01` 到模型中的 `RULE-CONTRACT-APPROVAL-LEVEL` 只能靠人工理解对应。见 [`ontology_modeling_framework_v9.md#L221-L238`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/references/ontology_modeling_framework_v9.md#L221-L238) 和 [`#L268-L275`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/references/ontology_modeling_framework_v9.md#L268-L275)。manifest 只引用整份需求文档，没有为模型元素提供机器可读的 `source_ref_ids`，见 [`manifest.json`](https://github.com/sharptoolbox/ontology-driven-dev/blob/0fc4f9d28667e05339ef5acaa4e8396cffdb40cb/reference-example/manifest.json)。

公开需求中的 `[已确认]` 与“47/47 通过”也没有附带可核验的人类确认记录。因此它应被理解为方法范例中的文档状态，不能直接当作真实客户确认或交付验收。

这些问题不否定七模型的价值，反而说明最值得 Adapt 的不是 YAML 文件本身，而是把引用闭包、唯一归属、可达性和实现状态变成可执行检查。

## 7. 七模型对 OntoPoc 的学习价值

| 视角 | 应回答的问题 | OntoPoc 的落点 |
| --- | --- | --- |
| M1 对象 | 哪些业务对象、属性和关系决定影响范围？ | OntologySpec 的实体、关系和事实证据 |
| M2 行为 | 用户或系统到底要完成什么动作？ | ingest、建模、评估、确认、驳回等产品行为覆盖 |
| M3 规则 | 哪条规则影响哪个行为，谁拥有它？ | 四态确定性规则和唯一 rule owner |
| M5 主体 | 谁提供证据、谁建议、谁作最终决定？ | 质量负责人、业务参与者、Agent 和禁止动作 |
| M6 流程 | 正常路径、失败路径和人工确认点是否完整？ | 当前决策序列的派生流程视图，不新增工作流引擎 |
| M7 查询 | 用户必须看到哪些问题的答案？ | 影响范围、证据、反证、缺口和回执视图 |
| MU 界面 | 哪些内容需要成为稳定交互？ | 后置到功能闭环被验证之后，由产品行为派生 |

这七个视角应作为“遗漏雷达”，而不是七个都可编辑、都能决定运行行为的配置源。

## 8. ADOPT / ADAPT / DEFER / REJECT

### ADOPT：直接吸收方法

| 方法 | 产品理由 | 验收方式 |
| --- | --- | --- |
| A/B 信息区分 | 猜错会改变业务结论的信息必须由人确认 | 未确认的系统归属、关系和排除条件不得进入确定结论 |
| 未确认项保持未确认 | 避免把行业常识伪装成客户事实 | 输出明确 unresolved questions 或 `not_evaluable` |
| 规则唯一归属 | 防止相同规则在模型、Agent prompt 和代码中重复漂移 | 每条规则只有一个 authority，并能追到使用它的行为 |
| 行为—规则—行为追溯 | 能说明规则在何时生效、产生什么后果 | 从临时控制决定追到规则、证据和后续人工动作 |
| 流程失败路径与可达性检查 | 黄金路径之外的缺口更能暴露产品问题 | 驳回、缺证、无法评估和修正路径均可到达 |
| 一对多来源先聚合再关联 | 避免 BOM、批次、库存关系连接造成范围重复或放大 | 影响对象计数与来源明细可复核 |
| 角色与具体个人分离 | 业务责任稳定，人员绑定可变化 | 决策 owner 是角色，执行和确认记录具体人 |
| 完整黄金业务路径 | 比孤立 CRUD 或模型文件更能证明用户闭环 | 一个已知案例贯通决定、分支、人工动作、修正/冲销和结果 |

### ADAPT：改变形态后吸收

| 源项目做法 | OntoPoc 形态 | 为什么这样改 |
| --- | --- | --- |
| 八阶段硬暂停 | 痛点/决定、证据/数据、判断/动作边界、黄金验收四个风险门 | 只在结论可能改变时要求确认 |
| 每个问题必须给 AI 建议 | 对高风险未知允许回答“无法安全建议” | 不把缺少客户证据时的猜测包装为建议 |
| 七份可编辑 YAML | 从可编辑 DecisionPack 和编译所得 OntologySpec 派生 CoverageView | 保持单一可编辑语义权威 |
| 模型到代码映射表 | 带 source ref、execution state 和 hash 的实现追溯视图 | 区分 declared、implemented、verified，而非只看同名 ID |
| M6 流程运行时 | 先做确认点、失败路径和恢复路径的覆盖检查 | 当前没有跨天等待、重试和真实回执需求 |
| M7 通用报表 | 临时控制影响范围、证据、反证、缺口和回执查询 | 围绕一个业务决定，而不是报表平台 |
| MU UI 模型 | 功能闭环稳定后生成只读界面契约 | 当前优先验证能力，不让网页替代产品能力 |
| 单一黄金案例 | 黄金案例之外增加未提前调参的 held-out 挑战 | 防止围绕唯一 demo 过拟合 |

### DEFER：有第二个真实需求后再做

- 通用本体 registry：等出现第二个独立运行时消费者；
- UI、API 和报表 codegen：等第二个稳定业务应用证明重复结构；
- 持久化工作流引擎：等出现跨天等待、失败重试或外部回执；
- 通用自然语言 SQL：等固定决策视图无法覆盖高频真实问题，并具备权限与审计条件。

### REJECT：不进入当前路线

- 复制 Flask/React techbase 再改造成 OntoPoc；
- 让七模型 YAML 与 DecisionPack / OntologySpec 同时可编辑；
- 固定八次硬暂停、固定两份报告或固定 UI 样式；
- 强制每个产品都带 AI 对话框；
- 把 Agent 按模型写出的代码称为确定性生成；
- 用同步的五系统 demo 连接器冒充真实 ERP/MES/QMS/WMS/PLM 集成；
- 在没有用户和数据权限约束时开放动态业务 SQL。

## 9. 对完整 Adapt 计划的具体影响

Phase 1 进入设计时，应只引入四个决策门及其阻塞条件：

1. 痛点与决定：触发、决定句、decision owner 和时限；
2. 证据与数据：来源系统、标识、时间语义、关键关系和缺口；
3. 判断与动作边界：四态规则、排除条件、Agent 禁止主张和人工权威；
4. 黄金验收：已知案例、边界案例和留出案例。

Phase 2 的七模型覆盖必须满足三个约束：

- 只读派生，不新增七份业务配置；
- 只检查当前 CoverageView 回答临时控制决定所必需的引用、角色和路径，不建设通用七模型 validator；
- 只回答 `covered`、`missing`、`not_applicable`，并为 `covered` 提供当前证据；`declared_only`、`executable`、`verified` 等实现状态留到 Phase 3 的实现追溯契约。

Phase 3 之前不应扩展 `74363b3`。届时要用批准后的 Phase 2 契约判断它是：保留并重写、仅作为 spike 参考，还是撤销。当前既不回退，也不继续叠加。

## 10. Phase 0 出口建议

建议批准本文件的学习矩阵，并进入 Phase 1 的“四个决策门”契约设计。

批准不代表授权后续所有实现。Phase 1 的目标只应是：让系统在建模开始前发现会改变临时控制结论的关键未知，并把不能安全补全的内容留给人确认。

进入 Phase 1 时仍保持以下产品边界：

- DecisionPack 是唯一可编辑语义权威，OntologySpec 是其编译产物；
- Python evaluator 是四态判断权威；
- Agent 只产生候选、质疑与修订建议；
- 质量负责人决定最终临时控制范围；
- 不连接真实外部系统，不执行停产、冻结库存或拦截发运；
- 不先做网页、通用工作流、registry 或 codegen。
