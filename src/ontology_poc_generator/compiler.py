from __future__ import annotations

from ontology_poc_generator.decision_pack import DecisionPack, InputBinding
from ontology_poc_generator.errors import KnowledgeValidationError
from ontology_poc_generator.identity import stable_binding_id
from ontology_poc_generator.knowledge import (
    KnowledgeUnit,
    SourceRef,
    match_knowledge_unit,
)
from ontology_poc_generator.models import ScenarioParameters


def compile_decision_pack(
    params: ScenarioParameters,
    knowledge_units: tuple[KnowledgeUnit, ...] = (),
) -> DecisionPack:
    """Compile semantic input and explicitly supplied knowledge without side effects."""
    if not isinstance(params, ScenarioParameters):
        raise KnowledgeValidationError("params must be ScenarioParameters")
    if not isinstance(knowledge_units, tuple) or any(
        not isinstance(unit, KnowledgeUnit) for unit in knowledge_units
    ):
        raise KnowledgeValidationError("knowledge_units must be a tuple of KnowledgeUnit")

    unit_ids = tuple(unit.unit_id for unit in knowledge_units)
    if len(set(unit_ids)) != len(unit_ids):
        raise KnowledgeValidationError("duplicate knowledge unit_id")
    ordered_units = tuple(
        sorted(
            knowledge_units,
            key=lambda unit: (unit.unit_id, unit.unit_version, unit.unit_content_hash),
        )
    )

    input_bindings = tuple(
        InputBinding(
            binding_id=stable_binding_id(
                params.decision_key, item.role_key, item.semantic_key
            ),
            role_key=item.role_key,
            semantic_key=item.semantic_key,
            label=item.object_label,
        )
        for item in params.object_role_bindings
    )
    outcomes = tuple(match_knowledge_unit(params, unit) for unit in ordered_units)
    cited_source_ids = {
        source_ref_id
        for outcome in outcomes
        for suggestion in outcome.suggestions
        for source_ref_id in suggestion.source_ref_ids
    }

    sources_by_id: dict[str, SourceRef] = {}
    for unit in ordered_units:
        for source in unit.source_refs:
            if source.source_ref_id not in cited_source_ids:
                continue
            existing = sources_by_id.get(source.source_ref_id)
            if existing is not None and existing != source:
                raise KnowledgeValidationError(
                    f"source_ref_id {source.source_ref_id} has conflicting content"
                )
            sources_by_id[source.source_ref_id] = source

    unresolved = cited_source_ids - sources_by_id.keys()
    if unresolved:
        raise KnowledgeValidationError(
            f"suggestion references unavailable source_ref_id: {sorted(unresolved)[0]}"
        )

    return DecisionPack(
        schema="decision_pack.v1",
        scenario=params,
        input_bindings=input_bindings,
        source_refs=tuple(sources_by_id.values()),
        knowledge_outcomes=outcomes,
    )
