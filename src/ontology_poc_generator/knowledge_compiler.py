from __future__ import annotations

from dataclasses import dataclass

from ontology_poc_generator.decision_pack import DecisionPack, InputBinding
from ontology_poc_generator.errors import SpecCompilationError
from ontology_poc_generator.identity import (
    stable_compilation_issue_id,
    stable_relation_type_id,
)
from ontology_poc_generator.knowledge import (
    KnowledgeSuggestion,
    MatchStatus,
)
from ontology_poc_generator.ontology_spec import (
    CompilationIssue,
    CompilationIssueSeverity,
    EntityTypeSpec,
    PropertyTypeSpec,
    RelationTypeSpec,
    RuleDeclarationSpec,
    SpecGovernanceStatus,
    SpecOriginKind,
)


_NON_EXECUTABLE_PROFILES = {
    "constraint.narrative.v1": (
        "narrative_constraint_requires_formalization",
        "Narrative constraint requires formalization before execution.",
    ),
    "data_requirement.narrative.v1": (
        "data_requirement_not_executable",
        "Data requirement requires an explicit executable mapping.",
    ),
    "acceptance_question.v1": (
        "acceptance_question_not_executable",
        "Acceptance question remains review input and is not executable.",
    ),
    "readiness_gap.v1": (
        "readiness_gap_blocks_rule_compilation",
        "Readiness gap requires review before rule compilation.",
    ),
}


@dataclass(frozen=True)
class KnowledgeCompilation:
    relation_types: tuple[RelationTypeSpec, ...] = ()
    property_types: tuple[PropertyTypeSpec, ...] = ()
    rule_declarations: tuple[RuleDeclarationSpec, ...] = ()
    compilation_issues: tuple[CompilationIssue, ...] = ()

    def __post_init__(self) -> None:
        collections = (
            ("relation_types", RelationTypeSpec, "relation_type_id"),
            ("property_types", PropertyTypeSpec, "property_type_id"),
            ("rule_declarations", RuleDeclarationSpec, "rule_id"),
            ("compilation_issues", CompilationIssue, "issue_id"),
        )
        for field, item_type, identity_field in collections:
            items = getattr(self, field)
            if not isinstance(items, tuple) or any(
                not isinstance(item, item_type) for item in items
            ):
                raise TypeError(f"{field} must be a tuple of {item_type.__name__}")
            object.__setattr__(
                self,
                field,
                tuple(
                    sorted(
                        items,
                        key=lambda item: getattr(item, identity_field).casefold(),
                    )
                ),
            )


def compile_knowledge_profiles(
    pack: DecisionPack,
    entity_types: tuple[EntityTypeSpec, ...],
    existing_relation_types: tuple[RelationTypeSpec, ...] = (),
) -> KnowledgeCompilation:
    """Project recognized applicable knowledge profiles into draft spec objects."""
    bindings_by_role = {
        binding.role_key.casefold(): binding for binding in pack.input_bindings
    }
    entity_types_by_binding = {
        entity.origin_ref_id: entity for entity in entity_types
    }
    occupied_relation_ids = {
        relation.relation_type_id.casefold() for relation in existing_relation_types
    }
    relation_types: list[RelationTypeSpec] = []
    compilation_issues: list[CompilationIssue] = []

    for outcome in pack.knowledge_outcomes:
        if outcome.match_status is not MatchStatus.APPLICABLE:
            continue
        for suggestion in outcome.suggestions:
            if suggestion.payload_schema == "relation_semantics.v1":
                relation = _compile_relation(
                    suggestion,
                    bindings_by_role=bindings_by_role,
                    entity_types_by_binding=entity_types_by_binding,
                )
                relation_identity = relation.relation_type_id.casefold()
                if relation_identity in occupied_relation_ids:
                    raise SpecCompilationError(
                        "duplicate_relation_type_identity",
                        "Relation type identity is already occupied.",
                    )
                occupied_relation_ids.add(relation_identity)
                relation_types.append(relation)
            elif suggestion.payload_schema in _NON_EXECUTABLE_PROFILES:
                compilation_issues.append(_compile_issue(suggestion))

    return KnowledgeCompilation(
        relation_types=tuple(relation_types),
        compilation_issues=tuple(compilation_issues),
    )


def _compile_relation(
    suggestion: KnowledgeSuggestion,
    *,
    bindings_by_role: dict[str, InputBinding],
    entity_types_by_binding: dict[str, EntityTypeSpec],
) -> RelationTypeSpec:
    payload = dict(suggestion.payload)
    source_binding = bindings_by_role.get(payload["source_role_key"].casefold())
    target_binding = bindings_by_role.get(payload["target_role_key"].casefold())
    if source_binding is None or target_binding is None:
        raise SpecCompilationError(
            "missing_relation_role_binding",
            "Relation role cannot be resolved to an input binding.",
        )
    if (
        source_binding.binding_id not in suggestion.input_binding_ids
        or target_binding.binding_id not in suggestion.input_binding_ids
    ):
        raise SpecCompilationError(
            "relation_endpoint_binding_mismatch",
            "Relation endpoint is outside suggestion input provenance.",
        )
    source_entity = entity_types_by_binding.get(source_binding.binding_id)
    target_entity = entity_types_by_binding.get(target_binding.binding_id)
    if source_entity is None or target_entity is None:
        raise SpecCompilationError(
            "missing_relation_role_binding",
            "Relation binding cannot be resolved to an entity type.",
        )
    relation_type_id = stable_relation_type_id(
        suggestion.semantic_key,
        source_entity.type_id,
        payload["predicate"],
        target_entity.type_id,
    )
    return RelationTypeSpec(
        relation_type_id=relation_type_id,
        semantic_key=suggestion.semantic_key,
        predicate=payload["predicate"],
        domain_type_id=source_entity.type_id,
        range_type_id=target_entity.type_id,
        description=payload["description"],
        governance_status=SpecGovernanceStatus.CANDIDATE,
        origin_kind=SpecOriginKind.KNOWLEDGE_SUGGESTION,
        origin_ref_id=suggestion.suggestion_id,
    )


def _compile_issue(suggestion: KnowledgeSuggestion) -> CompilationIssue:
    code, message = _NON_EXECUTABLE_PROFILES[suggestion.payload_schema]
    return CompilationIssue(
        issue_id=stable_compilation_issue_id(
            suggestion.suggestion_id,
            code,
            suggestion.payload_schema,
        ),
        code=code,
        severity=CompilationIssueSeverity.REQUIRES_REVIEW,
        suggestion_id=suggestion.suggestion_id,
        payload_schema=suggestion.payload_schema,
        message=message,
    )
