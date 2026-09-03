from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class InvestigationScopeError(ValueError):
    """A source snapshot cannot support a bounded investigation comparison."""


class InvestigationFactorStatus(str, Enum):
    PRIORITY = "priority"
    WEAKENED = "weakened"


class ControlScopeStatus(str, Enum):
    CONFIRMED_IMPACT = "confirmed_impact"
    POSSIBLE_IMPACT = "possible_impact"
    EXCLUDED = "excluded"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True)
class InvestigationFactor:
    status: InvestigationFactorStatus
    predicate: str
    factor_id: str
    abnormal_subject_ids: tuple[str, ...]
    normal_subject_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    counterevidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class InvestigationGap:
    subject_id: str
    predicate: str
    source_system: str
    evidence_ref: str


@dataclass(frozen=True)
class InvestigationScopeResult:
    schema: str
    quality_signal_id: str
    factors: tuple[InvestigationFactor, ...]
    gaps: tuple[InvestigationGap, ...]
    root_cause_confirmed: bool


@dataclass(frozen=True)
class ControlScopeObject:
    object_id: str
    object_type: str
    status: ControlScopeStatus
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ControlScopeResult:
    schema: str
    quality_signal_id: str
    objects: tuple[ControlScopeObject, ...]
    root_cause_confirmed: bool


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvestigationScopeError(f"{field} is required")
    return value.strip()


def _normalized_records(source_snapshot: object) -> tuple[dict[str, object], ...]:
    if not isinstance(source_snapshot, Mapping):
        raise InvestigationScopeError("source_snapshot must be a mapping")
    if source_snapshot.get("schema") != "quality_source_snapshot.v1":
        raise InvestigationScopeError("schema must be quality_source_snapshot.v1")
    if source_snapshot.get("evidence_scope") != "synthetic_demo":
        raise InvestigationScopeError("evidence_scope must be synthetic_demo")

    raw_records = source_snapshot.get("records")
    if not isinstance(raw_records, list) or not raw_records:
        raise InvestigationScopeError("records must be a non-empty list")

    records: list[dict[str, object]] = []
    record_ids: set[str] = set()
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, Mapping):
            raise InvestigationScopeError(f"records[{index}] must be a mapping")
        record = {
            field: _required_text(raw.get(field), f"records[{index}].{field}")
            for field in (
                "source_system",
                "source_record_id",
                "observed_at",
                "subject_id",
                "predicate",
                "evidence_ref",
            )
        }
        record_key = str(record["source_record_id"]).casefold()
        if record_key in record_ids:
            raise InvestigationScopeError("source_record_id must be unique")
        record_ids.add(record_key)

        availability = raw.get("availability")
        if availability not in ("available", "missing"):
            raise InvestigationScopeError(
                f"records[{index}].availability must be available or missing"
            )
        object_id = raw.get("object_id")
        if availability == "available":
            object_id = _required_text(object_id, f"records[{index}].object_id")
        elif object_id is not None:
            raise InvestigationScopeError(
                f"records[{index}].object_id must be null when availability is missing"
            )
        record["availability"] = availability
        record["object_id"] = object_id
        records.append(record)

    return tuple(
        sorted(
            records,
            key=lambda item: str(item["source_record_id"]).casefold(),
        )
    )


