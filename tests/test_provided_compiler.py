import unittest
from pathlib import Path

from ontology_poc_generator.compiler import compile_decision_pack
from ontology_poc_generator.decision_pack import decision_pack_content_hash
from ontology_poc_generator.errors import SpecCompilationError
from ontology_poc_generator.identity import (
    stable_entity_type_id,
    stable_relation_type_id,
)
from ontology_poc_generator.knowledge import load_knowledge_unit
from ontology_poc_generator.models import DeclaredBridge, ScenarioParameters
from ontology_poc_generator.ontology_spec import (
    EvidenceScope,
    SpecGovernanceStatus,
    SpecOriginKind,
    SpecStage,
)
from ontology_poc_generator.provided_compiler import compile_provided_spec


ROOT = Path(__file__).parents[1]
KNOWLEDGE_UNIT_PATH = (
    ROOT / "knowledge/supply_chain/supplier_evidence_boundary_v1.json"
)


def scenario(**overrides: object) -> ScenarioParameters:
    data = {
        "industry": "供应链",
        "scene_name": "订单干预",
        "business_decision": "哪些订单进入优先干预队列",
        "decision_owner": "计划经理",
        "trigger": "订单承诺变化",
        "objects": ["订单", "物料", "供应商"],
        "acceptance_questions": ["结论可解释吗？"],
        "relations": [
            {"source": "供应商", "predicate": "历史供应", "target": "物料"}
        ],
        "decision_key": "order_priority_intervention",
        "object_role_bindings": [
            {
                "role_key": "customer_order",
                "semantic_key": "order.primary",
                "object_label": "订单",
            },
            {
                "role_key": "material",
                "semantic_key": "material.required",
                "object_label": "物料",
            },
            {
                "role_key": "supplier",
                "semantic_key": "supplier.candidate",
                "object_label": "供应商",
            },
        ],
        "declared_bridges": [
            {
                "semantic_key": "customer_order_requires_material",
                "source_role_key": "customer_order",
                "predicate": "REQUIRES",
                "target_role_key": "material",
            }
        ],
    }
    data.update(overrides)
    return ScenarioParameters.from_dict(data)


