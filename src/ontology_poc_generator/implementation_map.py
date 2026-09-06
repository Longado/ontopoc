from __future__ import annotations

from ontology_poc_generator.decision_pack import (
    DecisionPack,
    decision_pack_content_hash,
)
from ontology_poc_generator.errors import OntologySpecValidationError
from ontology_poc_generator.ontology_spec import (
    SpecCompilationResult,
    ontology_spec_content_hash,
)


_CLOSURE_VALIDATOR = (
    "ontology_poc_generator.validation:validate_reference_closure"
)
_RULE_RUNTIME = (
    "ontology_poc_generator.rule_runtime:evaluate_synthetic_rule"
)
_VALIDATION_RECEIPT = (
    "ontology_poc_generator.validation_receipt:ValidationReceipt"
)


def build_implementation_map(
    pack: DecisionPack,
    compilation: SpecCompilationResult,
) -> dict[str, object]:
    """Project compiled ontology elements to their current evidence and consumers."""
    if not isinstance(pack, DecisionPack):
        raise OntologySpecValidationError("pack must be a DecisionPack")
    if not isinstance(compilation, SpecCompilationResult):
        raise OntologySpecValidationError(
            "compilation must be a SpecCompilationResult"
        )

    pack_hash = decision_pack_content_hash(pack)
    if compilation.spec.pack_content_hash != pack_hash:
        raise OntologySpecValidationError(
            "spec pack_content_hash does not match DecisionPack"
        )

    suggestions = {
        suggestion.suggestion_id: suggestion
        for outcome in pack.knowledge_outcomes
        for suggestion in outcome.suggestions
    }

    def entry(
        element_kind: str,
        element_id: str,
        semantic_key: str,
        origin_ref_id: str,
        execution_state: str,
        implementation_refs: tuple[str, ...],
    ) -> dict[str, object]:
        suggestion = suggestions.get(origin_ref_id)
        return {
            "element_kind": element_kind,
            "element_id": element_id,
            "semantic_key": semantic_key,
            "origin_ref_id": origin_ref_id,
            "source_ref_ids": (
                sorted(suggestion.source_ref_ids, key=str.casefold)
                if suggestion is not None
                else []
            ),
            "execution_state": execution_state,
            "implementation_refs": list(implementation_refs),
        }

    entries = [
        *(
            entry(
                "entity_type",
                item.type_id,
                item.semantic_key,
                item.origin_ref_id,
                "declared_only",
                (_CLOSURE_VALIDATOR,),
            )
            for item in compilation.spec.entity_types
        ),
        *(
            entry(
                "relation_type",
                item.relation_type_id,
                item.semantic_key,
                item.origin_ref_id,
                "declared_only",
                (_CLOSURE_VALIDATOR,),
            )
            for item in compilation.spec.relation_types
        ),
        *(
            entry(
                "property_type",
                item.property_type_id,
                item.semantic_key,
                item.origin_ref_id,
                "runtime_input",
                (_CLOSURE_VALIDATOR, _RULE_RUNTIME),
            )
            for item in compilation.spec.property_types
        ),
        *(
            entry(
                "rule_declaration",
                item.rule_id,
                item.semantic_key,
                item.origin_suggestion_id,
                "runtime_executable",
                (_CLOSURE_VALIDATOR, _RULE_RUNTIME, _VALIDATION_RECEIPT),
            )
            for item in compilation.spec.rule_declarations
        ),
    ]
    entries.sort(
        key=lambda item: (
            str(item["element_kind"]).casefold(),
            str(item["element_id"]).casefold(),
        )
    )
    return {
        "schema": "implementation_map.v1",
        "decision_key": compilation.spec.decision_key,
        "decision_pack_content_hash": pack_hash,
        "ontology_spec_content_hash": ontology_spec_content_hash(
            compilation.spec
        ),
        "editable": False,
        "entries": entries,
    }
