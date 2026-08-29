from __future__ import annotations

from ontology_poc_generator.decision_pack import DecisionPack
from ontology_poc_generator.knowledge_compiler import compile_knowledge_profiles
from ontology_poc_generator.ontology_spec import OntologySpec, SpecCompilationResult
from ontology_poc_generator.provided_compiler import compile_provided_spec
from ontology_poc_generator.validation import validate_reference_closure


def compile_ontology_spec(pack: DecisionPack) -> SpecCompilationResult:
    """Assemble provided inputs and applicable knowledge into a closed draft spec."""
    provided = compile_provided_spec(pack)
    knowledge = compile_knowledge_profiles(
        pack,
        provided.entity_types,
        existing_relation_types=provided.relation_types,
    )
    spec = OntologySpec(
        schema=provided.schema,
        decision_key=provided.decision_key,
        pack_content_hash=provided.pack_content_hash,
        stage=provided.stage,
        evidence_scope=provided.evidence_scope,
        governance_status=provided.governance_status,
        input_binding_ids=provided.input_binding_ids,
        entity_types=provided.entity_types,
        relation_types=provided.relation_types + knowledge.relation_types,
        property_types=knowledge.property_types,
        rule_declarations=knowledge.rule_declarations,
        compilation_issues=knowledge.compilation_issues,
    )
    closure_report = validate_reference_closure(spec, pack)
    return SpecCompilationResult(spec=spec, closure_report=closure_report)
