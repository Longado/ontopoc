from __future__ import annotations

import json
from dataclasses import asdict

from ontology_poc_generator.knowledge import (
    KnowledgeOutcome,
    KnowledgeSuggestion,
    SourceRef,
)
from ontology_poc_generator.models import Proposal


def _bullets(items: tuple[str, ...], empty: str) -> str:
    values = items or (empty,)
    return "\n".join(f"- {item}" for item in values)


def _knowledge_suggestion_dict(
    suggestion: KnowledgeSuggestion,
) -> dict[str, object]:
    return {
        "suggestion_id": suggestion.suggestion_id,
        "unit_id": suggestion.unit_id,
        "unit_version": suggestion.unit_version,
        "unit_content_hash": suggestion.unit_content_hash,
        "contribution_type": suggestion.contribution_type,
        "semantic_key": suggestion.semantic_key,
        "payload_schema": suggestion.payload_schema,
        "payload": dict(suggestion.payload),
        "input_binding_ids": list(suggestion.input_binding_ids),
        "source_ref_ids": list(suggestion.source_ref_ids),
        "governance_status": suggestion.governance_status,
    }


def _knowledge_source_dict(source: SourceRef) -> dict[str, object]:
    return {
        "source_ref_id": source.source_ref_id,
        "source_kind": source.source_kind.value,
        "title": source.title,
        "locator": source.locator,
        "revision": source.revision,
        "snapshot_sha256": source.snapshot_sha256,
        "caveat": source.caveat,
    }


def _knowledge_outcome_dict(outcome: KnowledgeOutcome) -> dict[str, object]:
    return {
        "unit_id": outcome.unit_id,
        "unit_version": outcome.unit_version,
        "unit_content_hash": outcome.unit_content_hash,
        "match_status": outcome.match_status.value,
        "reason_code": outcome.reason_code,
        "input_binding_ids": list(outcome.input_binding_ids),
        "suggestions": [
            _knowledge_suggestion_dict(suggestion)
            for suggestion in outcome.suggestions
        ],
    }


def _render_knowledge_appendix(proposal: Proposal) -> str:
    if not proposal.knowledge_outcomes:
        return ""

    bindings = {item.binding_id: item for item in proposal.input_bindings}
    sources = {
        item.source_ref_id: item for item in proposal.knowledge_source_refs
    }
    lines = ["", "## 有来源的候选建议", ""]
    for outcome in proposal.knowledge_outcomes:
        lines.extend(
            (
                f"### 知识单元 `{outcome.unit_id}`",
                "",
                f"- 单元版本：`{outcome.unit_version}`",
                f"- 内容哈希：`{outcome.unit_content_hash}`",
                f"- 匹配状态：`{outcome.match_status.value}`",
                f"- 匹配原因：`{outcome.reason_code}`",
                "",
            )
        )
        if not outcome.suggestions:
            lines.extend(
                (
                    "本知识单元未产生候选建议；该匹配状态不会推断或展示来源。",
                    "",
                )
            )
            continue

        lines.extend(("#### 相关稳定绑定", ""))
        for binding_id in outcome.input_binding_ids:
            binding = bindings[binding_id]
            lines.append(
                f"- {binding.label}：semantic `{binding.semantic_key}`；"
                f"binding `{binding.binding_id}`"
            )
        lines.append("")

        cited_source_ids: set[str] = set()
        for suggestion in outcome.suggestions:
            cited_source_ids.update(suggestion.source_ref_ids)
            payload = json.dumps(
                dict(suggestion.payload),
                ensure_ascii=False,
                sort_keys=True,
            )
            lines.extend(
                (
                    f"#### 候选建议 `{suggestion.suggestion_id}`",
                    "",
                    f"- 治理状态：`{suggestion.governance_status}`",
                    f"- 贡献类型：`{suggestion.contribution_type}`",
                    f"- Payload schema：`{suggestion.payload_schema}`",
                    f"- Semantic key：`{suggestion.semantic_key}`",
                    f"- Payload：`{payload}`",
                    "- 绑定 ID："
                    + ", ".join(f"`{item}`" for item in suggestion.input_binding_ids),
                    "- 来源 ID："
                    + ", ".join(f"`{item}`" for item in suggestion.source_ref_ids),
                    "",
                )
            )

        lines.extend(("#### 实际引用来源", ""))
        for source_id in sorted(cited_source_ids):
            source = sources[source_id]
            lines.extend(
                (
                    f"- `{source.source_ref_id}` · `{source.source_kind.value}` · {source.title}",
                    f"  - Locator：{source.locator}",
                    f"  - Revision：{source.revision}",
                    f"  - Snapshot SHA-256：`{source.snapshot_sha256}`",
                    f"  - Caveat：{source.caveat}",
                )
            )
        lines.append("")
    return "\n".join(lines)


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
    if proposal.relation_candidates:
        risks.append("显式候选关系待业务确认，不能直接视为正式本体")
    else:
        risks.append("关系信息不足，需补充来源后再形成显式候选关系")
    if proposal.notes:
        risks.append(proposal.notes)

    baseline = f"""# {proposal.scene_name} — 本体建设 POC 方案

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
    return baseline + _render_knowledge_appendix(proposal)


def render_json(proposal: Proposal) -> str:
    data = asdict(proposal)
    if not proposal.knowledge_outcomes:
        for field in (
            "input_bindings",
            "knowledge_source_refs",
            "knowledge_outcomes",
        ):
            data.pop(field)
    else:
        data["input_bindings"] = [asdict(item) for item in proposal.input_bindings]
        data["knowledge_source_refs"] = [
            _knowledge_source_dict(item) for item in proposal.knowledge_source_refs
        ]
        data["knowledge_outcomes"] = [
            _knowledge_outcome_dict(item) for item in proposal.knowledge_outcomes
        ]
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
