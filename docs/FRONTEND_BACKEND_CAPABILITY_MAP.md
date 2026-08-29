# Frontend / Backend Capability Map

本页中的 `LIVE` 表示仓库内已有可运行实现，不表示已连接客户系统或正在调用外部模型。

| Capability | Status | Input | Output | Boundary and prohibited wording |
| --- | --- | --- | --- | --- |
| Deterministic scenario recognition | LIVE | 固定 `synthetic_demo` 源文本与 recorded candidate | `matched` Recognition 结果、owner、trigger、provider、model | 无网络调用；不得称为“实时模型识别”或“模型正在运行” |
| DecisionPack compilation | LIVE | Recognition 生成的 Scenario，加两份显式加载的 knowledge unit | Canonical `decision_pack.v1`、bindings、sources、outcomes、后端 SHA-256 | 只生成候选知识；不得称为已批准规则、业务结论或生产决策 |
| OntologySpec compilation | LIVE | DecisionPack | `ontology_spec.v1` draft、closed reference report、编译问题、后端 SHA-256 | `complete` 仅表示编译结束；`closed` 仅表示引用闭合；不得称为验证通过、发布完成或生产可用 |
| Browser artifact adapter | LIVE | Committed `model_recognition_demo.v1` JSON | 四个只读阶段：Recognition、DecisionPack、OntologySpec、Validation | 校验既有 hash 格式与绑定关系，不在浏览器重算 hash；不得称为浏览器重新编译 |
| Trial workspace interaction | LIVE | 用户点击“运行演示” | 一次完整 artifact 加载，以及成功后的点击/左右键阶段切换 | 同步整包语义；无定时器逐阶段伪造；无批准、发布、Action 或写回控件 |
| ValidationReceipt schema | CONTRACT ONLY | 预期为 spec、rule、reference 与结果绑定 | `validation_receipt.v1` contract | 本演示 receipt 为 `null`；不得称为已生成验证回执 |
| Validation evaluator | NOT IMPLEMENTED | 尚未定义运行输入 | 无 | 不得称为已执行 evaluator、已通过或未通过 Validation |
| Live model provider call | NOT IMPLEMENTED | 无 API credential、endpoint 或实时请求 | 无 | provider/model 仅是 recorded deterministic demo 标识 |
| Persistent draft creation | NOT IMPLEMENTED | 无数据库或服务端写入 | `draft_created = false` | 编译得到 draft artifact 不等于已创建持久化草案 |
| Publication | NOT IMPLEMENTED | 无发布请求 | `published = false` | 不得称为已发布、已上线或已生效 |
| Action execution | NOT IMPLEMENTED | 无 Action 请求 | `actions_executed = false` | 不得称为已创建任务、已审批或已执行处置 |
| External write | NOT IMPLEMENTED | 无 ERP、数据库或 Web API 连接 | `external_write = false` | 不得称为已写回 ERP、已同步客户系统或已交付生产 |
