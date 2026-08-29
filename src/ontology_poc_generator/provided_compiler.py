from __future__ import annotations

from ontology_poc_generator.decision_pack import (
    DecisionPack,
    decision_pack_content_hash,
)
from ontology_poc_generator.errors import SpecCompilationError
from ontology_poc_generator.identity import (
    stable_entity_type_id,
    stable_relation_type_id,
)
from ontology_poc_generator.ontology_spec import (
    EntityTypeSpec,
    EvidenceScope,
    OntologySpec,
    RelationTypeSpec,
    SpecGovernanceStatus,
    SpecOriginKind,
    SpecStage,
)


def compile_provided_spec(pack: DecisionPack) -> OntologySpec:
    """Compile only explicit input bindings and declared bridges."""
    decision_key = pack.scenario.decision_key
    if not decision_key:
        raise SpecCompilationError(
            "missing_decision_key",
            "decision_key is required to compile provided ontology inputs",
        )

    entity_types = tuple(
        EntityTypeSpec(
            type_id=stable_entity_type_id(
                decision_key,
                binding.role_key,
                binding.semantic_key,
            ),
            role_key=binding.role_key,
            semantic_key=binding.semantic_key,
            label=binding.label,
            governance_status=SpecGovernanceStatus.CANDIDATE,
            origin_kind=SpecOriginKind.PROVIDED_INPUT,
            origin_ref_id=binding.binding_id,
        )
        for binding in pack.input_bindings
    )
    entity_by_role = {item.role_key: item for item in entity_types}

    relation_types: list[RelationTypeSpec] = []
    for bridge in pack.scenario.declared_bridges:
        domain = entity_by_role.get(bridge.source_role_key)
        range_ = entity_by_role.get(bridge.target_role_key)
        if domain is None or range_ is None:
            raise SpecCompilationError(
                "missing_relation_role_binding",
                f"declared bridge {bridge.semantic_key} references an unbound role",
            )
        relation_types.append(
            RelationTypeSpec(
                relation_type_id=stable_relation_type_id(
                    bridge.semantic_key,
                    domain.type_id,
                    bridge.predicate,
                    range_.type_id,
                ),
                semantic_key=bridge.semantic_key,
                predicate=bridge.predicate,
                domain_type_id=domain.type_id,
                range_type_id=range_.type_id,
                description=(
                    f"{bridge.source_role_key} "
                    f"{bridge.predicate} {bridge.target_role_key}"
                ),
                governance_status=SpecGovernanceStatus.CANDIDATE,
                origin_kind=SpecOriginKind.PROVIDED_INPUT,
                origin_ref_id=bridge.semantic_key,
            )
        )

    return OntologySpec(
        schema="ontology_spec.v1",
        decision_key=decision_key,
        pack_content_hash=decision_pack_content_hash(pack),
        stage=SpecStage.DRAFT,
        evidence_scope=EvidenceScope.SYNTHETIC_DEMO,
        governance_status=SpecGovernanceStatus.CANDIDATE,
        input_binding_ids=tuple(item.binding_id for item in pack.input_bindings),
        entity_types=entity_types,
        relation_types=tuple(relation_types),
        property_types=(),
        rule_declarations=(),
        compilation_issues=(),
    )
