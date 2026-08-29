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
_CANDIDATE_SCHEMA = "scenario_intake_candidate.v1"
_SUPPORTED_PROFILE = "order_priority_intervention"
_CANDIDATE_FIELDS = {
    "schema",
    "match_status",
    "profile_key",
    "decision_owner",
    "trigger",
    "participant_keys",
    "constraint_keys",
    "data_source_statuses",
    "desired_action_keys",
    "missing_required_fields",
}
_MATCH_STATUSES = {"matched", "insufficient_information", "unsupported"}
_SOURCE_STATUSES = {"available", "to_confirm", "unavailable"}
_MISSING_FIELDS = ("decision_owner", "trigger")

_PARTICIPANTS = {
    "order_manager": "订单经理",
    "procurement_owner": "采购负责人",
    "production_planner": "生产计划员",
    "logistics_owner": "物流负责人",
}
_CONSTRAINTS = {
    "erp_transaction_authority": "ERP 仍是交易事实权威",
    "supplier_commitment_requires_evidence": "缺少供应商承诺时不得推断为已确认交期",
    "high_risk_requires_human_confirmation": "高风险处置必须由指定责任人确认",
}
_NO_WRITEBACK_KEY = "no_erp_writeback"
_CONSTRAINT_KEYS = (*_CONSTRAINTS, _NO_WRITEBACK_KEY)
_DATA_SOURCES = {
    "erp_order_material": ("ERP 订单与物料数据", "database"),
    "supplier_commitment_feedback": ("供应商交期反馈", "spreadsheet"),
    "logistics_node_status": ("物流节点状态", "api"),
}
_DESIRED_ACTIONS = {
    "create_order_exception_review_task": "创建订单异常核查任务",
    "assign_procurement_or_planning_owner": "指定采购或计划责任人",
    "record_verdict_and_override_reason": "记录接受、拒绝和人工覆盖理由",
}
_PROFILE_OBJECTS = (
    "客户订单",
    "订单行",
    "物料",
    "供应商",
    "采购承诺",
    "生产任务",
    "物流节点",
    "履约风险",
    "处置任务",
)
_ACCEPTANCE_QUESTIONS = (
    "系统能否解释订单风险由哪些物料、供应商承诺和生产节点共同造成？",
    "业务人员修改一条约束后，风险排序和待办对象是否同步变化？",
    "无法获得物流状态时，系统是否明确显示信息不足而不是给出确定结论？",
)
_NO_WRITEBACK_NOTE = "POC 从只读分析和内部任务开始，不直接回写 ERP。"

