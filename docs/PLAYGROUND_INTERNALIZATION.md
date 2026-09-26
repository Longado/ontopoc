# Playground 内化

## 第 1 轮：本体库与 RDF/XML 导入

Pain：上传前缺少可浏览的领域参考，也不能读取已有 RDF/XML 本体。

Decision：哪些领域定义值得拿来理解自己的业务？导入的定义有哪些内容能读出、哪些尚未支持？

Outcome：本体库中能搜索、按领域筛选首批 12 份参考，查看关系图与对象属性；能导入 `.rdf/.owl` 查看定义和原文。

Non-goals：本轮不做领域匹配、结构编辑、实例生成、自动确认或问答计算，不做 Fabric 导出。

Smallest path：标准库解析 RDF/XML、本机服务提供读取接口，工作台增加本体库入口，复用现有 `OntologyGraph`。

### 收录与来源

首批为：Fourth Coffee、电商、医疗、金融、制造、大学、IQ Lab 零售供应链最终版、Zava 果园到货架，以及社区的售后服务工单、人力资源、供应链中断与风险、产线运营。

原始 RDF 与 metadata 原样保存在 `examples/ontologies/playground/`，`index.json` 记录中文入口名称、原始路径、固定上游提交及文件校验值。收录自 `microsoft/Ontology-Playground` 的提交 `42a5e5ec170c1e76343886b9d5ba7a55959cb112`，随附原始 MIT LICENSE；项目 LICENSE 保留 Microsoft 版权行。

### 能力边界

- 支持显式 `owl:Class`、`owl:DatatypeProperty`、`owl:ObjectProperty`、标签、描述及 Playground 的类型、单位、枚举、标识字段、基数、关系属性、端点注解。
- 用完整 IRI 区分概念；相对地址按 `xml:base` 解析。没有可解析的基地址时保留原文地址并提示。
- 类型或基数没有声明时保持未知，不猜值。不执行 OWL 推理，不自动读取 `owl:imports` 或连接数据绑定声明。
- 继承、限制等未转换的 RDF/OWL 结构有提示，原文完整保留；未能对应的属性与关系单独列出。
- 导入只接受 UTF-8 RDF/XML，最多 2 MB；不读取带 DTD/ENTITY 声明的 XML。
- 浏览与导入不调用模型、不写运行记录、不改变当前建模结果或确认。导入内容留在当前浏览器页面，刷新后重新选文件。

### 本机接口

- `GET /api/ontology/library`：目录与数量。
- `GET /api/ontology/library/<id>`：定义、原始 RDF、元数据及来源。
- `POST /api/ontology/library/import`：`filename`、`content_base64`，返回定义；不保存为建模运行。

### 详情布局修正

Pain：说明和长属性列表把详情撑高，用户要滚动整页才能看完整关系图。

Decision：看对象及其相邻关系时，能否保持图的位置并读完属性？

Outcome：详情在当前可视区内显示完整图区域，长属性在侧栏内滚动；说明、来源、提示及原文按需打开。

Non-goals：不改变图布局算法、解析规则或建模流程。

Smallest path：本体库详情使用紧凑工具栏与限高布局，复用现有图和浏览器原生说明弹窗。

布局回归可在本机服务启动后执行：`cd landing-page && node --test tests/ontology-library-layout.test.mjs`，需要已安装的 `agent-browser`。默认访问 5178，可用 `ONTOPOC_LAYOUT_URL` 指定试跑页面。

### 后续轮次

后续以 [2026-09-26 内化实施计划](superpowers/plans/2026-09-26-playground-internalization.md) 为准：包括微软能力与本体取舍、领域对照、确认中编辑、路径查找、起步引导的分轮范围及验收，并接回迭代 9。

本轮同时移除工作台顶部重复显示的五项状态；对象、体检、问答、对照和稳定性仍在各自页面查看。专项回归：`cd landing-page && node --test tests/workbench-header.test.mjs`。