class ProvidedCompilerTest(unittest.TestCase):
    def test_maps_only_provided_bindings_and_bridges_to_candidate_spec(self):
        pack = compile_decision_pack(scenario())

        spec = compile_provided_spec(pack)

        self.assertEqual(spec.schema, "ontology_spec.v1")
        self.assertEqual(spec.decision_key, pack.scenario.decision_key)
        self.assertEqual(spec.pack_content_hash, decision_pack_content_hash(pack))
        self.assertIs(spec.stage, SpecStage.DRAFT)
        self.assertIs(spec.evidence_scope, EvidenceScope.SYNTHETIC_DEMO)
        self.assertIs(spec.governance_status, SpecGovernanceStatus.CANDIDATE)
        self.assertEqual(
            spec.input_binding_ids,
            tuple(binding.binding_id for binding in pack.input_bindings),
        )
        self.assertEqual(len(spec.entity_types), 3)
        self.assertEqual(len(spec.relation_types), 1)
        self.assertEqual(spec.property_types, ())
        self.assertEqual(spec.rule_declarations, ())
        self.assertEqual(spec.compilation_issues, ())

        entity_by_role = {item.role_key: item for item in spec.entity_types}
        for binding in pack.input_bindings:
            entity = entity_by_role[binding.role_key]
            self.assertEqual(
                entity.type_id,
                stable_entity_type_id(
                    pack.scenario.decision_key,
                    binding.role_key,
                    binding.semantic_key,
                ),
            )
            self.assertEqual(entity.semantic_key, binding.semantic_key)
            self.assertEqual(entity.label, binding.label)
            self.assertIs(entity.governance_status, SpecGovernanceStatus.CANDIDATE)
            self.assertIs(entity.origin_kind, SpecOriginKind.PROVIDED_INPUT)
            self.assertEqual(entity.origin_ref_id, binding.binding_id)

        relation = spec.relation_types[0]
        self.assertEqual(relation.semantic_key, "customer_order_requires_material")
        self.assertEqual(relation.predicate, "REQUIRES")
        self.assertEqual(relation.domain_type_id, entity_by_role["customer_order"].type_id)
        self.assertEqual(relation.range_type_id, entity_by_role["material"].type_id)
        self.assertEqual(
            relation.description,
            "customer_order REQUIRES material",
        )
        self.assertEqual(
            relation.relation_type_id,
            stable_relation_type_id(
                relation.semantic_key,
                relation.domain_type_id,
                relation.predicate,
                relation.range_type_id,
            ),
        )
        self.assertIs(relation.governance_status, SpecGovernanceStatus.CANDIDATE)
        self.assertIs(relation.origin_kind, SpecOriginKind.PROVIDED_INPUT)
        self.assertEqual(relation.origin_ref_id, relation.semantic_key)

    def test_roles_with_same_semantic_key_remain_distinct_entity_types(self):
        params = scenario(
            object_role_bindings=[
                {
                    "role_key": "customer_order",
                    "semantic_key": "business_object.shared",
                    "object_label": "订单",
                },
                {
                    "role_key": "material",
                    "semantic_key": "business_object.shared",
                    "object_label": "物料",
                },
                {
                    "role_key": "supplier",
                    "semantic_key": "supplier.candidate",
                    "object_label": "供应商",
                },
            ]
        )

        spec = compile_provided_spec(compile_decision_pack(params))
        shared = [
            item
            for item in spec.entity_types
            if item.semantic_key == "business_object.shared"
        ]

        self.assertEqual(len(shared), 2)
        self.assertEqual({item.role_key for item in shared}, {"customer_order", "material"})
        self.assertEqual(len({item.type_id for item in shared}), 2)

    def test_label_rename_and_input_reorder_preserve_element_ids(self):
        first = compile_provided_spec(compile_decision_pack(scenario()))
        renamed = scenario(
            industry="不同领域",
            scene_name="另一场景",
            business_decision="另一段业务决策文本",
            trigger="另一触发文本",
            objects=["供应方", "物料项", "客户订单"],
            relations=[
                {"source": "客户订单", "predicate": "旧关系", "target": "供应方"}
            ],
            object_role_bindings=[
                {
                    "role_key": "supplier",
                    "semantic_key": "supplier.candidate",
                    "object_label": "供应方",
                },
                {
                    "role_key": "material",
                    "semantic_key": "material.required",
                    "object_label": "物料项",
                },
                {
                    "role_key": "customer_order",
                    "semantic_key": "order.primary",
                    "object_label": "客户订单",
                },
            ],
        )
        second = compile_provided_spec(compile_decision_pack(renamed))

        self.assertEqual(
            {item.type_id for item in first.entity_types},
            {item.type_id for item in second.entity_types},
        )
        self.assertEqual(
            {item.relation_type_id for item in first.relation_types},
            {item.relation_type_id for item in second.relation_types},
        )
        self.assertNotEqual(first.pack_content_hash, second.pack_content_hash)

    def test_unbound_objects_and_legacy_relations_are_ignored(self):
        params = scenario(
            objects=["订单", "物料", "供应商", "未绑定对象"],
            relations=[
                {"source": "未绑定对象", "predicate": "旧关系", "target": "供应商"},
                {"source": "供应商", "predicate": "旧供应", "target": "物料"},
            ],
        )

        spec = compile_provided_spec(compile_decision_pack(params))

        self.assertEqual({item.label for item in spec.entity_types}, {"订单", "物料", "供应商"})
        self.assertEqual(
            {item.predicate for item in spec.relation_types},
            {"REQUIRES"},
        )

    def test_knowledge_suggestions_are_not_compiled_by_this_stage(self):
        pack = compile_decision_pack(
            scenario(),
            (load_knowledge_unit(KNOWLEDGE_UNIT_PATH),),
        )
        self.assertTrue(pack.knowledge_outcomes[0].suggestions)

        spec = compile_provided_spec(pack)

        self.assertTrue(
            all(
                item.origin_kind is SpecOriginKind.PROVIDED_INPUT
                for item in spec.entity_types + spec.relation_types
            )
        )
        self.assertEqual(spec.property_types, ())
        self.assertEqual(spec.rule_declarations, ())
        self.assertEqual(spec.compilation_issues, ())

    def test_empty_decision_key_is_a_typed_compilation_error(self):
        pack = compile_decision_pack(
            scenario(decision_key="", object_role_bindings=[], declared_bridges=[])
        )

        with self.assertRaises(SpecCompilationError) as caught:
            compile_provided_spec(pack)

        self.assertEqual(caught.exception.code, "missing_decision_key")

    def test_broken_bridge_source_endpoint_is_a_typed_compilation_error(self):
        pack = compile_decision_pack(scenario())
        object.__setattr__(
            pack.scenario,
            "declared_bridges",
            (
                DeclaredBridge(
                    semantic_key="broken_bridge",
                    source_role_key="missing_role",
                    predicate="REQUIRES",
                    target_role_key="material",
                ),
            ),
        )

        with self.assertRaises(SpecCompilationError) as caught:
            compile_provided_spec(pack)

        self.assertEqual(caught.exception.code, "missing_relation_role_binding")

    def test_broken_bridge_target_endpoint_is_a_typed_compilation_error(self):
        pack = compile_decision_pack(scenario())
        bridge = pack.scenario.declared_bridges[0]
        object.__setattr__(bridge, "target_role_key", "missing_role")

        with self.assertRaises(SpecCompilationError) as caught:
            compile_provided_spec(pack)

        self.assertEqual(caught.exception.code, "missing_relation_role_binding")


if __name__ == "__main__":
    unittest.main()