_SYSTEM_PROMPT = """你是一个只做候选场景识别的结构化提取器。
只输出 scenario_intake_candidate.v1 JSON 对象，字段必须且只能是：
schema, match_status, profile_key, decision_owner, trigger, participant_keys,
constraint_keys, data_source_statuses, desired_action_keys, missing_required_fields。

match_status 只能是 matched、insufficient_information、unsupported。
仅当材料明确描述“哪些客户订单进入优先人工干预队列”时输出 matched，profile_key
固定为 order_priority_intervention；信息不够时输出 insufficient_information；其他场景
输出 unsupported，不要选择最接近的 profile。

participant_keys 只能使用 order_manager、procurement_owner、production_planner、
logistics_owner。constraint_keys 只能使用 erp_transaction_authority、
supplier_commitment_requires_evidence、high_risk_requires_human_confirmation、
no_erp_writeback。data_source_statuses 每项只能包含 source_key 和 status；source_key
只能使用 erp_order_material、supplier_commitment_feedback、logistics_node_status，status
只能使用 available、to_confirm、unavailable。desired_action_keys 只能使用
create_order_exception_review_task、assign_procurement_or_planning_owner、
record_verdict_and_override_reason。missing_required_fields 只能使用 decision_owner、trigger。

decision_owner 必须逐字复制材料中的负责人称谓，不能输出 participant key 或自行改写。
除 decision_owner 和 trigger 外，不要输出自由文本。不要输出对象、语义 ID、关系、
readiness、customer data、规则、threshold、expression、score、weight、客户事实、
队列结论、Action、发布状态或写回指令。
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


def _require_optional_text(
    value: object,
    field: str,
    maximum_length: int,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RecognitionError(f"{field} must be a non-empty string or null")
    normalized = value.strip()
    if len(normalized) > maximum_length:
        raise RecognitionError(f"{field} exceeds {maximum_length} characters")
    return normalized


def _require_controlled_keys(
    value: object,
    field: str,
    allowed_keys: tuple[str, ...],
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RecognitionError(f"{field} must be a list of controlled keys")
    if len(set(value)) != len(value):
        raise RecognitionError(f"duplicate {field}")
    unknown = sorted(set(value) - set(allowed_keys))
    if unknown:
        raise RecognitionError(f"unknown {field}: {', '.join(unknown)}")
    selected = set(value)
    return [key for key in allowed_keys if key in selected]


def _require_data_source_statuses(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise RecognitionError("data_source_statuses must be a list of objects")
    selected: dict[str, str] = {}
    for index, item in enumerate(value):
        if set(item) != {"source_key", "status"}:
            raise RecognitionError(
                f"data_source_statuses[{index}] must contain only source_key and status"
            )
        source_key = item["source_key"]
        status = item["status"]
        if not isinstance(source_key, str) or source_key not in _DATA_SOURCES:
            raise RecognitionError(f"unknown data source key: {source_key}")
        if source_key in selected:
            raise RecognitionError(f"duplicate data source key: {source_key}")
        if not isinstance(status, str) or status not in _SOURCE_STATUSES:
            raise RecognitionError(f"unsupported data source status: {status}")
        selected[source_key] = status
    return [
        {"source_key": key, "status": selected[key]}
        for key in _DATA_SOURCES
        if key in selected
    ]


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
    match_status = value["match_status"]
    if not isinstance(match_status, str) or match_status not in _MATCH_STATUSES:
        raise RecognitionError(f"unsupported match_status: {match_status}")
    profile_key = value["profile_key"]
    if profile_key is not None and not isinstance(profile_key, str):
        raise RecognitionError("profile_key must be a string or null")
    decision_owner = _require_optional_text(
        value["decision_owner"], "decision_owner", 80
    )
    trigger = _require_optional_text(value["trigger"], "trigger", 300)
    participant_keys = _require_controlled_keys(
        value["participant_keys"], "participant_keys", tuple(_PARTICIPANTS)
    )
    constraint_keys = _require_controlled_keys(
        value["constraint_keys"], "constraint_keys", _CONSTRAINT_KEYS
    )
    data_source_statuses = _require_data_source_statuses(value["data_source_statuses"])
    desired_action_keys = _require_controlled_keys(
        value["desired_action_keys"], "desired_action_keys", tuple(_DESIRED_ACTIONS)
    )
    missing_required_fields = _require_controlled_keys(
        value["missing_required_fields"],
        "missing_required_fields",
        _MISSING_FIELDS,
    )

    canonical: dict[str, object] = {
        "schema": _CANDIDATE_SCHEMA,
        "match_status": match_status,
        "profile_key": profile_key,
        "decision_owner": decision_owner,
        "trigger": trigger,
        "participant_keys": participant_keys,
        "constraint_keys": constraint_keys,
        "data_source_statuses": data_source_statuses,
        "desired_action_keys": desired_action_keys,
        "missing_required_fields": missing_required_fields,
    }
    if match_status == "matched":
        if profile_key != _SUPPORTED_PROFILE:
            raise RecognitionError(
                f"matched profile_key must equal {_SUPPORTED_PROFILE}"
            )
        if decision_owner is None:
            raise RecognitionError("decision_owner is required for matched candidate")
        if trigger is None:
            raise RecognitionError("trigger is required for matched candidate")
        if missing_required_fields:
            raise RecognitionError("matched candidate cannot have missing required fields")
        return canonical
    if match_status == "insufficient_information":
        if profile_key != _SUPPORTED_PROFILE:
            raise RecognitionError(
                f"insufficient profile_key must equal {_SUPPORTED_PROFILE}"
            )
        if not missing_required_fields:
            raise RecognitionError("insufficient information must identify missing fields")
        for field in _MISSING_FIELDS:
            is_missing = field in missing_required_fields
            has_value = canonical[field] is not None
            if is_missing == has_value:
                raise RecognitionError(
                    f"{field} must be null exactly when listed as missing"
                )
        raise RecognitionError("insufficient information; scenario was not compiled")
    if any(
        (
            profile_key is not None,
            decision_owner is not None,
            trigger is not None,
            participant_keys,
            constraint_keys,
            data_source_statuses,
            desired_action_keys,
            missing_required_fields,
        )
    ):
        raise RecognitionError("unsupported candidate must not contain profile data")
    raise RecognitionError("unsupported scenario; no closest profile fallback")


def _scenario_from_candidate(candidate: dict[str, object]) -> ScenarioParameters:
    participant_keys = candidate["participant_keys"]
    constraint_keys = candidate["constraint_keys"]
    source_status_items = candidate["data_source_statuses"]
    desired_action_keys = candidate["desired_action_keys"]
    assert isinstance(participant_keys, list)
    assert isinstance(constraint_keys, list)
    assert isinstance(source_status_items, list)
    assert isinstance(desired_action_keys, list)
    source_statuses = {
        item["source_key"]: item["status"]
        for item in source_status_items
        if isinstance(item, dict)
    }
    return ScenarioParameters.from_dict(
        {
            "industry": "制造业供应链",
            "scene_name": "外贸订单履约风险识别与异常处置",
            "business_decision": "哪些订单进入优先干预队列",
            "decision_key": _SUPPORTED_PROFILE,
            "decision_owner": candidate["decision_owner"],
            "trigger": candidate["trigger"],
            "participants": [_PARTICIPANTS[key] for key in participant_keys],
            "objects": list(_PROFILE_OBJECTS),
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
            "constraints": [
                _CONSTRAINTS[key] for key in constraint_keys if key in _CONSTRAINTS
            ],
            "data_sources": [
                {
                    "name": name,
                    "type": source_type,
                    "status": source_statuses.get(source_key, "to_confirm"),
                }
                for source_key, (name, source_type) in _DATA_SOURCES.items()
            ],
            "desired_actions": [
                _DESIRED_ACTIONS[key] for key in desired_action_keys
            ],
            "acceptance_questions": list(_ACCEPTANCE_QUESTIONS),
            "customer_data_available": False,
            "notes": (
                _NO_WRITEBACK_NOTE if _NO_WRITEBACK_KEY in constraint_keys else ""
            ),
            "relations": [],
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
    decision_owner = candidate["decision_owner"]
    if not isinstance(decision_owner, str) or decision_owner not in normalized_source:
        raise RecognitionError("decision_owner must be copied from source text")
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