每轮单独 PR，验收合并后继续。2026-09-26 用户授权合并现有 PR，#45 与 #47 已合入主分支。迭代 9 第 2–6 轮的口径、问答闭环、版本与发布闸门、Agent 按需查询、使用记录与改进建议继续保留，见 [迭代 9](PRD_ITERATION_9.md)。

## 第 2 轮：领域参考对照

Pain：能看领域定义，但不能用它检查本次上传建出的本体。

Decision：哪些对象、关系和字段在业务上对应，哪些差异需要补充，哪些不适用于本次范围？

Outcome：在“数据体检 → 对照标准 → 领域参考对照”选择本体库参考，手工对应对象、关系和属性，预览差异后确认保存；重新打开可恢复。

Non-goals：本轮不自动匹配、不编辑本体结构、不做 OWL 推理，不把领域样例当企业标准答案。

Smallest path：复用本体库定义、现有运行存储及关系图；新增确定性的领域映射检查，保留原标准答案比较逻辑。

### 使用与边界

1. 先对应对象，再在“关系对应”“属性对应”中选本次关系与表字段。相同名字不会自动对应；同名字段按表名与字段路径区分。
2. 不适用的项可写原因；未指定的项保持待判断。修改对象对应会清除依赖它的属性和关系对应，避免悄悄改写旧判断。
3. “预览差异”不保存；“确认对应并保存”才写到本次运行的 `evaluation.domain_reference`。取消修改恢复最近保存内容。
4. 差异分已对应、仅参考有、仅本次有、约束不同、当前无法检查、本次不适用；不打总分。对应不等于语义完全一致，缺失参考项不自动判为错误。
5. 关系端点必须符合对象对应；方向相反单列。属性类型、单位、枚举按已有声明/字段信息显示；类型可能来自数据推断。业务角色需人核对，数据统计不替代基数声明。关系属性、未转换的 OWL、未归属属性均保留无法检查提示。
6. 参考文件版本或本次本体/字段/确认判断变化后，旧对应标为过期，页面从空白对应重新核对；不将其自动迁移到新运行。提问本身不使对应过期。
7. 图中定位按需打开，图占固定视区；桌面编辑与差异切换显示，长列表在自己的区域滚动。原“已确认本体 / JSON 标准答案”仍可展开使用。

只读取本地收录的 12 份参考。外部 `.rdf/.owl` 仍可在本体库导入浏览，本轮不将临时导入内容保存为对照参考。参考对应不修改本体、数据绑定、确认、问答、派生指标或原标准答案结果；没有模型调用。

### 接口与验证

- `GET /api/ontology/runs/<saved_as>/reference`：本次字段候选、版本指纹、已保存对应及过期提示。
- `POST /api/ontology/reference/preview`：传 `saved_as`、`reference_id`、`reference_sha256`、`run_sha256`、`mappings`，返回差异，不写文件。
- `POST /api/ontology/reference/confirm`：相同请求加 `confirmed: true` 后保存。版本冲突返回 409，保留旧结果。

`mappings` 每项包含 `kind`（object/relation/property）、完整参考 IRI `reference`、本次 `local`；属性还需参考对象 IRI `owner`，`local` 为 `{source, path}`。不适用项省略 `local`，填写 `reason`。

后端回归：`PYTHONPATH=src python3 -m unittest discover -s tests -p test_ontology_reference.py`。

浏览器回归需隔离服务与公开数据运行：`cd landing-page && ONTOPOC_REFERENCE_URL=http://127.0.0.1:5179 ONTOPOC_REFERENCE_RUN=<saved_as> node --test tests/ontology-reference.test.mjs`。此测试会保存对应，不对正式运行执行。

真实模型试跑使用临时数据目录与 Northwind 91 个客户、830 条订单。客户订单数的 89 组结果与独立 CSV 计算全部一致；7 项数据检查通过；保存 2 个对象、1 条关系、1 个属性对应后，本体与原问答结果保持一致。
