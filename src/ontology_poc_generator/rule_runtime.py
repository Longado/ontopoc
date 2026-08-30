from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from ontology_poc_generator.decision_pack import (
    DecisionPack,
    decision_pack_content_hash,
)
from ontology_poc_generator.ontology_spec import SpecCompilationResult
from ontology_poc_generator.validation_receipt import (
    DecisionResult,
    EvaluationStatus,
    ValidationReceipt,
)


class RuleEvaluationError(ValueError):
    """Synthetic facts or a compiled rule cannot form a bounded receipt."""


class FactAvailability(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuleEvaluationError(f"{field} is required")
    return value.strip()


def _references(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise RuleEvaluationError(f"{field} must be a non-empty tuple")
    normalized = tuple(
        _text(item, f"{field}[{index}]")
        for index, item in enumerate(value)
    )
    normalized_keys = tuple(item.casefold() for item in normalized)
    if len(set(normalized_keys)) != len(normalized_keys):
        raise RuleEvaluationError(f"{field} must not contain duplicates")
    return tuple(sorted(normalized, key=lambda item: (item.casefold(), item)))


@dataclass(frozen=True)
class SyntheticFact:
    fact_ref: str
    property_type_id: str
    availability: FactAvailability
    value: str | None
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fact_ref", _text(self.fact_ref, "fact_ref"))
        object.__setattr__(
            self,
            "property_type_id",
            _text(self.property_type_id, "property_type_id"),
        )
        if not isinstance(self.availability, FactAvailability):
            raise RuleEvaluationError("availability must be FactAvailability")
        if self.availability is FactAvailability.AVAILABLE:
            object.__setattr__(self, "value", _text(self.value, "value"))
        elif self.value is not None:
            raise RuleEvaluationError("value must be absent when fact is unavailable")
        object.__setattr__(
            self,
            "evidence_refs",
            _references(self.evidence_refs, "evidence_refs"),
        )


@dataclass(frozen=True)
class SyntheticFactSet:
    schema: str
    evidence_scope: str
    subject_id: str
    facts: tuple[SyntheticFact, ...]

    def __post_init__(self) -> None:
        if self.schema != "synthetic_fact_set.v1":
            raise RuleEvaluationError("schema must be synthetic_fact_set.v1")
        if self.evidence_scope != "synthetic_demo":
            raise RuleEvaluationError("evidence_scope must be synthetic_demo")
        object.__setattr__(self, "subject_id", _text(self.subject_id, "subject_id"))
        if not isinstance(self.facts, tuple) or not self.facts:
            raise RuleEvaluationError("facts must be a non-empty tuple")
        if any(not isinstance(item, SyntheticFact) for item in self.facts):
            raise RuleEvaluationError("facts must contain only SyntheticFact")
        fact_refs = tuple(item.fact_ref.casefold() for item in self.facts)
        property_ids = tuple(item.property_type_id.casefold() for item in self.facts)
        if len(set(fact_refs)) != len(fact_refs):
            raise RuleEvaluationError("facts must not repeat fact_ref")
        if len(set(property_ids)) != len(property_ids):
            raise RuleEvaluationError("facts must not repeat property_type_id")
        object.__setattr__(
            self,
            "facts",
            tuple(sorted(self.facts, key=lambda item: item.property_type_id.casefold())),
        )


def synthetic_fact_set_to_dict(facts: SyntheticFactSet) -> dict[str, object]:
    if not isinstance(facts, SyntheticFactSet):
        raise RuleEvaluationError("facts must be a SyntheticFactSet")
    return {
        "schema": facts.schema,
        "evidence_scope": facts.evidence_scope,
        "subject_id": facts.subject_id,
        "facts": [
            {
                "fact_ref": item.fact_ref,
                "property_type_id": item.property_type_id,
                "availability": item.availability.value,
                "value": item.value,
                "evidence_refs": list(item.evidence_refs),
            }
            for item in facts.facts
        ],
    }


def canonical_synthetic_fact_set_json(facts: SyntheticFactSet) -> str:
    return json.dumps(
        synthetic_fact_set_to_dict(facts),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def synthetic_fact_set_content_hash(facts: SyntheticFactSet) -> str:
    canonical = canonical_synthetic_fact_set_json(facts).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _rule_source_refs(pack: DecisionPack, suggestion_id: str) -> tuple[str, ...]:
    matches = [
        suggestion
        for outcome in pack.knowledge_outcomes
        for suggestion in outcome.suggestions
        if suggestion.suggestion_id == suggestion_id
    ]
    if len(matches) != 1:
        raise RuleEvaluationError(
            "rule origin_suggestion_id must resolve exactly once in DecisionPack"
        )
    return matches[0].source_ref_ids


def evaluate_synthetic_rule(
    pack: DecisionPack,
    compilation: SpecCompilationResult,
    facts: SyntheticFactSet,
    rule_id: str,
) -> ValidationReceipt:
    if not isinstance(pack, DecisionPack):
        raise RuleEvaluationError("pack must be a DecisionPack")
    if not isinstance(compilation, SpecCompilationResult):
        raise RuleEvaluationError("compilation must be a SpecCompilationResult")
    if not isinstance(facts, SyntheticFactSet):
        raise RuleEvaluationError("facts must be a SyntheticFactSet")
    normalized_rule_id = _text(rule_id, "rule_id")

    pack_hash = decision_pack_content_hash(pack)
    if compilation.spec.pack_content_hash != pack_hash:
        raise RuleEvaluationError("spec pack_content_hash does not match DecisionPack")

    rules = [
        item
        for item in compilation.spec.rule_declarations
        if item.rule_id == normalized_rule_id
    ]
    if len(rules) != 1:
        raise RuleEvaluationError("rule_id must resolve exactly once")
    rule = rules[0]

    facts_by_property = {item.property_type_id: item for item in facts.facts}
    condition_facts: list[SyntheticFact | None] = []
    for condition in rule.conditions:
        fact = facts_by_property.get(condition.property_type_id)
        condition_facts.append(fact)

    source_refs = _rule_source_refs(pack, rule.origin_suggestion_id)
    evidence_refs = tuple(
        sorted(
            {
                *source_refs,
                *(
                    evidence_ref
                    for fact in condition_facts
                    if fact is not None
                    for evidence_ref in fact.evidence_refs
                ),
            },
            key=str.casefold,
        )
    )

    if rule.rule_kind != "categorical_all_of_v1" or any(
        condition.operator != "in" for condition in rule.conditions
    ):
        status = EvaluationStatus.UNSUPPORTED
        result = DecisionResult.UNSUPPORTED
    elif any(
        fact is None or fact.availability is FactAvailability.UNAVAILABLE
        for fact in condition_facts
    ):
        status = EvaluationStatus.NOT_EVALUABLE
        result = DecisionResult.INFORMATION_INSUFFICIENT
    elif all(
        fact is not None and fact.value in condition.allowed_values
        for condition, fact in zip(rule.conditions, condition_facts, strict=True)
    ):
        status = EvaluationStatus.PASS
        result = DecisionResult.IN_QUEUE
    else:
        status = EvaluationStatus.FAIL
        result = DecisionResult.NOT_IN_QUEUE

    return ValidationReceipt(
        schema="validation_receipt.v1",
        decision_pack_content_hash=pack_hash,
        ontology_spec_content_hash=compilation.spec_content_hash,
        facts_content_hash=synthetic_fact_set_content_hash(facts),
        rule_id=rule.rule_id,
        evaluation_status=status,
        decision_result=result,
        fact_refs=tuple(
            fact.fact_ref
            if fact is not None
            else f"missing:{facts.subject_id}:{condition.property_type_id}"
            for condition, fact in zip(
                rule.conditions,
                condition_facts,
                strict=True,
            )
        ),
        evidence_refs=evidence_refs,
        draft_created=False,
        published=False,
        actions_executed=False,
        external_write=False,
    )
