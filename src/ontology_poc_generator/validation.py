from __future__ import annotations

from types import MappingProxyType

from ontology_poc_generator.decision_pack import (
    DecisionPack,
    decision_pack_content_hash,
)
from ontology_poc_generator.errors import OntologySpecValidationError
from ontology_poc_generator.identity import stable_closure_issue_id
from ontology_poc_generator.ontology_spec import (
    ClosureIssue,
    EntityTypeSpec,
    OntologySpec,
    PropertyTypeSpec,
    ReferenceClosureReport,
    RelationTypeSpec,
    SpecOriginKind,
)


ORIGIN_MATRIX = MappingProxyType(
    {
        EntityTypeSpec: frozenset((SpecOriginKind.PROVIDED_INPUT,)),
        RelationTypeSpec: frozenset(
            (
                SpecOriginKind.PROVIDED_INPUT,
                SpecOriginKind.KNOWLEDGE_SUGGESTION,
            )
        ),
        PropertyTypeSpec: frozenset((SpecOriginKind.KNOWLEDGE_SUGGESTION,)),
    }
)

SUGGESTION_PROFILE_MATRIX = MappingProxyType(
    {
        RelationTypeSpec: frozenset(("relation_semantics.v1",)),
        PropertyTypeSpec: frozenset(("decision_rule.v1",)),
    }
)


class _ClosureCollector:
    def __init__(self) -> None:
        self.checked_reference_count = 0
        self._issues: dict[str, ClosureIssue] = {}

    def checked(self) -> None:
        self.checked_reference_count += 1

    def issue(
        self,
        code: str,
        owner_id: str,
        field: str,
        referenced_id: str,
    ) -> None:
        issue_id = stable_closure_issue_id(
            code,
            owner_id,
            field,
            referenced_id,
        )
        self._issues.setdefault(
            issue_id,
            ClosureIssue(
                issue_id=issue_id,
                code=code,
                owner_id=owner_id,
                field=field,
                referenced_id=referenced_id,
            ),
        )

    def report(self) -> ReferenceClosureReport:
        return ReferenceClosureReport(
            checked_reference_count=self.checked_reference_count,
            issues=tuple(self._issues.values()),
        )


def _check_internal_references(
    spec: OntologySpec,
    collector: _ClosureCollector,
) -> None:
    entities = {item.type_id: item for item in spec.entity_types}
    properties = {item.property_type_id: item for item in spec.property_types}
    property_domains_are_valid: dict[str, bool] = {}

    for relation in spec.relation_types:
        for field, referenced_id, code in (
            (
                "domain_type_id",
                relation.domain_type_id,
                "dangling_relation_domain",
            ),
            (
                "range_type_id",
                relation.range_type_id,
                "dangling_relation_range",
            ),
        ):
            collector.checked()
            if referenced_id not in entities:
                collector.issue(
                    code,
                    relation.relation_type_id,
                    field,
                    referenced_id,
                )

    for property_type in spec.property_types:
        collector.checked()
        domain_is_valid = property_type.domain_type_id in entities
        property_domains_are_valid[property_type.property_type_id] = domain_is_valid
        if not domain_is_valid:
            collector.issue(
                "dangling_property_domain",
                property_type.property_type_id,
                "domain_type_id",
                property_type.domain_type_id,
            )

    for rule in spec.rule_declarations:
        collector.checked()
        subject_is_valid = rule.subject_type_id in entities
        if not subject_is_valid:
            collector.issue(
                "dangling_rule_subject_type",
                rule.rule_id,
                "subject_type_id",
                rule.subject_type_id,
            )
        for condition in rule.conditions:
            collector.checked()
            property_type = properties.get(condition.property_type_id)
            if property_type is None:
                collector.issue(
                    "dangling_rule_property",
                    rule.rule_id,
                    "conditions.property_type_id",
                    condition.property_type_id,
                )
                continue
            if (
                subject_is_valid
                and property_domains_are_valid[property_type.property_type_id]
                and property_type.domain_type_id != rule.subject_type_id
            ):
                collector.issue(
                    "rule_property_domain_mismatch",
                    rule.rule_id,
                    "conditions.property_type_id",
                    condition.property_type_id,
                )


