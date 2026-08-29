from ontology_poc_generator.models import (
    Proposal,
    ScenarioParameters,
    _current_draft_contents,
)


def generate_proposal(params: ScenarioParameters) -> Proposal:
    relations = tuple(
        f"{relation.source} -> {relation.predicate}（待业务确认） -> {relation.target}"
        for relation in params.relations
    )
    evidence_mode = (
        "customer_data" if params.customer_data_available else "synthetic_demo"
    )
    data_gaps = tuple(
        f"{source.name}："
        f"{'数据状态待确认' if source.status == 'to_confirm' else '数据源不可用'}"
        for source in params.data_sources
        if source.status != "available"
    )
    current_draft_contents = _current_draft_contents(relations)
    return Proposal(
        industry=params.industry,
        scene_name=params.scene_name,
        primary_decision=params.business_decision,
        decision_owner=params.decision_owner,
        trigger=params.trigger,
        object_types=params.objects,
        relation_candidates=relations,
        constraints=params.constraints,
        data_sources=params.data_sources,
        data_gaps=data_gaps,
        desired_actions=params.desired_actions,
        acceptance_questions=params.acceptance_questions,
        decision_loop=(
            f"触发：{params.trigger}",
            f"当前已生成：汇集该决策相关{current_draft_contents}",
            "POC 计划（待验证）：基于确认后的规则输入进行求值，并保留信息不足状态",
            f"POC 计划（待验证）：由{params.decision_owner}进行人工确认，审阅草案并选择、拒绝或标记信息不足",
        ),
        responsibility_boundaries=(
            "LLM（POC 建议职责，尚未接入）：从需求材料抽取候选参数，不直接发布本体或业务结论",
            f"本体与规则：当前仅生成{current_draft_contents}；规则求值与版本记录为 POC 待验证能力",
            "专业模型（POC 建议职责，尚未接入）：只提供经过独立验证的预测结果",
            "Agent（POC 建议职责，尚未实现）：编排查询、验证、送审和任务创建",
            f"人工：由{params.decision_owner}作出最终决策",
        ),
        evidence_mode=evidence_mode,
        notes=params.notes,
    )
