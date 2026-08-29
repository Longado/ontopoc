import json
import unittest

from ontology_poc_generator.errors import ScenarioValidationError
from ontology_poc_generator.generator import generate_proposal
from ontology_poc_generator.models import ScenarioParameters
from ontology_poc_generator.renderers import render_json, render_markdown


class GeneratorTest(unittest.TestCase):
    def test_generates_one_decision_centered_proposal(self):
        params = ScenarioParameters.from_dict({
            "industry": "乳制品研发",
            "scene_name": "候选实验方向设计",
            "business_decision": "选择下一轮候选实验方向",
            "decision_owner": "研发项目负责人",
            "trigger": "完成需求澄清后",
            "objects": ["研发目标", "候选配方", "实验"],
            "acceptance_questions": ["能否解释候选方向的依据？"],
            "customer_data_available": False,
        })

        proposal = generate_proposal(params)

        self.assertEqual(proposal.primary_decision, "选择下一轮候选实验方向")
        self.assertEqual(proposal.decision_owner, "研发项目负责人")
        self.assertEqual(proposal.trigger, "完成需求澄清后")
        self.assertEqual(proposal.object_types, ("研发目标", "候选配方", "实验"))
        self.assertEqual(proposal.evidence_mode, "synthetic_demo")
        self.assertIn("人工确认", proposal.decision_loop[-1])

    def test_rejects_a_scenario_without_a_primary_decision(self):
        with self.assertRaisesRegex(ScenarioValidationError, "business_decision is required"):
            ScenarioParameters.from_dict({
                "industry": "供应链",
                "scene_name": "异常处置",
                "business_decision": "",
                "decision_owner": "计划经理",
                "trigger": "订单可能延期时",
                "objects": ["订单", "交付风险"],
                "acceptance_questions": ["能否解释风险依据？"],
            })

    def test_unconfirmed_source_is_reported_as_a_data_gap(self):
        params = ScenarioParameters.from_dict({
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "objects": ["订单", "物料", "供应商"],
            "data_sources": [
                {"name": "ERP 订单表", "type": "table", "status": "to_confirm"}
            ],
            "acceptance_questions": ["能否解释订单为什么被优先处置？"],
        })

        proposal = generate_proposal(params)

        self.assertEqual(proposal.data_gaps, ("ERP 订单表：数据状态待确认",))

    def test_markdown_contains_required_sections_and_is_deterministic(self):
        params = ScenarioParameters.from_dict({
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "objects": ["订单", "物料", "供应商"],
            "acceptance_questions": ["能否解释订单为什么被优先处置？"],
        })
        proposal = generate_proposal(params)

        first = render_markdown(proposal)
        second = render_markdown(proposal)

        for section in (
            "POC 摘要", "业务决策卡", "决策闭环", "本体对象与关系草案",
            "规则、约束与状态", "数据映射与缺口", "技术职责边界",
            "演示剧本", "分阶段实施范围", "验收问题与通过条件",
            "交付物", "风险和待确认事项",
        ):
            self.assertIn(f"## {section}", first)
        self.assertEqual(first, second)

    def test_json_renderer_preserves_the_structured_decision(self):
        params = ScenarioParameters.from_dict({
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "objects": ["订单", "履约风险"],
            "acceptance_questions": ["能否解释处置优先级？"],
        })

        rendered = render_json(generate_proposal(params))

        self.assertEqual(
            json.loads(rendered)["primary_decision"],
            "选择需要优先处置的订单",
        )


if __name__ == "__main__":
    unittest.main()
