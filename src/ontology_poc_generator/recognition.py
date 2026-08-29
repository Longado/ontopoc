from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Protocol

from ontology_poc_generator.compiler import compile_decision_pack
from ontology_poc_generator.decision_pack import (
    decision_pack_content_hash,
    decision_pack_to_dict,
)
from ontology_poc_generator.models import ScenarioParameters
from ontology_poc_generator.ontology_spec import ontology_spec_to_dict
from ontology_poc_generator.spec_compiler import compile_ontology_spec


PROMPT_VERSION = "order_priority_intervention.v1"
_CANDIDATE_SCHEMA = "scenario_recognition_candidate.v1"
_SUPPORTED_PROFILE = "order_priority_intervention"
_CANDIDATE_FIELDS = {
    "schema",
    "profile",
    "industry",
    "scene_name",
    "business_decision",
    "decision_owner",
    "trigger",
    "participants",
    "additional_objects",
    "constraints",
    "data_sources",
    "desired_actions",
    "acceptance_questions",
    "notes",
}
_PROFILE_OBJECTS = ("客户订单", "物料", "供应商")

_SYSTEM_PROMPT = """你是一个只做候选场景识别的结构化提取器。
仅当材料描述“哪些客户订单进入优先人工干预队列”时，profile 输出
order_priority_intervention；否则 profile 输出 unsupported。

只输出一个 JSON 对象，字段必须且只能是：
schema, profile, industry, scene_name, business_decision, decision_owner, trigger,
participants, additional_objects, constraints, data_sources, desired_actions,
acceptance_questions, notes。

schema 固定为 scenario_recognition_candidate.v1。participants、additional_objects、
constraints、data_sources、desired_actions、acceptance_questions 必须是数组；
data_sources 每项只能包含 name、type、status，status 只能是 available、to_confirm、
unavailable。缺失的可选列表输出空数组，但 acceptance_questions 至少一项。

不要输出 decision_key、semantic_key、role_key、关系 ID、规则、threshold、expression、
score、weight、客户事实、队列结论、Action、发布状态或写回指令。不要把建议说成确认事实。
"""


class RecognitionError(ValueError):
    """A model response cannot enter the deterministic scenario boundary."""


