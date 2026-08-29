# Ontology POC Generator 原型与架构图

本目录的图基于 `docs/PRD.md`，同时吸收 2026-08-29 多 Agent 审核结论。

## 图件

- [`prototype/index.html`](../../prototype/index.html)：可点击工作台原型；
- [`user-flow.svg`](user-flow.svg)：从场景输入到 Draft/Confirmed 交接的最小用户流程；
- [`project-blueprint-domain.svg`](project-blueprint-domain.svg)：ProjectBlueprint 领域模型；
- [`technical-architecture.svg`](technical-architecture.svg)：目标技术架构与 EIP 边界。

## PNG 预览

- [`prototype-workbench.png`](previews/prototype-workbench.png)
- [`user-flow.png`](previews/user-flow.png)
- [`project-blueprint-domain.png`](previews/project-blueprint-domain.png)
- [`technical-architecture.png`](previews/technical-architecture.png)

## 统一图例

- 绿色 `CURRENT`：当前仓库已经实现并有测试证据；
- 蓝色 `NEXT`：下一阶段建议实现；
- 灰色虚线 `FUTURE / CONDITIONAL`：需要用户验证、EIP 接口或安全条件；
- 橙色：候选、阻断、信息不足或必须人工确认的内容。

图中的位置只表示流程和依赖，不表示整体产品成熟度。当前可验证能力仍是 JSON 输入、CLI、确定性 POC Markdown/JSON 输出与两个合成样例。