def _factor_predicates(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise InvestigationScopeError("factor_predicates must be a non-empty tuple")
    predicates = tuple(
        _required_text(item, f"factor_predicates[{index}]")
        for index, item in enumerate(value)
    )
    if len({item.casefold() for item in predicates}) != len(predicates):
        raise InvestigationScopeError("factor_predicates must not contain duplicates")
    return tuple(sorted(predicates, key=str.casefold))


def evaluate_investigation_scope(
    source_snapshot: object,
    quality_signal_id: str,
    factor_predicates: tuple[str, ...],
) -> InvestigationScopeResult:
    """Compare explicit abnormal subjects with normal controls without claiming root cause."""
    records = _normalized_records(source_snapshot)
    normalized_signal_id = _required_text(quality_signal_id, "quality_signal_id")
    if not isinstance(source_snapshot, Mapping):
        raise InvestigationScopeError("source_snapshot must be a mapping")
    if source_snapshot.get("quality_signal_id") != normalized_signal_id:
        raise InvestigationScopeError(
            "quality_signal_id does not match source snapshot"
        )
    predicates = _factor_predicates(factor_predicates)

    available = tuple(
        record for record in records if record["availability"] == "available"
    )
    identified_subjects = {
        str(record["object_id"])
        for record in available
        if record["subject_id"] == normalized_signal_id
        and record["predicate"] == "IDENTIFIES"
    }
    if not identified_subjects:
        raise InvestigationScopeError(
            "quality signal must identify at least one abnormal subject"
        )

    outcomes: dict[str, str] = {}
    for record in available:
        if record["predicate"] != "HAS_INSPECTION_OUTCOME":
            continue
        subject_id = str(record["subject_id"])
        outcome = str(record["object_id"])
        previous = outcomes.get(subject_id)
        if previous is not None and previous != outcome:
            raise InvestigationScopeError(
                f"subject {subject_id} has conflicting inspection outcomes"
            )
        outcomes[subject_id] = outcome

    if any(outcomes.get(subject_id) != "abnormal" for subject_id in identified_subjects):
        raise InvestigationScopeError(
            "every subject identified by the quality signal must be abnormal"
        )
    normal_subjects = {
        subject_id for subject_id, outcome in outcomes.items() if outcome == "normal"
    }
    if not normal_subjects:
        raise InvestigationScopeError("at least one normal control is required")

    factors: list[InvestigationFactor] = []
    for predicate in predicates:
        abnormal_records = tuple(
            record
            for record in available
            if record["subject_id"] in identified_subjects
            and record["predicate"] == predicate
        )
        factor_ids = sorted(
            {str(record["object_id"]) for record in abnormal_records},
            key=str.casefold,
        )
        for factor_id in factor_ids:
            evidence = tuple(
                record
                for record in abnormal_records
                if record["object_id"] == factor_id
            )
            counterevidence = tuple(
                record
                for record in available
                if record["subject_id"] in normal_subjects
                and record["predicate"] == predicate
                and record["object_id"] == factor_id
            )
            factors.append(
                InvestigationFactor(
                    status=(
                        InvestigationFactorStatus.WEAKENED
                        if counterevidence
                        else InvestigationFactorStatus.PRIORITY
                    ),
                    predicate=predicate,
                    factor_id=factor_id,
                    abnormal_subject_ids=tuple(
                        sorted(
                            {str(record["subject_id"]) for record in evidence},
                            key=str.casefold,
                        )
                    ),
                    normal_subject_ids=tuple(
                        sorted(
                            {
                                str(record["subject_id"])
                                for record in counterevidence
                            },
                            key=str.casefold,
                        )
                    ),
                    evidence_refs=tuple(
                        sorted(
                            {str(record["evidence_ref"]) for record in evidence},
                            key=str.casefold,
                        )
                    ),
                    counterevidence_refs=tuple(
                        sorted(
                            {
                                str(record["evidence_ref"])
                                for record in counterevidence
                            },
                            key=str.casefold,
                        )
                    ),
                )
            )

    status_rank = {
        InvestigationFactorStatus.PRIORITY: 0,
        InvestigationFactorStatus.WEAKENED: 1,
    }
    ordered_factors = tuple(
        sorted(
            factors,
            key=lambda item: (
                status_rank[item.status],
                item.predicate.casefold(),
                item.factor_id.casefold(),
            ),
        )
    )
    gaps = tuple(
        sorted(
            (
                InvestigationGap(
                    subject_id=str(record["subject_id"]),
                    predicate=str(record["predicate"]),
                    source_system=str(record["source_system"]),
                    evidence_ref=str(record["evidence_ref"]),
                )
                for record in records
                if record["availability"] == "missing"
                and record["subject_id"] in identified_subjects
            ),
            key=lambda item: (
                item.subject_id.casefold(),
                item.predicate.casefold(),
                item.evidence_ref.casefold(),
            ),
        )
    )

    return InvestigationScopeResult(
        schema="investigation_scope.v1",
        quality_signal_id=normalized_signal_id,
        factors=ordered_factors,
        gaps=gaps,
        root_cause_confirmed=False,
    )


def evaluate_control_scope(
    source_snapshot: object,
    quality_signal_id: str,
) -> ControlScopeResult:
    """Derive a temporary-control scope from explicit batch and version links."""
    records = _normalized_records(source_snapshot)
    normalized_signal_id = _required_text(quality_signal_id, "quality_signal_id")
    if not isinstance(source_snapshot, Mapping):
        raise InvestigationScopeError("source_snapshot must be a mapping")
    if source_snapshot.get("quality_signal_id") != normalized_signal_id:
        raise InvestigationScopeError(
            "quality_signal_id does not match source snapshot"
        )
    available = tuple(
        record for record in records if record["availability"] == "available"
    )
    identified_records = tuple(
        record
        for record in available
        if record["subject_id"] == normalized_signal_id
        and record["predicate"] == "IDENTIFIES"
    )
    abnormal_subjects = {
        str(record["object_id"])
        for record in identified_records
    }
    if not abnormal_subjects:
        raise InvestigationScopeError(
            "quality signal must identify at least one abnormal subject"
        )

    outcomes: dict[str, str] = {}
    for record in available:
        if record["predicate"] != "HAS_INSPECTION_OUTCOME":
            continue
        subject_id = str(record["subject_id"])
        outcome = str(record["object_id"])
        previous = outcomes.get(subject_id)
        if previous is not None and previous != outcome:
            raise InvestigationScopeError(
                f"subject {subject_id} has conflicting inspection outcomes"
            )
        outcomes[subject_id] = outcome
    if any(outcomes.get(subject_id) != "abnormal" for subject_id in abnormal_subjects):
        raise InvestigationScopeError(
            "every identified subject must have one explicit abnormal outcome"
        )
    abnormal_outcome_records = tuple(
        record
        for record in available
        if record["predicate"] == "HAS_INSPECTION_OUTCOME"
        and record["subject_id"] in abnormal_subjects
        and record["object_id"] == "abnormal"
    )
    scope_root_evidence = {
        str(record["evidence_ref"])
        for record in (*identified_records, *abnormal_outcome_records)
    }

    def matching(
        *,
        subjects: set[str] | None = None,
        predicate: str | None = None,
        object_ids: set[str] | None = None,
    ) -> tuple[dict[str, object], ...]:
        return tuple(
            record
            for record in available
            if (subjects is None or str(record["subject_id"]) in subjects)
            and (predicate is None or record["predicate"] == predicate)
            and (object_ids is None or str(record["object_id"]) in object_ids)
        )

    abnormal_batch_records = matching(
        subjects=abnormal_subjects, predicate="USES_BATCH"
    )
    abnormal_version_records = matching(
        subjects=abnormal_subjects, predicate="BUILT_UNDER_VERSION"
    )
    abnormal_batches = {
        str(record["object_id"]) for record in abnormal_batch_records
    }
    abnormal_versions = {
        str(record["object_id"]) for record in abnormal_version_records
    }

    normal_outcome_records = tuple(
        record
        for record in available
        if record["predicate"] == "HAS_INSPECTION_OUTCOME"
        and outcomes.get(str(record["subject_id"])) == "normal"
    )
    normal_subjects = {
        str(record["subject_id"]) for record in normal_outcome_records
    }
    normal_batch_records = matching(
        subjects=normal_subjects, predicate="USES_BATCH"
    )
    normal_batches = {str(record["object_id"]) for record in normal_batch_records}

    allowed_types = {
        "inventory",
        "work_in_process",
        "pending_shipment",
        "in_transit",
        "customer_side",
    }
    type_records = tuple(
        record
        for record in available
        if record["predicate"] == "HAS_OBJECT_TYPE"
        and record["object_id"] in allowed_types
    )
    if not type_records:
        raise InvestigationScopeError("no temporary-control object types found")
    object_types: dict[str, str] = {}
    for record in type_records:
        object_id = str(record["subject_id"])
        if object_id in object_types:
            raise InvestigationScopeError(
                f"control object {object_id} must have exactly one object type"
            )
        object_types[object_id] = str(record["object_id"])

    objects: list[ControlScopeObject] = []
    for type_record in type_records:
        object_id = str(type_record["subject_id"])
        object_type = str(type_record["object_id"])
        missing_links = tuple(
            record
            for record in records
            if record["subject_id"] == object_id
            and record["availability"] == "missing"
        )
        direct_batch_records = matching(
            subjects={object_id}, predicate="USES_BATCH"
        )
        stocked_batch_records = tuple(
            record
            for record in available
            if record["predicate"] == "STOCKED_AS"
            and record["object_id"] == object_id
        )
        object_batch_records = direct_batch_records + stocked_batch_records
        object_batches = {
            str(record["object_id"])
            if record["predicate"] == "USES_BATCH"
            else str(record["subject_id"])
            for record in object_batch_records
        }
        exact_batches = object_batches & abnormal_batches

        if exact_batches:
            evidence = {
                str(record["evidence_ref"])
                for record in abnormal_batch_records
                if record["object_id"] in exact_batches
            } | {
                str(record["evidence_ref"])
                for record in object_batch_records
                if (
                    record["object_id"] in exact_batches
                    or record["subject_id"] in exact_batches
                )
            }
            status = ControlScopeStatus.CONFIRMED_IMPACT
            reason = "对象与质量异常件使用同一物料批次，进入临时控制候选。"
        elif object_batches and object_batches <= normal_batches and not missing_links:
            safe_batches = object_batches
            evidence = {
                str(record["evidence_ref"])
                for record in object_batch_records
                if (
                    record["object_id"] in safe_batches
                    or record["subject_id"] in safe_batches
                )
            } | {
                str(record["evidence_ref"])
                for record in normal_batch_records
                if record["object_id"] in safe_batches
            } | {
                str(record["evidence_ref"])
                for record in normal_outcome_records
                if record["subject_id"]
                in {
                    batch_record["subject_id"]
                    for batch_record in normal_batch_records
                    if batch_record["object_id"] in safe_batches
                }
            }
            status = ControlScopeStatus.EXCLUDED
            reason = "对象使用另一物料批次，且该批次关联的对照件检验正常。"
        else:
            object_version_records = matching(
                subjects={object_id}, predicate="BUILT_UNDER_VERSION"
            )
            shared_versions = {
                str(record["object_id"]) for record in object_version_records
            } & abnormal_versions
            if shared_versions:
                evidence = {
                    str(record["evidence_ref"])
                    for record in abnormal_version_records
                    if record["object_id"] in shared_versions
                } | {
                    str(record["evidence_ref"])
                    for record in object_version_records
                    if record["object_id"] in shared_versions
                }
                status = ControlScopeStatus.POSSIBLE_IMPACT
                reason = "对象与异常件使用同一版本，但缺少物料批次级直接绑定。"
            else:
                evidence = {
                    str(record["evidence_ref"])
                    for record in (*object_batch_records, *missing_links)
                } or {str(type_record["evidence_ref"])}
                status = ControlScopeStatus.NOT_EVALUABLE
                reason = "缺少把该对象闭合到异常件的必要关系，当前无法评估。"
        evidence |= scope_root_evidence
        evidence |= {str(record["evidence_ref"]) for record in missing_links}
        objects.append(
            ControlScopeObject(
                object_id=object_id,
                object_type=object_type,
                status=status,
                reason=reason,
                evidence_refs=tuple(sorted(evidence, key=str.casefold)),
            )
        )

    status_rank = {
        ControlScopeStatus.CONFIRMED_IMPACT: 0,
        ControlScopeStatus.POSSIBLE_IMPACT: 1,
        ControlScopeStatus.EXCLUDED: 2,
        ControlScopeStatus.NOT_EVALUABLE: 3,
    }
    ordered = tuple(
        sorted(
            objects,
            key=lambda item: (
                status_rank[item.status],
                item.object_type.casefold(),
                item.object_id.casefold(),
            ),
        )
    )
    return ControlScopeResult(
        schema="control_scope.v1",
        quality_signal_id=normalized_signal_id,
        objects=ordered,
        root_cause_confirmed=False,
    )
