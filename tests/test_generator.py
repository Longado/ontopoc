import json
import unittest

from ontology_poc_generator.errors import ScenarioValidationError
from ontology_poc_generator.generator import generate_proposal
from ontology_poc_generator.models import DataSource, ScenarioParameters
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

    def test_object_order_does_not_create_relation_candidates_without_relations(self):
        base = {
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "acceptance_questions": ["能否解释订单为什么被优先处置？"],
        }
        first = generate_proposal(ScenarioParameters.from_dict({
            **base,
            "objects": ["订单", "物料", "供应商"],
        }))
        reordered = generate_proposal(ScenarioParameters.from_dict({
            **base,
            "objects": ["供应商", "订单", "物料"],
        }))

        self.assertEqual(first.relation_candidates, ())
        self.assertEqual(reordered.relation_candidates, ())

    def test_explicit_relations_keep_their_semantics_when_objects_are_reordered(self):
        base = {
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "relations": [
                {"source": "订单", "predicate": "使用", "target": "物料"}
            ],
            "acceptance_questions": ["能否解释订单为什么被优先处置？"],
        }
        first = generate_proposal(ScenarioParameters.from_dict({
            **base,
            "objects": ["订单", "物料", "供应商"],
        }))
        reordered = generate_proposal(ScenarioParameters.from_dict({
            **base,
            "objects": ["供应商", "订单", "物料"],
        }))

        expected = ("订单 -> 使用（待业务确认） -> 物料",)
        self.assertEqual(first.relation_candidates, expected)
        self.assertEqual(reordered.relation_candidates, expected)

    def test_rejects_relation_with_unknown_endpoint(self):
        with self.assertRaisesRegex(
            ScenarioValidationError,
            "relations\\[0\\]\\.target must reference an object",
        ):
            ScenarioParameters.from_dict({
                "industry": "供应链",
                "scene_name": "履约风险处置",
                "business_decision": "选择需要优先处置的订单",
                "decision_owner": "计划经理",
                "trigger": "订单交付风险上升时",
                "objects": ["订单", "物料"],
                "relations": [
                    {"source": "订单", "predicate": "使用", "target": "供应商"}
                ],
                "acceptance_questions": ["能否解释订单为什么被优先处置？"],
            })

    def test_rejects_relation_with_empty_predicate(self):
        with self.assertRaisesRegex(
            ScenarioValidationError,
            "relations\\[0\\]\\.predicate is required",
        ):
            ScenarioParameters.from_dict({
                "industry": "供应链",
                "scene_name": "履约风险处置",
                "business_decision": "选择需要优先处置的订单",
                "decision_owner": "计划经理",
                "trigger": "订单交付风险上升时",
                "objects": ["订单", "物料"],
                "relations": [
                    {"source": "订单", "predicate": " ", "target": "物料"}
                ],
                "acceptance_questions": ["能否解释订单为什么被优先处置？"],
            })

    def test_positional_participants_argument_remains_compatible(self):
        params = ScenarioParameters(
            "供应链",
            "履约风险处置",
            "选择需要优先处置的订单",
            "计划经理",
            "订单交付风险上升时",
            ("订单", "物料"),
            ("能否解释订单为什么被优先处置？",),
            ("业务专家",),
        )

        self.assertEqual(params.participants, ("业务专家",))
        self.assertEqual(params.relations, ())

    def test_markdown_explains_when_explicit_relation_information_is_missing(self):
        params = ScenarioParameters.from_dict({
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "objects": ["订单", "物料"],
            "acceptance_questions": ["能否解释订单为什么被优先处置？"],
        })

        markdown = render_markdown(generate_proposal(params))

        self.assertIn(
            "未提供有来源的候选关系，需要业务确认或后续知识包补充",
            markdown,
        )

    def test_rejects_string_customer_data_available(self):
        with self.assertRaisesRegex(
            ScenarioValidationError,
            "customer_data_available must be a boolean",
        ):
            ScenarioParameters.from_dict({
                "industry": "供应链",
                "scene_name": "履约风险处置",
                "business_decision": "选择需要优先处置的订单",
                "decision_owner": "计划经理",
                "trigger": "订单交付风险上升时",
                "objects": ["订单", "物料"],
                "acceptance_questions": ["能否解释订单为什么被优先处置？"],
                "customer_data_available": "false",
            })

    def test_rejects_unknown_data_source_status(self):
        for status in ("pending", ["available"]):
            with self.subTest(status=status), self.assertRaisesRegex(
                ScenarioValidationError,
                "data_sources\\[0\\]\\.status must be available, to_confirm, or unavailable",
            ):
                ScenarioParameters.from_dict({
                    "industry": "供应链",
                    "scene_name": "履约风险处置",
                    "business_decision": "选择需要优先处置的订单",
                    "decision_owner": "计划经理",
                    "trigger": "订单交付风险上升时",
                    "objects": ["订单", "物料"],
                    "data_sources": [
                        {"name": "ERP 订单表", "type": "table", "status": status}
                    ],
                    "acceptance_questions": ["能否解释订单为什么被优先处置？"],
                })

    def test_rejects_direct_construction_with_unknown_data_source_status(self):
        with self.assertRaisesRegex(
            ScenarioValidationError,
            "status must be available, to_confirm, or unavailable",
        ):
            DataSource(name="ERP 订单表", type="table", status="pending")

    def test_rejects_direct_construction_with_string_customer_data_available(self):
        with self.assertRaisesRegex(
            ScenarioValidationError,
            "customer_data_available must be a boolean",
        ):
            ScenarioParameters(
                industry="供应链",
                scene_name="履约风险处置",
                business_decision="选择需要优先处置的订单",
                decision_owner="计划经理",
                trigger="订单交付风险上升时",
                objects=("订单", "物料"),
                acceptance_questions=("能否解释订单为什么被优先处置？",),
                customer_data_available="false",
            )

    def test_rejects_direct_construction_with_dict_data_source(self):
        with self.assertRaisesRegex(
            ScenarioValidationError,
            "data_sources\\[0\\] must be a DataSource",
        ):
            ScenarioParameters(
                industry="供应链",
                scene_name="履约风险处置",
                business_decision="选择需要优先处置的订单",
                decision_owner="计划经理",
                trigger="订单交付风险上升时",
                objects=("订单", "物料"),
                acceptance_questions=("能否解释订单为什么被优先处置？",),
                data_sources=({"name": "ERP 订单表", "type": "table", "status": "available"},),
            )

    def test_data_source_missing_text_errors_include_source_index(self):
        for source, error in (
            (
                {"type": "api", "status": "available"},
                "data_sources\\[1\\]\\.name is required",
            ),
            (
                {"name": "物流节点状态", "status": "available"},
                "data_sources\\[1\\]\\.type is required",
            ),
        ):
            with self.subTest(source=source), self.assertRaisesRegex(
                ScenarioValidationError,
                error,
            ):
                ScenarioParameters.from_dict({
                    "industry": "供应链",
                    "scene_name": "履约风险处置",
                    "business_decision": "选择需要优先处置的订单",
                    "decision_owner": "计划经理",
                    "trigger": "订单交付风险上升时",
                    "objects": ["订单", "物料"],
                    "data_sources": [
                        {"name": "ERP 订单表", "type": "table", "status": "available"},
                        source,
                    ],
                    "acceptance_questions": ["能否解释订单为什么被优先处置？"],
                })

    def test_unavailable_source_remains_unavailable_in_projections(self):
        params = ScenarioParameters.from_dict({
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "objects": ["订单", "物料"],
            "data_sources": [
                {"name": "物流节点状态", "type": "api", "status": "unavailable"}
            ],
            "acceptance_questions": ["能否解释订单为什么被优先处置？"],
        })

        proposal = generate_proposal(params)

        self.assertEqual(proposal.data_sources[0].status, "unavailable")
        self.assertEqual(proposal.data_gaps, ("物流节点状态：数据源不可用",))
        self.assertEqual(
            json.loads(render_json(proposal))["data_sources"][0]["status"],
            "unavailable",
        )
        self.assertIn("物流节点状态（api；unavailable）", render_markdown(proposal))
        self.assertIn("物流节点状态：数据源不可用", render_markdown(proposal))

    def test_proposal_is_not_changed_when_raw_data_source_dict_is_mutated(self):
        source = {"name": "ERP 订单表", "type": "table", "status": "to_confirm"}
        params = ScenarioParameters.from_dict({
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "objects": ["订单", "物料"],
            "data_sources": [source],
            "acceptance_questions": ["能否解释订单为什么被优先处置？"],
        })
        proposal = generate_proposal(params)

        source["name"] = "已修改的来源"
        source["status"] = "available"

        self.assertEqual(proposal.data_sources[0].name, "ERP 订单表")
        self.assertEqual(proposal.data_sources[0].status, "to_confirm")

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
