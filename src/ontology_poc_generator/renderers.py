from __future__ import annotations

import json
from dataclasses import asdict

from ontology_poc_generator.models import Proposal


def _bullets(items: tuple[str, ...], empty: str) -> str:
    values = items or (empty,)
    return "\n".join(f"- {item}" for item in values)


def render_markdown(proposal: Proposal) -> str:
    data_sources = tuple(
        f"{row.name}（{row.type}；{row.status}）"
        for row in proposal.data_sources
    )
    mode_note = (
        "当前使用客户可用数据设计验证路径；数据授权、口径和质量仍需单独确认。"
        if proposal.evidence_mode == "customer_data"
        else "当前无已确认客户数据，方案按 synthetic_demo 设计，只验证方法和结构，不代表客户业务事实。"
    )
    current_demo_scope = (
        "对象、显式关系、约束和数据缺口草案"
        if proposal.relation_candidates
        else "对象、约束和数据缺口草案；关系信息不足"
    )
    demo_steps = (
        f"1. 当前已生成：展示以“{proposal.trigger}”为触发条件的决策卡草案。",
        f"2. 当前已生成：展示与主决策相关的{current_demo_scope}。",
        "3. POC 计划（待验证）：在具备规则输入后，验证规则变更的影响分析。",
        f"4. POC 计划（待验证）：由{proposal.decision_owner}审阅并确认选择、拒绝或信息不足。",
        "5. POC 计划（待验证）：验证任务创建以及版本和决策轨迹记录。",
    )
    stages = (
        "阶段一（POC 计划）：确认主决策、业务对象、数据边界和候选验收问题。",
        "阶段二（POC 计划）：建立最小本体、映射和待验证的规则求值。",
        "阶段三（POC 计划）：验证演示决策闭环和业务修正记录。",
        "阶段四（POC 计划）：复盘候选验收问题，决定是否扩大数据和系统范围。",
    )
    deliverables = (
        "当前已生成：Proposal 的 Markdown 文档",
    ) + proposal.current_capabilities + proposal.planned_capabilities
    risks = list(proposal.data_gaps)
    if proposal.evidence_mode == "synthetic_demo":
        risks.append("缺少已确认客户数据，不能验证实际数据质量或业务效果")
    risks.append("候选关系需要业务人员确认，不能把自动建议直接视为正式本体")
    if proposal.notes:
        risks.append(proposal.notes)

    return f"""# {proposal.scene_name} — 本体建设 POC 方案

## POC 摘要

- 行业：{proposal.industry}
- 主决策：{proposal.primary_decision}
- 决策负责人：{proposal.decision_owner}
- 证据模式：`{proposal.evidence_mode}`
- 边界说明：{mode_note}

## 业务决策卡

| 项目 | 内容 |
|---|---|
| 触发条件 | {proposal.trigger} |
| 核心决策 | {proposal.primary_decision} |
| 最终决策者 | {proposal.decision_owner} |
| 决策输出 | 当前生成的决策卡草案：选择、拒绝或信息不足；任务创建为 POC 待验证项 |

## 决策闭环

{_bullets(proposal.decision_loop, "尚未形成决策闭环")}

## 本体对象与关系草案

### 对象类型

{_bullets(proposal.object_types, "尚未提供业务对象")}

### 候选关系

{_bullets(proposal.relation_candidates, "未提供有来源的候选关系，需要业务确认或后续知识包补充")}

## 规则、约束与状态

{_bullets(proposal.constraints, "首轮访谈需确认稳定规则、限制条件和状态定义")}

POC 计划（待验证）中的规则求值结果需区分 `pass`、`fail`、`not_evaluable` 和 `unsupported`。

## 数据映射与缺口

### 已知数据源

{_bullets(data_sources, "尚未提供数据源；POC 先使用明确标识的合成数据")}

### 数据缺口

{_bullets(proposal.data_gaps, "当前已列数据源均标记为 available，仍需核对口径和授权")}

## 技术职责边界

{_bullets(proposal.responsibility_boundaries, "尚未定义技术职责")}

## 演示剧本

{chr(10).join(demo_steps)}

## 分阶段实施范围

{_bullets(stages, "尚未形成实施阶段")}

## 验收问题与通过条件

{_bullets(tuple(f"{proposal.acceptance_questions_status}：{item}" for item in proposal.acceptance_questions), "尚未定义验收问题")}

{proposal.readiness_gap}

## 交付物

{_bullets(deliverables, "尚未定义交付物")}

## 风险和待确认事项

{_bullets(tuple(risks), "当前没有已登记风险")}
"""


def render_json(proposal: Proposal) -> str:
    return json.dumps(asdict(proposal), ensure_ascii=False, sort_keys=True, indent=2)
