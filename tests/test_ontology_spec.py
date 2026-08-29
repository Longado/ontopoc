from dataclasses import FrozenInstanceError
import hashlib
import json
import unittest

from ontology_poc_generator.errors import (
    OntologySpecValidationError,
    SpecCompilationError,
)
from ontology_poc_generator.ontology_spec import (
    CompilationIssue,
    CompilationIssueSeverity,
    CompilationStatus,
    EntityTypeSpec,
    EvidenceScope,
    OntologySpec,
    PropertyTypeSpec,
    RelationTypeSpec,
    RuleConditionSpec,
    RuleDeclarationSpec,
    SpecGovernanceStatus,
    SpecOriginKind,
    SpecStage,
    canonical_ontology_spec_json,
    ontology_spec_content_hash,
    ontology_spec_to_dict,
)


VALID_HASH = "a" * 64


def entity_fixture(
    *,
    type_id: str = "type_order",
    role_key: str = "customer_order",
) -> EntityTypeSpec:
    return EntityTypeSpec(
        type_id=type_id,
        role_key=role_key,
        semantic_key=f"{role_key}.candidate",
        label="客户订单",
        governance_status=SpecGovernanceStatus.CANDIDATE,
        origin_kind=SpecOriginKind.PROVIDED_INPUT,
        origin_ref_id=f"binding_{role_key}",
    )


def relation_fixture(
    *, relation_type_id: str = "relation_order_requires_material"
) -> RelationTypeSpec:
    return RelationTypeSpec(
        relation_type_id=relation_type_id,
        semantic_key="customer_order_requires_material",
        predicate="REQUIRES",
        domain_type_id="type_order",
        range_type_id="type_material",
        description="订单需要物料。",
        governance_status=SpecGovernanceStatus.CANDIDATE,
        origin_kind=SpecOriginKind.PROVIDED_INPUT,
        origin_ref_id="customer_order_requires_material",
    )


def property_fixture(
    *, property_type_id: str = "property_order_state"
) -> PropertyTypeSpec:
    return PropertyTypeSpec(
        property_type_id=property_type_id,
        semantic_key="customer_order.state",
        domain_type_id="type_order",
        value_type="symbolic_state",
        governance_status=SpecGovernanceStatus.CANDIDATE,
        origin_kind=SpecOriginKind.KNOWLEDGE_SUGGESTION,
        origin_ref_id="suggestion_rule",
    )


def rule_fixture(*, rule_id: str = "rule_priority_queue") -> RuleDeclarationSpec:
    return RuleDeclarationSpec(
        rule_id=rule_id,
        semantic_key="order_priority.queue_entry",
        rule_kind="all_conditions_match",
        subject_type_id="type_order",
        conditions=(
            RuleConditionSpec(
                property_type_id="property_order_state",
                operator="in",
                allowed_values=("at_risk",),
            ),
        ),
        output_conclusion_key="priority_intervention_queue",
        positive_conclusion_value="enter",
        negative_conclusion_value="do_not_enter",
        description="Synthetic policy declaration.",
        governance_status=SpecGovernanceStatus.CANDIDATE,
        origin_suggestion_id="suggestion_rule",
    )


def issue_fixture(*, issue_id: str = "issue_readiness") -> CompilationIssue:
    return CompilationIssue(
        issue_id=issue_id,
        code="readiness_gap_blocks_rule_compilation",
        severity=CompilationIssueSeverity.REQUIRES_REVIEW,
        suggestion_id="suggestion_readiness",
        payload_schema="readiness_gap.v1",
        message="Queue policy still requires review.",
    )


def spec_fixture(**overrides: object) -> OntologySpec:
    values = {
        "schema": "ontology_spec.v1",
        "decision_key": "order_priority_intervention",
        "pack_content_hash": VALID_HASH,
        "stage": SpecStage.DRAFT,
        "evidence_scope": EvidenceScope.SYNTHETIC_DEMO,
        "governance_status": SpecGovernanceStatus.CANDIDATE,
        "input_binding_ids": (),
        "entity_types": (),
        "relation_types": (),
        "property_types": (),
        "rule_declarations": (),
        "compilation_issues": (),
    }
    values.update(overrides)
    return OntologySpec(**values)