@dataclass(frozen=True)
class ModelCompletion:
    provider: str
    model: str
    content: str

    def __post_init__(self) -> None:
        for field in ("provider", "model", "content"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise RecognitionError(f"model completion {field} is required")
            object.__setattr__(self, field, value.strip())


class RecognitionGateway(Protocol):
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> ModelCompletion: ...


@dataclass(frozen=True)
class RecognitionResult:
    prompt_version: str
    source_text_sha256: str
    provider: str
    model: str
    candidate_json: str
    scenario: ScenarioParameters

    @property
    def candidate(self) -> dict[str, object]:
        value = json.loads(self.candidate_json)
        assert isinstance(value, dict)
        return value


def _require_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise RecognitionError(f"{field} must be a list of non-empty strings")
    return [item.strip() for item in value]


def _validate_candidate(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RecognitionError("model response must be a valid JSON object")
    fields = set(value)
    missing = sorted(_CANDIDATE_FIELDS - fields)
    unexpected = sorted(fields - _CANDIDATE_FIELDS)
    if missing:
        raise RecognitionError(f"missing fields: {', '.join(missing)}")
    if unexpected:
        raise RecognitionError(f"unexpected fields: {', '.join(unexpected)}")
    if value["schema"] != _CANDIDATE_SCHEMA:
        raise RecognitionError(f"schema must equal {_CANDIDATE_SCHEMA}")
    if value["profile"] != _SUPPORTED_PROFILE:
        raise RecognitionError(f"unsupported profile: {value['profile']}")
    for field in (
        "industry",
        "scene_name",
        "business_decision",
        "decision_owner",
        "trigger",
    ):
        if not isinstance(value[field], str) or not value[field].strip():
            raise RecognitionError(f"{field} is required")
    if not isinstance(value["notes"], str):
        raise RecognitionError("notes must be a string")
    for field in (
        "participants",
        "additional_objects",
        "constraints",
        "desired_actions",
        "acceptance_questions",
    ):
        value[field] = _require_string_list(value[field], field)
    if not value["acceptance_questions"]:
        raise RecognitionError("acceptance_questions must contain at least one item")
    sources = value["data_sources"]
    if not isinstance(sources, list) or any(not isinstance(item, dict) for item in sources):
        raise RecognitionError("data_sources must be a list of objects")
    for index, source in enumerate(sources):
        if set(source) != {"name", "type", "status"}:
            raise RecognitionError(
                f"data_sources[{index}] must contain only name, type, and status"
            )
    return value


def _scenario_from_candidate(candidate: dict[str, object]) -> ScenarioParameters:
    additional_objects = candidate["additional_objects"]
    assert isinstance(additional_objects, list)
    objects = list(dict.fromkeys((*_PROFILE_OBJECTS, *additional_objects)))
    return ScenarioParameters.from_dict(
        {
            "industry": candidate["industry"],
            "scene_name": candidate["scene_name"],
            "business_decision": candidate["business_decision"],
            "decision_key": _SUPPORTED_PROFILE,
            "decision_owner": candidate["decision_owner"],
            "trigger": candidate["trigger"],
            "participants": candidate["participants"],
            "objects": objects,
            "object_role_bindings": [
                {
                    "role_key": "customer_order",
                    "semantic_key": "order.primary",
                    "object_label": "客户订单",
                },
                {
                    "role_key": "material",
                    "semantic_key": "material.required",
                    "object_label": "物料",
                },
                {
                    "role_key": "supplier",
                    "semantic_key": "supplier.candidate",
                    "object_label": "供应商",
                },
            ],
            "declared_bridges": [
                {
                    "semantic_key": "customer_order_requires_material",
                    "source_role_key": "customer_order",
                    "predicate": "REQUIRES",
                    "target_role_key": "material",
                }
            ],
            "readiness_declarations": [
                {
                    "requirement_key": "queue_entry_evidence_policy",
                    "status": "to_confirm",
                }
            ],
            "constraints": candidate["constraints"],
            "data_sources": candidate["data_sources"],
            "desired_actions": candidate["desired_actions"],
            "acceptance_questions": candidate["acceptance_questions"],
            "customer_data_available": False,
            "notes": candidate["notes"],
        }
    )


def recognize_scenario(
    source_text: str,
    gateway: RecognitionGateway,
) -> RecognitionResult:
    if not isinstance(source_text, str) or not source_text.strip():
        raise RecognitionError("source text is required")
    normalized_source = source_text.strip()
    completion = gateway.complete_json(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=f"待识别业务材料：\n{normalized_source}",
    )
    try:
        parsed = json.loads(completion.content)
    except json.JSONDecodeError as exc:
        raise RecognitionError("model response must be a valid JSON object") from exc
    candidate = _validate_candidate(parsed)
    scenario = _scenario_from_candidate(candidate)
    candidate_json = json.dumps(
        candidate,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return RecognitionResult(
        prompt_version=PROMPT_VERSION,
        source_text_sha256=hashlib.sha256(normalized_source.encode("utf-8")).hexdigest(),
        provider=completion.provider,
        model=completion.model,
        candidate_json=candidate_json,
        scenario=scenario,
    )


def build_recognition_demo_envelope(
    result: RecognitionResult,
    knowledge_units: tuple[object, ...] = (),
) -> dict[str, object]:
    pack = compile_decision_pack(result.scenario, knowledge_units)
    compilation = compile_ontology_spec(pack)
    pack_data = decision_pack_to_dict(pack)
    return {
        "schema": "model_recognition_demo.v1",
        "recognition": {
            "prompt_version": result.prompt_version,
            "source_text_sha256": result.source_text_sha256,
            "provider": result.provider,
            "model": result.model,
            "candidate": result.candidate,
        },
        "scenario": pack_data["scenario"],
        "decision_pack": {
            "content_hash": decision_pack_content_hash(pack),
            "pack": pack_data,
        },
        "ontology_spec": {
            "content_hash": compilation.spec_content_hash,
            "compilation_status": compilation.compilation_status.value,
            "reference_closure": {
                "is_closed": compilation.closure_report.is_closed,
                "checked_reference_count": compilation.closure_report.checked_reference_count,
                "issues": [
                    {
                        "issue_id": issue.issue_id,
                        "code": issue.code,
                        "owner_id": issue.owner_id,
                        "field": issue.field,
                        "referenced_id": issue.referenced_id,
                    }
                    for issue in compilation.closure_report.issues
                ],
            },
            "spec": ontology_spec_to_dict(compilation.spec),
        },
    }
