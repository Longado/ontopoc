from ontology_poc_generator.models import Proposal, ScenarioParameters


def generate_proposal(params: ScenarioParameters) -> Proposal:
    relations = tuple(
        f"{source} -> 关联/约束（待业务确认） -> {target}"
        for source, target in zip(params.objects, params.objects[1:])
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
            "汇集与该决策有关的对象、关系、约束和证据",
            "确定性规则计算可验证结论，并显式保留信息不足状态",
            f"{params.decision_owner}进行人工确认，记录选择、拒绝与理由",
        ),
        responsibility_boundaries=(
            "LLM：从需求材料抽取候选参数，不直接发布本体或业务结论",
            "本体与规则：维护对象、关系、约束、版本和可复现事实",
            "专业模型：只提供经过独立验证的预测结果",
            "Agent：编排查询、验证、送审和任务创建",
            f"人工：由{params.decision_owner}作出最终决策",
        ),
        evidence_mode=evidence_mode,
        notes=params.notes,
    )
