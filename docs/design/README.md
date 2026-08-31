# Ontology POC Generator 架构图

本目录的图基于 `docs/PRD.md`，记录 2026-08-29 的目标设计候选。2026-08-31 起这些图不是当前实施路线；当前事实架构和 Gate 1–3 以 `docs/TECHNICAL_ARCHITECTURE.md`、`docs/ROADMAP.md` 与 `docs/DEVELOPMENT_HANDOFF.md` 为准。

## 图件

- [`user-flow.svg`](user-flow.svg)：从场景输入到 Draft/Confirmed 交接的最小用户流程；
- [`project-blueprint-domain.svg`](project-blueprint-domain.svg)：ProjectBlueprint 领域模型；
- [`technical-architecture.svg`](technical-architecture.svg)：历史目标技术架构与 EIP 边界，不代表当前 NEXT。

## PNG 预览

- [`user-flow.png`](previews/user-flow.png)
- [`project-blueprint-domain.png`](previews/project-blueprint-domain.png)
- [`technical-architecture.png`](previews/technical-architecture.png)

## 统一图例

- 绿色 `CURRENT`：当前仓库已经实现并有测试证据；
- 蓝色 `NEXT`：2026-08-29 图稿当时的建议，不代表当前 Gate 1–3 顺序；
- 灰色虚线 `FUTURE / CONDITIONAL`：需要用户验证、EIP 接口或安全条件；
- 橙色：候选、阻断、信息不足或必须人工确认的内容。

图中的位置只表示历史候选流程和依赖，不表示整体产品成熟度或当前授权。当前能力事实以 capability map 为准。
