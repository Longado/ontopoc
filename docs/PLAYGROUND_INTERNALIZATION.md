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

### 后续轮次

2. 领域参考比对：人确认对象、关系和字段对应，再看差异。
3. 确认中编辑：修改结构、核验、撤销重做。
4. 路径查找：区分结构路径与问答实际计算路径。
5. 起步与引导：少量领域起步参考与短引导。

每轮单独 PR，等用户合并后继续。迭代 9 第 2–6 轮的口径、问答闭环、版本与发布闸门、Agent 按需查询、使用记录与改进建议继续保留；原计划在 PR #45 的 `docs/PRD_ITERATION_9.md`。本轮从 `origin/main` 开始，不依赖 #45，也不复用已关闭的 Fabric 导出方向。
