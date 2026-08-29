import json
import unittest
from dataclasses import fields
from pathlib import Path

from ontology_poc_generator.errors import ScenarioValidationError
from ontology_poc_generator.generator import generate_proposal
from ontology_poc_generator.knowledge import load_knowledge_unit
from ontology_poc_generator.models import DataSource, Proposal, ScenarioParameters
from ontology_poc_generator.renderers import render_json, render_markdown


class GeneratorTest(unittest.TestCase):
    REPO_ROOT = Path(__file__).parents[1]
    KNOWLEDGE_PATH = (
        REPO_ROOT
        / "knowledge/supply_chain/supplier_evidence_boundary_v1.json"
    )

    def _supply_chain_raw(self):
        return json.loads(
            (self.REPO_ROOT / "examples/supply_chain_exception.json").read_text(
                encoding="utf-8"
            )
        )

    def _knowledge_proposal(self, raw=None):
        return generate_proposal(
            ScenarioParameters.from_dict(raw or self._supply_chain_raw()),
            (load_knowledge_unit(self.KNOWLEDGE_PATH),),
        )

    def test_direct_scenario_rejects_mutable_or_invalid_collection_fields(self):
        base = dict(
            industry="供应链",
            scene_name="履约风险处置",
            business_decision="选择需要优先处置的订单",
            decision_owner="计划经理",
            trigger="订单交付风险上升时",
            objects=("订单", "物料"),
            acceptance_questions=("能否解释？",),
        )

        for field, value in (
            ("objects", ["订单", "物料"]),
            ("acceptance_questions", ["能否解释？"]),
            ("participants", ["计划员"]),
            ("constraints", ["人工确认"]),
            ("desired_actions", ["核查"]),
            ("objects", ("订单", 1)),
            ("acceptance_questions", (" ",)),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ScenarioValidationError):
                ScenarioParameters(**{**base, field: value})

    def test_scenario_does_not_share_caller_mutable_collections(self):
        objects = ["订单", "物料"]
        raw = {
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "objects": objects,
            "acceptance_questions": ["能否解释？"],
        }
        params = ScenarioParameters.from_dict(raw)
        objects[0] = "已修改订单"

        self.assertEqual(params.objects, ("订单", "物料"))

    def test_proposal_rejects_wrong_knowledge_tuple_elements(self):
        base = dict(
            industry="供应链", scene_name="履约风险处置",
            primary_decision="选择订单", decision_owner="计划经理",
            trigger="风险上升", object_types=("订单", "物料"),
            relation_candidates=(), constraints=(), data_sources=(), data_gaps=(),
            desired_actions=(), acceptance_questions=("能否解释？",),
            decision_loop=(), responsibility_boundaries=(),
            evidence_mode="synthetic_demo", notes="",
        )

        for field in ("input_bindings", "knowledge_source_refs", "knowledge_outcomes"):
            with self.subTest(field=field), self.assertRaises(ScenarioValidationError):
                Proposal(**{**base, field: (object(),)})

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
        self.assertEqual(params.decision_key, "")
        self.assertEqual(params.object_role_bindings, ())

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

    def test_renderers_label_unimplemented_capabilities_as_planned(self):
        params = ScenarioParameters.from_dict({
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "objects": ["订单", "物料"],
            "acceptance_questions": ["能否解释订单为什么被优先处置？"],
        })

        proposal = generate_proposal(params)
        markdown = render_markdown(proposal)
        rendered_json = json.loads(render_json(proposal))
        rendered_json_text = json.dumps(rendered_json, ensure_ascii=False)

        for unimplemented_claim in (
            "确定性规则计算可验证结论",
            "修改一项业务规则或对象关系并预览影响",
            "生成后续任务，保留版本与决策轨迹",
            "可运行的合成或客户数据演示",
            "验收矩阵、修正记录和下一阶段建议",
        ):
            self.assertNotIn(unimplemented_claim, markdown)
            self.assertNotIn(unimplemented_claim, rendered_json_text)

        self.assertIn("当前已生成", markdown)
        self.assertIn("POC 计划", markdown)
        self.assertIn("候选验收问题", markdown)
        self.assertIn("尚未形成完整通过条件", markdown)
        self.assertIn("current_capabilities", rendered_json)
        self.assertIn("planned_capabilities", rendered_json)
        self.assertIn("当前已生成", rendered_json["current_capabilities"][0])
        self.assertIn("POC 计划", rendered_json["planned_capabilities"][0])

    def test_generated_artifacts_match_the_renderer_and_explicit_relations(self):
        base = {
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "objects": ["订单", "物料"],
            "acceptance_questions": ["能否解释订单为什么被优先处置？"],
        }
        without_relations = generate_proposal(ScenarioParameters.from_dict(base))
        with_relations = generate_proposal(ScenarioParameters.from_dict({
            **base,
            "relations": [{"source": "订单", "predicate": "使用", "target": "物料"}],
        }))

        markdown_without_relations = render_markdown(without_relations)
        markdown_with_relations = render_markdown(with_relations)
        json_without_relations = json.loads(render_json(without_relations))
        json_with_relations = json.loads(render_json(with_relations))
        json_without_relations_text = json.dumps(
            json_without_relations,
            ensure_ascii=False,
        )

        self.assertIn("当前已生成：Proposal 的 Markdown 文档", markdown_without_relations)
        self.assertNotIn("当前已生成：Proposal 的结构化 JSON", markdown_without_relations)
        self.assertNotIn("Markdown", json_without_relations_text)
        self.assertNotIn("Proposal 的结构化 JSON", json_without_relations_text)
        self.assertIn("当前已生成：业务决策卡、对象、约束和数据缺口草案", markdown_without_relations)
        self.assertNotIn("当前已生成：业务决策卡、对象、显式关系、约束和数据缺口草案", markdown_without_relations)
        self.assertNotRegex(
            markdown_without_relations,
            r"当前(?:已生成|仅生成)[^\n]*(显式关系|、关系、|关系草案)",
        )
        self.assertNotRegex(
            json_without_relations_text,
            r"当前(?:已生成|仅生成)[^\"]*(显式关系|、关系、|关系草案)",
        )
        self.assertIn("关系信息不足", markdown_without_relations)
        self.assertIn("关系信息不足", json_without_relations_text)
        self.assertNotIn("自动建议", markdown_without_relations)
        self.assertNotIn("候选关系需要业务人员确认", markdown_without_relations)
        self.assertIn("显式关系", markdown_with_relations)
        self.assertIn("显式候选关系待业务确认", markdown_with_relations)
        self.assertIn("显式关系", " ".join(json_with_relations["current_capabilities"]))
        self.assertRegex(markdown_with_relations, r"当前已生成[^\n]*显式关系")
        self.assertRegex(
            json.dumps(json_with_relations, ensure_ascii=False),
            r"当前已生成[^\"]*显式关系",
        )

    def test_proposal_owns_shared_capability_and_candidate_statuses(self):
        params = ScenarioParameters.from_dict({
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "objects": ["订单", "物料"],
            "acceptance_questions": ["能否解释订单为什么被优先处置？"],
        })

        proposal = generate_proposal(params)
        markdown = render_markdown(proposal)
        rendered_json = json.loads(render_json(proposal))
        legacy_proposal = Proposal(
            "供应链", "履约风险处置", "选择需要优先处置的订单", "计划经理",
            "订单交付风险上升时", ("订单", "物料"), (), (), (), (), (),
            ("能否解释订单为什么被优先处置？",), (), (), "synthetic_demo", "",
        )
        legacy_markdown = render_markdown(legacy_proposal)

        self.assertEqual(
            set(rendered_json),
            {field.name for field in fields(Proposal) if not field.name.startswith("knowledge_") and field.name != "input_bindings"},
        )
        self.assertEqual(
            [field.name for field in fields(Proposal)][-7:-3],
            [
                "current_capabilities",
                "planned_capabilities",
                "acceptance_questions_status",
                "readiness_gap",
            ],
        )
        self.assertEqual(
            tuple(rendered_json["current_capabilities"]),
            proposal.current_capabilities,
        )
        self.assertEqual(
            tuple(rendered_json["planned_capabilities"]),
            proposal.planned_capabilities,
        )
        self.assertEqual(
            rendered_json["acceptance_questions_status"],
            proposal.acceptance_questions_status,
        )
        self.assertEqual(rendered_json["readiness_gap"], proposal.readiness_gap)
        self.assertEqual(
            tuple(rendered_json["acceptance_questions"]),
            proposal.acceptance_questions,
        )
        for item in proposal.current_capabilities + proposal.planned_capabilities:
            self.assertIn(item, markdown)
        for question in proposal.acceptance_questions:
            self.assertIn(
                f"{proposal.acceptance_questions_status}：{question}",
                markdown,
            )
        self.assertIn(proposal.readiness_gap, markdown)
        self.assertTrue(legacy_proposal.current_capabilities)
        self.assertTrue(legacy_proposal.planned_capabilities)
        self.assertIn("候选验收问题：能否解释订单为什么被优先处置？", legacy_markdown)
        self.assertIn("尚未形成完整通过条件", legacy_markdown)
        for item in legacy_proposal.current_capabilities + legacy_proposal.planned_capabilities:
            self.assertIn(item, legacy_markdown)
        self.assertNotIn("显式关系", legacy_markdown)

    def test_no_relation_risk_is_recorded_when_other_risks_are_absent(self):
        params = ScenarioParameters.from_dict({
            "industry": "供应链",
            "scene_name": "履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单交付风险上升时",
            "objects": ["订单", "物料"],
            "data_sources": [
                {"name": "ERP 订单表", "type": "table", "status": "available"}
            ],
            "acceptance_questions": ["能否解释订单为什么被优先处置？"],
            "customer_data_available": True,
        })

        markdown = render_markdown(generate_proposal(params))

        self.assertIn("关系信息不足，需补充来源", markdown)
        self.assertNotIn("当前没有已登记风险", markdown)
        self.assertNotIn("自动建议", markdown)
        self.assertNotIn("显式候选关系待业务确认", markdown)

    def test_json_projection_preserves_complete_candidate_knowledge_contract(self):
        rendered = json.loads(render_json(self._knowledge_proposal()))

        self.assertEqual(len(rendered["input_bindings"]), 3)
        self.assertEqual(len(rendered["knowledge_source_refs"]), 3)
        outcome = rendered["knowledge_outcomes"][0]
        self.assertEqual(
            set(outcome),
            {
                "unit_id", "unit_version", "unit_content_hash", "match_status",
                "reason_code", "input_binding_ids", "suggestions",
            },
        )
        self.assertEqual(outcome["match_status"], "applicable")
        self.assertEqual(outcome["reason_code"], "applicable")
        self.assertEqual(len(outcome["suggestions"]), 7)
        for suggestion in outcome["suggestions"]:
            self.assertEqual(
                set(suggestion),
                {
                    "suggestion_id", "unit_id", "unit_version",
                    "unit_content_hash", "contribution_type", "semantic_key",
                    "payload_schema", "payload", "input_binding_ids",
                    "source_ref_ids", "governance_status",
                },
            )
            self.assertEqual(suggestion["governance_status"], "candidate")
            self.assertIsInstance(suggestion["payload"], dict)
        for source in rendered["knowledge_source_refs"]:
            self.assertEqual(
                set(source),
                {
                    "source_ref_id", "source_kind", "title", "locator",
                    "revision", "snapshot_sha256", "caveat",
                },
            )
            self.assertEqual(len(source["snapshot_sha256"]), 64)

    def test_markdown_appends_source_backed_candidates_with_bindings_and_sources(
        self,
    ):
        default_markdown = render_markdown(
            generate_proposal(ScenarioParameters.from_dict(self._supply_chain_raw()))
        )
        markdown = render_markdown(self._knowledge_proposal())

        self.assertNotIn("## 有来源的候选建议", default_markdown)
        self.assertIn("## 有来源的候选建议", markdown)
        for value in (
            "supply_chain.order_priority.supplier_evidence_boundary",
            "`applicable`", "`candidate`", "relation_semantics.v1",
            "supplier_qualified_to_supply_material", "QUALIFIED_TO_SUPPLY",
            "eip_quality_vocabulary_v11", "version: 11",
            "1e8b7bf0a128f716d55ab438a0830959dadd15cebcc91e576eee67e2ffd71425",
            "First-party implementation snapshot, not a customer fact or industry standard.",
            "order.primary", "binding_",
        ):
            self.assertIn(value, markdown)

    def test_non_applicable_and_insufficient_outcomes_expose_no_candidates_or_sources(
        self,
    ):
        dairy_raw = json.loads(
            (self.REPO_ROOT / "examples/dairy_rnd.json").read_text(encoding="utf-8")
        )
        insufficient_raw = self._supply_chain_raw()
        insufficient_raw["declared_bridges"] = []

        for raw, expected_status, expected_reason in (
            (dairy_raw, "not_applicable", "decision_key_mismatch"),
            (
                insufficient_raw,
                "insufficient_information",
                "order_material_bridge_missing",
            ),
        ):
            with self.subTest(status=expected_status):
                proposal = self._knowledge_proposal(raw)
                rendered = json.loads(render_json(proposal))
                outcome = rendered["knowledge_outcomes"][0]
                markdown = render_markdown(proposal)

                self.assertEqual(outcome["match_status"], expected_status)
                self.assertEqual(outcome["reason_code"], expected_reason)
                self.assertEqual(outcome["suggestions"], [])
                self.assertEqual(rendered["knowledge_source_refs"], [])
                self.assertIn("本知识单元未产生候选建议", markdown)
                self.assertNotIn("eip_quality_vocabulary_v11", markdown)
                self.assertNotIn("nano-ontoprompt", markdown)

    def test_ready_filters_only_the_readiness_gap_while_to_confirm_retains_it(
        self,
    ):
        pending_raw = self._supply_chain_raw()
        ready_raw = self._supply_chain_raw()
        ready_raw["readiness_declarations"] = [
            {"requirement_key": "queue_entry_evidence_policy", "status": "ready"}
        ]

        pending = json.loads(render_json(self._knowledge_proposal(pending_raw)))
        ready = json.loads(render_json(self._knowledge_proposal(ready_raw)))
        pending_types = {
            item["contribution_type"]
            for item in pending["knowledge_outcomes"][0]["suggestions"]
        }
        ready_types = {
            item["contribution_type"]
            for item in ready["knowledge_outcomes"][0]["suggestions"]
        }

        self.assertIn("readiness_gap", pending_types)
        self.assertNotIn("readiness_gap", ready_types)
        self.assertEqual(len(pending["knowledge_outcomes"][0]["suggestions"]), 7)
        self.assertEqual(len(ready["knowledge_outcomes"][0]["suggestions"]), 6)

    def test_knowledge_projection_does_not_claim_final_decision_or_external_write(self):
        text = render_json(self._knowledge_proposal()) + render_markdown(
            self._knowledge_proposal()
        )
        for completed_claim in (
            "confirmed queue membership", "final queue score", "action created",
            "reviewed and published", "external write completed",
        ):
            self.assertNotIn(completed_claim, text.casefold())


if __name__ == "__main__":
    unittest.main()
