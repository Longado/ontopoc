from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ValidationReceiptValidationError(ValueError):
    """A validation receipt violates the frozen local contract."""


class EvaluationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"
    UNSUPPORTED = "unsupported"


class DecisionResult(str, Enum):
    IN_QUEUE = "in_queue"
    NOT_IN_QUEUE = "not_in_queue"
    INFORMATION_INSUFFICIENT = "information_insufficient"
    UNSUPPORTED = "unsupported"


_RESULT_BY_STATUS = {
    EvaluationStatus.PASS: DecisionResult.IN_QUEUE,
    EvaluationStatus.FAIL: DecisionResult.NOT_IN_QUEUE,
    EvaluationStatus.NOT_EVALUABLE: DecisionResult.INFORMATION_INSUFFICIENT,
    EvaluationStatus.UNSUPPORTED: DecisionResult.UNSUPPORTED,
}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationReceiptValidationError(f"{field} is required")
    return value.strip()


def _content_hash(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise ValidationReceiptValidationError(
            f"{field} must be a lowercase SHA-256 hex digest"
        )
    return value


def _references(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValidationReceiptValidationError(
            f"{field} must be a non-empty tuple"
        )
    normalized = tuple(
        _required_text(item, f"{field}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(normalized)) != len(normalized):
        raise ValidationReceiptValidationError(f"{field} must not contain duplicates")
    return tuple(sorted(normalized))


@dataclass(frozen=True)
class ValidationReceipt:
    schema: str
    decision_pack_content_hash: str
    ontology_spec_content_hash: str
    facts_content_hash: str
    rule_id: str
    evaluation_status: EvaluationStatus
    decision_result: DecisionResult
    fact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    draft_created: bool
    published: bool
    actions_executed: bool
    external_write: bool

    def __post_init__(self) -> None:
        if self.schema != "validation_receipt.v1":
            raise ValidationReceiptValidationError(
                "schema must be validation_receipt.v1"
            )
        for field in (
            "decision_pack_content_hash",
            "ontology_spec_content_hash",
            "facts_content_hash",
        ):
            object.__setattr__(
                self,
                field,
                _content_hash(getattr(self, field), field),
            )
        object.__setattr__(self, "rule_id", _required_text(self.rule_id, "rule_id"))
        if not isinstance(self.evaluation_status, EvaluationStatus):
            raise ValidationReceiptValidationError(
                "evaluation_status must be EvaluationStatus"
            )
        if not isinstance(self.decision_result, DecisionResult):
            raise ValidationReceiptValidationError(
                "decision_result must be DecisionResult"
            )
        expected_result = _RESULT_BY_STATUS[self.evaluation_status]
        if self.decision_result is not expected_result:
            raise ValidationReceiptValidationError(
                "decision_result does not match evaluation_status"
            )
        object.__setattr__(self, "fact_refs", _references(self.fact_refs, "fact_refs"))
        object.__setattr__(
            self,
            "evidence_refs",
            _references(self.evidence_refs, "evidence_refs"),
        )
        for field in (
            "draft_created",
            "published",
            "actions_executed",
            "external_write",
        ):
            if getattr(self, field) is not False:
                raise ValidationReceiptValidationError(
                    f"{field} must be literal false"
                )


def validation_receipt_to_dict(receipt: ValidationReceipt) -> dict[str, object]:
    """Return the explicit canonical content projection of a receipt."""
    if not isinstance(receipt, ValidationReceipt):
        raise ValidationReceiptValidationError(
            "receipt must be a ValidationReceipt"
        )
    return {
        "schema": receipt.schema,
        "decision_pack_content_hash": receipt.decision_pack_content_hash,
        "ontology_spec_content_hash": receipt.ontology_spec_content_hash,
        "facts_content_hash": receipt.facts_content_hash,
        "rule_id": receipt.rule_id,
        "evaluation_status": receipt.evaluation_status.value,
        "decision_result": receipt.decision_result.value,
        "fact_refs": list(receipt.fact_refs),
        "evidence_refs": list(receipt.evidence_refs),
        "draft_created": receipt.draft_created,
        "published": receipt.published,
        "actions_executed": receipt.actions_executed,
        "external_write": receipt.external_write,
    }


def canonical_validation_receipt_json(receipt: ValidationReceipt) -> str:
    return json.dumps(
        validation_receipt_to_dict(receipt),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def validation_receipt_content_hash(receipt: ValidationReceipt) -> str:
    canonical = canonical_validation_receipt_json(receipt).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


canonical_validation_receipt_dict = validation_receipt_to_dict
