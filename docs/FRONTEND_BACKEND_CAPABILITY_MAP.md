# Frontend / Backend Capability Map

本页中的 `LIVE` 表示仓库内已有可运行实现，不表示已连接客户系统或正在调用外部模型。

| Capability | Status | Input | Output | Boundary and prohibited wording |
| --- | --- | --- | --- | --- |
| Deterministic scenario recognition | LIVE | 固定 `synthetic_demo` 源文本与 recorded candidate | `matched` Recognition 结果、owner、trigger、provider、model | 无网络调用；不得称为“实时模型识别”或“模型正在运行” |
| DecisionPack compilation | LIVE | Recognition 生成的 Scenario，加两份显式加载的 knowledge unit | Canonical `decision_pack.v1`、bindings、sources、outcomes、后端 SHA-256 | 只生成候选知识；不得称为已批准规则、业务结论或生产决策 |
| OntologySpec compilation | LIVE | DecisionPack | `ontology_spec.v1` draft、closed reference report、编译问题、后端 SHA-256 | `complete` 仅表示编译结束；`closed` 仅表示引用闭合；不得称为验证通过、发布完成或生产可用 |
| Browser artifact adapter | LIVE | Committed `model_recognition_demo.v1` JSON | 四个只读阶段：Recognition、DecisionPack、OntologySpec、Validation | 校验既有 hash 格式与绑定关系，不在浏览器重算 hash；不得称为浏览器重新编译 |
| Deterministic document preset parser | LIVE (`synthetic_demo`) | 三段固定合成文本及其明确的 scenario ID | 一个 `compiled_artifact` route、两个 `scenario_preview` route；文本被编辑或 ID 未知时返回 `unsupported` | 只做去除首尾空白后的精确匹配；无模糊匹配、最近场景选择或实时模型调用 |
| Candidate document modeling preview | LIVE (`synthetic_demo`) | 未编辑的固定预设文本 | 三组只读候选 entity type、relation type、文本证据与能力边界 | 供应商资格变更和乳品研发回退仅为前端场景预览，不生成 hash、Validation receipt、Action 或业务变更 |
| Trial workspace interaction | LIVE | 用户选择预设、检查文本并点击“生成候选模型”；供应链预览可继续点击“Start compiled demo” | 候选图、证据选择和边界说明；只有供应链固定文本可加载一次完整 artifact，并在成功后点击/左右键切换四阶段 | 同步整包语义；无定时器逐阶段伪造；无上传、批准、发布、Action 或写回控件 |
| OntologySpec graph | LIVE (`synthetic_demo`) | Committed artifact 中的 `ontology_spec.spec` | 3 个 entity type、3 个有向 relation type、1 条独立展示的 candidate rule，以及只读证据检查器 | 固定布局且不可拖改、连线或写回；属性只在节点检查器展示；不包含客户实例或运行事实 |
| Deterministic artifact Q&A | LIVE (`synthetic_demo`) | 当前 committed pack/spec 与三个受支持的问题意图 | 带 pack/spec hash、canonical JSON pointer、stable ID 或 triple 的确定性回答；越界问题返回拒答原因 | 非实时模型调用；不使用 Validation flags 推断事实；不回答订单队列、供应商资格等实例问题 |
| ValidationReceipt schema | CONTRACT ONLY | 预期为 spec、rule、reference 与结果绑定 | `validation_receipt.v1` contract | 本演示 receipt 为 `null`；不得称为已生成验证回执 |
| Validation evaluator | NOT IMPLEMENTED | 尚未定义运行输入 | 无 | 不得称为已执行 evaluator、已通过或未通过 Validation |
| Live model provider call | NOT IMPLEMENTED | 无 API credential、endpoint 或实时请求 | 无 | provider/model 仅是 recorded deterministic demo 标识 |
| Live ontology chat API | NOT IMPLEMENTED | 无 chat endpoint、credential 或实时请求 | 无 | 当前问答是浏览器内纯函数读取 committed artifact，不得称为模型对话或实时检索 |
| Persistent draft creation | NOT IMPLEMENTED | 无数据库或服务端写入 | `draft_created = false` | 编译得到 draft artifact 不等于已创建持久化草案 |
| Publication | NOT IMPLEMENTED | 无发布请求 | `published = false` | 不得称为已发布、已上线或已生效 |
| Action execution | NOT IMPLEMENTED | 无 Action 请求 | `actions_executed = false` | 不得称为已创建任务、已审批或已执行处置 |
| External write | NOT IMPLEMENTED | 无 ERP、数据库或 Web API 连接 | `external_write = false` | 不得称为已写回 ERP、已同步客户系统或已交付生产 |
