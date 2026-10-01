# 自动建模与纠错迭代（2026-10-01）

本轮按 Eddie 的选择推进自动建模与纠错。主线仍是上传业务文件、模型提出本体、代码核验、人逐项决定。

## 本轮范围

- 痛点：9-30 Chinook 真模型建模被员工上级自引用关系阻断；原有同类对象两两连接也无法表达员工与上级的不同角色。
- 决策：这条业务关系的两端是否绑定到正确编号，并在真实数据中连上？
- 结果：模型可给每条关系明确两端编号列；核验失败显示具体关系、字段与纠正提示。
- 本轮不增加完整图编辑器、任意 Agent 编排、云部署或 Fabric 导出。
- 沿用 `public_ontology`、数据体检、确认记录、本体关系侧栏和 MCP；保持最多三次建模调用。

## 微软与 OntoPrompt 的当前情况

核查时间：2026-10-01。通过 GitHub API 固定源码版本，并读取相关代码；没有实测这两个上游的完整产品。

| 参考项目 | 当前事实 | 对 OntoPoc 的取舍 |
|---|---|---|
| [Microsoft Ontology-Playground](https://github.com/microsoft/Ontology-Playground/tree/42a5e5ec170c1e76343886b9d5ba7a55959cb112) | `main` 仍为我们 9-26 参考的 `42a5e5e`，最后提交日期 9-17；本轮未发现新源码 | 继续学习选中关系后展示定义、端点和属性的交互。本轮将实际编号绑定放进现有侧栏与列表。 |
| [nano-ontoprompt / Ontexus](https://github.com/jingw2/ontexus/tree/bb4b25e7e334e0c8562fc7ccd4802c1b8220ebe4) | 仓库已改名 Ontexus；默认分支最新提交是 9-30 的 star 图更新；最近非 star 图提交为 9-14 的 Action 导出修复 | 有值得学习的现有实现，但不能把每天的 star 图提交称为能力升级。 |

Ontexus 值得学习的三个具体地方：

1. **明确任务所需语义。** [semantic_validators.py](https://github.com/jingw2/ontexus/blob/bb4b25e7e334e0c8562fc7ccd4802c1b8220ebe4/backend/evals/business_journeys/semantic_validators.py) 检查必需对象、关系、引用及数值条件；有回答不等于答对任务。OntoPoc 本轮以原始 SQL 算出的员工汇报关系验证方向与数量，后续可针对具体任务补必需对象和关系检查。
2. **澄清是一个可恢复的动作。** [clarification.py](https://github.com/jingw2/ontexus/blob/bb4b25e7e334e0c8562fc7ccd4802c1b8220ebe4/backend/app/services/runtime/clarification.py) 保存待回答问题并接收人的答案。OntoPoc 本轮先显示具体绑定错误与纠正提示；后续候选是针对歧义让人选列，再核验。本轮未实现对话式澄清。
3. **Agent 使用有版本的本体并记录执行结果。** [README](https://github.com/jingw2/ontexus/blob/bb4b25e7e334e0c8562fc7ccd4802c1b8220ebe4/README.md) 与 [执行结果核对指南](https://github.com/jingw2/ontexus/blob/bb4b25e7e334e0c8562fc7ccd4802c1b8220ebe4/docs/agent-reconciliation.md) 说明发布本体、工具绑定和结果不确定时的人工核对。OntoPoc 本轮只让 MCP 返回同一端点绑定，并保证换绑定后不会继承旧确认；执行审批与外部动作不在本轮。

以上取舍是本项目判断，未复制上游代码或引入其服务栈。

## 新的关系表示

`from_identity` / `to_identity` 使用对象的逻辑识别键，值为关系来源表的实际编号列。例如同一个员工对象类型可以声明：

```json
{"from":"employee","to":"employee","source":"Employee",
 "from_identity":{"employee_id":"EmployeeId"},
 "to_identity":{"employee_id":"ReportsTo"}}
```

引用只连接已有对象，不创造上级实例，也不把下属行作为上级属性来源。查不到的非空编号进入数据体检。显式绑定只支持标量列；嵌套列表角色与关系端点变换本轮不支持。旧结果的隐式关系继续可读，不自动改写历史结果。

同类对象关系目前只能建模、核验、查看和导出；问答还不能选择遍历方向，返回明确限制。绑定或方向变化时重新确认，历史确认与稳定性不把它当成相同关系。

## 验证与交接

真实公开数据为 [Chinook](https://github.com/lerocha/chinook-database)，11 表，经本机转为工作簿后走产品的读取与建模代码。

- 模型 `deepseek/deepseek-v4.1-flash`，temperature 0，提示词 `company_ontology_modeler.v3`。
- 本轮一次完整建模，两次调用，约 30 秒；错误数 `2 → 0`，10 个对象、10 条关系，数据体检 7/7。
- 员工汇报的 7 条有向关系与原始 SQLite `EmployeeId, ReportsTo` 查询逐条一致。
- 9-30 旧结果最终为 blocked；其目的与提示词不同，不能据此量化准确率提升。
- 本地检查：后端 641 项（9 项跳过）、前端 222 项、Sites 4 项与生产构建通过；桌面与 390px 窄屏的关系绑定、空编号计数、失败提示及展开详情检查通过，浏览器无报错。
- 非作者独立完成全流程仍待真人验证。新的多角色场景由合成单测检查，不能代替公开或客户数据验收。

工作入口：`.worktrees/semantic-modeling-20261001`，分支 `codex/semantic-role-bindings`。

隔离试用：`http://127.0.0.1:5182`，后端 `8771`。数据、模型输出、SQL 对照、测试日志与截图在该工作树的 `output/semantic-trial/`，不提交原始数据或凭据。

下一步从这里继续：真人走一遍上传、查看核验、确认；若反复卡在同一个语义歧义，补“选列澄清 → 核验 → 人确认”。已有 Playground 属性编辑 3A 计划仍在，未在本轮展开。