class OntologySpecContractTest(unittest.TestCase):
    def test_spec_is_frozen_candidate_draft_synthetic(self):
        spec = spec_fixture()

        with self.assertRaises(FrozenInstanceError):
            spec.stage = "published"

    def test_all_contracts_are_frozen(self):
        values = (
            entity_fixture(),
            relation_fixture(),
            property_fixture(),
            RuleConditionSpec(
                property_type_id="property_order_state",
                operator="in",
                allowed_values=("at_risk",),
            ),
            rule_fixture(),
            issue_fixture(),
        )

        for value in values:
            with self.subTest(contract=type(value).__name__), self.assertRaises(
                FrozenInstanceError
            ):
                value.semantic_key = "changed"

    def test_enums_expose_only_frozen_loop_two_states(self):
        self.assertEqual(tuple(SpecStage), (SpecStage.DRAFT,))
        self.assertEqual(tuple(EvidenceScope), (EvidenceScope.SYNTHETIC_DEMO,))
        self.assertEqual(
            tuple(SpecGovernanceStatus), (SpecGovernanceStatus.CANDIDATE,)
        )
        self.assertEqual(
            tuple(SpecOriginKind),
            (
                SpecOriginKind.PROVIDED_INPUT,
                SpecOriginKind.KNOWLEDGE_SUGGESTION,
            ),
        )
        self.assertEqual(
            tuple(CompilationIssueSeverity),
            (
                CompilationIssueSeverity.REQUIRES_REVIEW,
                CompilationIssueSeverity.BLOCKING,
            ),
        )
        self.assertEqual(
            tuple(CompilationStatus),
            (CompilationStatus.COMPLETE, CompilationStatus.BLOCKED),
        )
        with self.assertRaises(ValueError):
            SpecGovernanceStatus("confirmed")
        with self.assertRaises(ValueError):
            SpecStage("published")

    def test_rejects_strings_in_place_of_enum_members(self):
        with self.assertRaisesRegex(
            OntologySpecValidationError, "stage must be SpecStage"
        ):
            spec_fixture(stage="draft")

        with self.assertRaisesRegex(
            OntologySpecValidationError,
            "governance_status must be SpecGovernanceStatus",
        ):
            entity_fixture().__class__(
                type_id="type_order",
                role_key="customer_order",
                semantic_key="customer_order.candidate",
                label="客户订单",
                governance_status="candidate",
                origin_kind=SpecOriginKind.PROVIDED_INPUT,
                origin_ref_id="binding_order",
            )

    def test_requires_exact_schema_and_sha256_pack_hash(self):
        for field, value, message in (
            ("schema", "ontology_spec.v2", "schema must be ontology_spec.v1"),
            ("pack_content_hash", "not-a-hash", "pack_content_hash"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(
                OntologySpecValidationError, message
            ):
                spec_fixture(**{field: value})

    def test_rejects_empty_text_and_ids(self):
        with self.assertRaisesRegex(OntologySpecValidationError, "decision_key"):
            spec_fixture(decision_key=" ")
        with self.assertRaisesRegex(OntologySpecValidationError, "type_id"):
            entity_fixture(type_id="")
        with self.assertRaisesRegex(OntologySpecValidationError, "description"):
            RelationTypeSpec(
                relation_type_id="relation_id",
                semantic_key="relation.semantic",
                predicate="RELATES_TO",
                domain_type_id="type_a",
                range_type_id="type_b",
                description=" ",
                governance_status=SpecGovernanceStatus.CANDIDATE,
                origin_kind=SpecOriginKind.PROVIDED_INPUT,
                origin_ref_id="bridge_id",
            )

    def test_all_collections_require_tuples(self):
        collection_fields = (
            "input_binding_ids",
            "entity_types",
            "relation_types",
            "property_types",
            "rule_declarations",
            "compilation_issues",
        )
        for field in collection_fields:
            with self.subTest(field=field), self.assertRaisesRegex(
                OntologySpecValidationError, f"{field} must be a tuple"
            ):
                spec_fixture(**{field: []})

        with self.assertRaisesRegex(
            OntologySpecValidationError, "conditions must be a tuple"
        ):
            RuleDeclarationSpec(
                **{
                    **rule_fixture().__dict__,
                    "conditions": [],
                }
            )
        with self.assertRaisesRegex(
            OntologySpecValidationError, "allowed_values must be a tuple"
        ):
            RuleConditionSpec(
                property_type_id="property_order_state",
                operator="in",
                allowed_values=["at_risk"],
            )

    def test_rejects_wrong_collection_element_types(self):
        for field, value, expected in (
            ("input_binding_ids", (1,), "str"),
            ("entity_types", ("entity",), "EntityTypeSpec"),
            ("relation_types", ("relation",), "RelationTypeSpec"),
            ("property_types", ("property",), "PropertyTypeSpec"),
            ("rule_declarations", ("rule",), "RuleDeclarationSpec"),
            ("compilation_issues", ("issue",), "CompilationIssue"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(
                OntologySpecValidationError, expected
            ):
                spec_fixture(**{field: value})

    def test_rejects_duplicate_ids(self):
        duplicate_cases = (
            ("input_binding_ids", ("binding_same", "binding_same"), "input_binding_id"),
            ("entity_types", (entity_fixture(), entity_fixture()), "type_id"),
            (
                "relation_types",
                (relation_fixture(), relation_fixture()),
                "relation_type_id",
            ),
            (
                "property_types",
                (property_fixture(), property_fixture()),
                "property_type_id",
            ),
            (
                "rule_declarations",
                (rule_fixture(), rule_fixture()),
                "rule_id",
            ),
            (
                "compilation_issues",
                (issue_fixture(), issue_fixture()),
                "issue_id",
            ),
        )
        for field, values, duplicate_name in duplicate_cases:
            with self.subTest(field=field), self.assertRaisesRegex(
                OntologySpecValidationError, f"duplicate {duplicate_name}"
            ):
                spec_fixture(**{field: values})

    def test_rejects_casefold_duplicate_ids(self):
        duplicate_cases = (
            ("input_binding_ids", ("binding_same", "BINDING_SAME")),
            (
                "entity_types",
                (
                    entity_fixture(type_id="type_same", role_key="first"),
                    entity_fixture(type_id="TYPE_SAME", role_key="second"),
                ),
            ),
            (
                "relation_types",
                (
                    relation_fixture(relation_type_id="relation_same"),
                    relation_fixture(relation_type_id="RELATION_SAME"),
                ),
            ),
            (
                "property_types",
                (
                    property_fixture(property_type_id="property_same"),
                    property_fixture(property_type_id="PROPERTY_SAME"),
                ),
            ),
            (
                "rule_declarations",
                (
                    rule_fixture(rule_id="rule_same"),
                    rule_fixture(rule_id="RULE_SAME"),
                ),
            ),
            (
                "compilation_issues",
                (
                    issue_fixture(issue_id="issue_same"),
                    issue_fixture(issue_id="ISSUE_SAME"),
                ),
            ),
        )
        for field, values in duplicate_cases:
            with self.subTest(field=field), self.assertRaisesRegex(
                OntologySpecValidationError, "duplicate"
            ):
                spec_fixture(**{field: values})

    def test_collections_are_sorted_by_stable_id(self):
        spec = spec_fixture(
            input_binding_ids=("binding_z", "binding_a"),
            entity_types=(
                entity_fixture(type_id="type_z", role_key="z"),
                entity_fixture(type_id="type_a", role_key="a"),
            ),
            relation_types=(
                relation_fixture(relation_type_id="relation_z"),
                relation_fixture(relation_type_id="relation_a"),
            ),
            property_types=(
                property_fixture(property_type_id="property_z"),
                property_fixture(property_type_id="property_a"),
            ),
            rule_declarations=(
                rule_fixture(rule_id="rule_z"),
                rule_fixture(rule_id="rule_a"),
            ),
            compilation_issues=(
                issue_fixture(issue_id="issue_z"),
                issue_fixture(issue_id="issue_a"),
            ),
        )

        self.assertEqual(spec.input_binding_ids, ("binding_a", "binding_z"))
        self.assertEqual(
            tuple(item.type_id for item in spec.entity_types), ("type_a", "type_z")
        )
        self.assertEqual(
            tuple(item.relation_type_id for item in spec.relation_types),
            ("relation_a", "relation_z"),
        )
        self.assertEqual(
            tuple(item.property_type_id for item in spec.property_types),
            ("property_a", "property_z"),
        )
        self.assertEqual(
            tuple(item.rule_id for item in spec.rule_declarations),
            ("rule_a", "rule_z"),
        )
        self.assertEqual(
            tuple(item.issue_id for item in spec.compilation_issues),
            ("issue_a", "issue_z"),
        )

    def test_rule_condition_values_and_conditions_are_deterministic(self):
        first = RuleConditionSpec(
            property_type_id="property_z",
            operator="in",
            allowed_values=("z", "a"),
        )
        second = RuleConditionSpec(
            property_type_id="property_a",
            operator="equals",
            allowed_values=("ready",),
        )
        rule = RuleDeclarationSpec(
            **{
                **rule_fixture().__dict__,
                "conditions": (first, second),
            }
        )

        self.assertEqual(first.allowed_values, ("a", "z"))
        self.assertEqual(
            tuple(item.property_type_id for item in rule.conditions),
            ("property_a", "property_z"),
        )

    def test_rule_condition_requires_nonempty_typed_values(self):
        with self.assertRaisesRegex(
            OntologySpecValidationError, "allowed_values must not be empty"
        ):
            RuleConditionSpec(
                property_type_id="property_order_state",
                operator="in",
                allowed_values=(),
            )
        with self.assertRaisesRegex(OntologySpecValidationError, "allowed_values"):
            RuleConditionSpec(
                property_type_id="property_order_state",
                operator="in",
                allowed_values=(1,),
            )

    def test_rejects_normalized_duplicate_allowed_values_and_conditions(self):
        with self.assertRaisesRegex(
            OntologySpecValidationError, "duplicate allowed_value"
        ):
            RuleConditionSpec(
                property_type_id="property_order_state",
                operator="in",
                allowed_values=(" at_risk ", "AT_RISK"),
            )

        first = RuleConditionSpec(
            property_type_id="property_order_state",
            operator="in",
            allowed_values=("at_risk", "missed"),
        )
        duplicate = RuleConditionSpec(
            property_type_id="PROPERTY_ORDER_STATE",
            operator="IN",
            allowed_values=("MISSED", "AT_RISK"),
        )
        with self.assertRaisesRegex(
            OntologySpecValidationError, "duplicate condition"
        ):
            RuleDeclarationSpec(
                **{
                    **rule_fixture().__dict__,
                    "conditions": (first, duplicate),
                }
            )

    def test_canonical_hash_is_repeatable_and_order_independent(self):
        first = spec_fixture(
            input_binding_ids=("binding_z", "binding_a"),
            entity_types=(
                entity_fixture(type_id="type_z", role_key="z"),
                entity_fixture(type_id="type_a", role_key="a"),
            ),
            relation_types=(
                relation_fixture(relation_type_id="relation_z"),
                relation_fixture(relation_type_id="relation_a"),
            ),
            property_types=(
                property_fixture(property_type_id="property_z"),
                property_fixture(property_type_id="property_a"),
            ),
            rule_declarations=(
                rule_fixture(rule_id="rule_z"),
                rule_fixture(rule_id="rule_a"),
            ),
            compilation_issues=(
                issue_fixture(issue_id="issue_z"),
                issue_fixture(issue_id="issue_a"),
            ),
        )
        second = spec_fixture(
            input_binding_ids=tuple(reversed(first.input_binding_ids)),
            entity_types=tuple(reversed(first.entity_types)),
            relation_types=tuple(reversed(first.relation_types)),
            property_types=tuple(reversed(first.property_types)),
            rule_declarations=tuple(reversed(first.rule_declarations)),
            compilation_issues=tuple(reversed(first.compilation_issues)),
        )

        first_json = canonical_ontology_spec_json(first)
        self.assertEqual(first_json, canonical_ontology_spec_json(second))
        self.assertEqual(
            ontology_spec_content_hash(first),
            ontology_spec_content_hash(second),
        )
        self.assertEqual(json.loads(first_json), ontology_spec_to_dict(first))
        self.assertEqual(
            ontology_spec_content_hash(first),
            hashlib.sha256(first_json.encode("utf-8")).hexdigest(),
        )
        self.assertIn("客户订单", first_json)

    def test_canonical_projection_is_explicit_and_has_no_envelope_fields(self):
        payload = ontology_spec_to_dict(
            spec_fixture(entity_types=(entity_fixture(),))
        )

        self.assertEqual(
            tuple(payload),
            (
                "schema",
                "decision_key",
                "pack_content_hash",
                "stage",
                "evidence_scope",
                "governance_status",
                "input_binding_ids",
                "entity_types",
                "relation_types",
                "property_types",
                "rule_declarations",
                "compilation_issues",
            ),
        )
        forbidden = {
            "spec_content_hash",
            "version",
            "base",
            "review",
            "publication",
            "created_at",
            "updated_at",
        }
        self.assertTrue(forbidden.isdisjoint(payload))
        self.assertEqual(payload["stage"], "draft")
        self.assertEqual(
            payload["entity_types"][0]["origin_kind"], "provided_input"
        )

    def test_tuple_contract_prevents_raw_list_alias_mutation(self):
        raw_entities = [entity_fixture()]
        with self.assertRaisesRegex(
            OntologySpecValidationError, "entity_types must be a tuple"
        ):
            spec_fixture(entity_types=raw_entities)
        raw_entities.clear()

    def test_spec_compilation_error_preserves_machine_code(self):
        error = SpecCompilationError("invalid_pack", "Pack contract is broken.")

        self.assertEqual(error.code, "invalid_pack")
        self.assertEqual(str(error), "Pack contract is broken.")


if __name__ == "__main__":
    unittest.main()