def _check_element_origin_contract(
    element: EntityTypeSpec | RelationTypeSpec | PropertyTypeSpec,
    owner_id: str,
    collector: _ClosureCollector,
) -> bool:
    collector.checked()
    if element.origin_kind not in ORIGIN_MATRIX[type(element)]:
        collector.issue(
            "unsupported_origin_contract",
            owner_id,
            "origin_kind",
            element.origin_kind.value,
        )
        return False
    return True


def _check_pack_relative_references(
    spec: OntologySpec,
    pack: DecisionPack,
    collector: _ClosureCollector,
) -> None:
    bindings = {item.binding_id: item for item in pack.input_bindings}
    bridges = {
        item.semantic_key: item for item in pack.scenario.declared_bridges
    }
    suggestions = {
        suggestion.suggestion_id: suggestion
        for outcome in pack.knowledge_outcomes
        for suggestion in outcome.suggestions
    }
    entities = {item.type_id: item for item in spec.entity_types}
    element_consumption: set[str] = set()
    issue_consumption: set[str] = set()

    collector.checked()
    expected_binding_ids = frozenset(bindings)
    actual_binding_ids = frozenset(spec.input_binding_ids)
    if actual_binding_ids != expected_binding_ids:
        collector.issue(
            "input_binding_set_mismatch",
            "ontology_spec",
            "input_binding_ids",
            (
                f"expected={','.join(sorted(expected_binding_ids))};"
                f"actual={','.join(sorted(actual_binding_ids))}"
            ),
        )

    for entity in spec.entity_types:
        if not _check_element_origin_contract(
            entity,
            entity.type_id,
            collector,
        ):
            continue
        binding = bindings.get(entity.origin_ref_id)
        if binding is None:
            collector.issue(
                "dangling_input_binding",
                entity.type_id,
                "origin_ref_id",
                entity.origin_ref_id,
            )
            continue
        if (
            entity.role_key != binding.role_key
            or entity.semantic_key != binding.semantic_key
        ):
            collector.issue(
                "origin_profile_mismatch",
                entity.type_id,
                "origin_ref_id",
                entity.origin_ref_id,
            )

    for relation in spec.relation_types:
        if not _check_element_origin_contract(
            relation,
            relation.relation_type_id,
            collector,
        ):
            continue
        if relation.origin_kind is SpecOriginKind.PROVIDED_INPUT:
            bridge = bridges.get(relation.origin_ref_id)
            if bridge is None:
                collector.issue(
                    "dangling_declared_bridge",
                    relation.relation_type_id,
                    "origin_ref_id",
                    relation.origin_ref_id,
                )
                continue
            domain = entities.get(relation.domain_type_id)
            range_ = entities.get(relation.range_type_id)
            if domain is None or range_ is None:
                continue
            if (
                relation.semantic_key != bridge.semantic_key
                or relation.predicate != bridge.predicate
                or domain.role_key != bridge.source_role_key
                or range_.role_key != bridge.target_role_key
            ):
                collector.issue(
                    "origin_profile_mismatch",
                    relation.relation_type_id,
                    "origin_ref_id",
                    relation.origin_ref_id,
                )
            continue

        suggestion = suggestions.get(relation.origin_ref_id)
        if suggestion is None:
            collector.issue(
                "dangling_suggestion_reference",
                relation.relation_type_id,
                "origin_ref_id",
                relation.origin_ref_id,
            )
            continue
        element_consumption.add(suggestion.suggestion_id)
        domain = entities.get(relation.domain_type_id)
        range_ = entities.get(relation.range_type_id)
        payload = dict(suggestion.payload)
        if (
            suggestion.payload_schema
            not in SUGGESTION_PROFILE_MATRIX[RelationTypeSpec]
            or relation.semantic_key != suggestion.semantic_key
            or payload.get("predicate") != relation.predicate
            or (
                domain is not None
                and payload.get("source_role_key") != domain.role_key
            )
            or (
                range_ is not None
                and payload.get("target_role_key") != range_.role_key
            )
        ):
            collector.issue(
                "origin_profile_mismatch",
                relation.relation_type_id,
                "origin_ref_id",
                relation.origin_ref_id,
            )

    for property_type in spec.property_types:
        if not _check_element_origin_contract(
            property_type,
            property_type.property_type_id,
            collector,
        ):
            continue
        suggestion = suggestions.get(property_type.origin_ref_id)
        if suggestion is None:
            collector.issue(
                "dangling_suggestion_reference",
                property_type.property_type_id,
                "origin_ref_id",
                property_type.origin_ref_id,
            )
            continue
        element_consumption.add(suggestion.suggestion_id)
        if (
            suggestion.payload_schema
            not in SUGGESTION_PROFILE_MATRIX[PropertyTypeSpec]
        ):
            collector.issue(
                "origin_profile_mismatch",
                property_type.property_type_id,
                "origin_ref_id",
                property_type.origin_ref_id,
            )

    for rule in spec.rule_declarations:
        collector.checked()
        suggestion = suggestions.get(rule.origin_suggestion_id)
        if suggestion is None:
            collector.issue(
                "dangling_suggestion_reference",
                rule.rule_id,
                "origin_suggestion_id",
                rule.origin_suggestion_id,
            )
            continue
        element_consumption.add(suggestion.suggestion_id)
        if (
            suggestion.payload_schema != "decision_rule.v1"
            or rule.semantic_key != suggestion.semantic_key
        ):
            collector.issue(
                "origin_profile_mismatch",
                rule.rule_id,
                "origin_suggestion_id",
                rule.origin_suggestion_id,
            )

    for issue in spec.compilation_issues:
        collector.checked()
        suggestion = suggestions.get(issue.suggestion_id)
        if suggestion is None:
            collector.issue(
                "dangling_suggestion_reference",
                issue.issue_id,
                "suggestion_id",
                issue.suggestion_id,
            )
            continue
        issue_consumption.add(suggestion.suggestion_id)
        if issue.payload_schema != suggestion.payload_schema:
            collector.issue(
                "origin_profile_mismatch",
                issue.issue_id,
                "payload_schema",
                issue.suggestion_id,
            )

    for suggestion_id in sorted(suggestions):
        collector.checked()
        consumed_as_element = suggestion_id in element_consumption
        consumed_as_issue = suggestion_id in issue_consumption
        if consumed_as_element and consumed_as_issue:
            collector.issue(
                "duplicate_suggestion_consumption",
                suggestion_id,
                "disposition",
                suggestion_id,
            )
        elif not consumed_as_element and not consumed_as_issue:
            collector.issue(
                "unaccounted_suggestion",
                suggestion_id,
                "disposition",
                suggestion_id,
            )


def validate_reference_closure(
    spec: OntologySpec,
    pack: DecisionPack,
) -> ReferenceClosureReport:
    """Collect every trustworthy closure failure without repairing references."""
    if not isinstance(spec, OntologySpec):
        raise OntologySpecValidationError("spec must be an OntologySpec")
    if not isinstance(pack, DecisionPack):
        raise OntologySpecValidationError("pack must be a DecisionPack")

    collector = _ClosureCollector()
    collector.checked()
    pack_hash_matches = spec.pack_content_hash == decision_pack_content_hash(pack)
    if not pack_hash_matches:
        collector.issue(
            "pack_content_hash_mismatch",
            "ontology_spec",
            "pack_content_hash",
            spec.pack_content_hash,
        )

    collector.checked()
    decision_key_matches = spec.decision_key == pack.scenario.decision_key
    if not decision_key_matches:
        collector.issue(
            "decision_key_mismatch",
            "ontology_spec",
            "decision_key",
            spec.decision_key,
        )

    _check_internal_references(spec, collector)
    if pack_hash_matches and decision_key_matches:
        _check_pack_relative_references(spec, pack, collector)
    return collector.report()
