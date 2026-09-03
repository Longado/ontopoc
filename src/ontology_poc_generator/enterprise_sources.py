from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable, Mapping
from urllib.request import Request, urlopen


AUTHORITATIVE_SYSTEMS = frozenset({"ERP", "MES", "QMS", "WMS", "PLM"})
_TRANSPORTS = {"json_file", "http_json"}
_AVAILABILITY = {"available", "missing"}
_SYSTEM_PREDICATES = {
    "ERP": {"HAS_OBJECT_TYPE", "FULFILLS_ORDER", "DELIVERED_TO"},
    "MES": {
        "HAS_OBJECT_TYPE",
        "USES_BATCH",
        "BUILT_UNDER_VERSION",
        "EXECUTED_ON",
    },
    "QMS": {"IDENTIFIES", "HAS_INSPECTION_OUTCOME"},
    "WMS": {"HAS_OBJECT_TYPE", "STOCKED_AS", "USES_BATCH", "BUILT_UNDER_VERSION"},
    "PLM": {"HAS_OBJECT_TYPE", "USES_BOM", "MAPPED_TO_PROJECT"},
}
_RECORD_FIELDS = (
    "source_record_id",
    "observed_at",
    "subject_id",
    "predicate",
    "object_id",
    "availability",
    "evidence_ref",
)


class EnterpriseSourceError(ValueError):
    """A read-only enterprise source cannot produce the normalized fact contract."""


def _required_text(value: object, field: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EnterpriseSourceError(f"{field} is required")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise EnterpriseSourceError(f"{field} exceeds {maximum} characters")
    return normalized


def _read_json_payload(
    source: Mapping[str, object],
    manifest_root: Path,
    environ: Mapping[str, str],
    opener: Callable[..., object],
) -> dict[str, object]:
    system = str(source["system"])
    transport = str(source["transport"])
    location = _required_text(source.get("location"), f"{system}.location", 2000)
    if transport == "json_file":
        path = Path(location)
        if not path.is_absolute():
            path = manifest_root / path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise EnterpriseSourceError(f"cannot read {system} source: {exc}") from exc
    else:
        if not location.startswith("https://"):
            raise EnterpriseSourceError(f"{system}.location must use https")
        headers = {"Accept": "application/json"}
        token_env = source.get("token_env")
        if token_env is not None:
            token_name = _required_text(token_env, f"{system}.token_env", 120)
            expected_token_name = f"{system}_READ_TOKEN"
            if token_name != expected_token_name:
                raise EnterpriseSourceError(
                    f"{system}.token_env must be {expected_token_name}"
                )
            token = environ.get(token_name, "").strip()
            if not token:
                raise EnterpriseSourceError(f"missing read token in {token_name}")
        request = Request(location, headers=headers, method="GET")
        if token_env is not None:
            request.add_unredirected_header("Authorization", f"Bearer {token}")
        try:
            with opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise EnterpriseSourceError(f"cannot read {system} source: {exc}") from exc
    if not isinstance(payload, dict):
        raise EnterpriseSourceError(f"{system} source must be a JSON object")
    return payload


def _normalize_records(
    system: str, payload: Mapping[str, object]
) -> list[dict[str, object]]:
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise EnterpriseSourceError(f"{system}.records must be a list")
    records: list[dict[str, object]] = []
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            raise EnterpriseSourceError(f"{system}.records[{index}] must be an object")
        unexpected = sorted(set(raw) - set(_RECORD_FIELDS))
        missing = sorted(set(_RECORD_FIELDS) - set(raw))
        if missing:
            raise EnterpriseSourceError(
                f"{system}.records[{index}] missing fields: {', '.join(missing)}"
            )
        if unexpected:
            raise EnterpriseSourceError(
                f"{system}.records[{index}] unexpected fields: {', '.join(unexpected)}"
            )
        availability = _required_text(
            raw["availability"], f"{system}.records[{index}].availability", 20
        )
        if availability not in _AVAILABILITY:
            raise EnterpriseSourceError(
                f"{system}.records[{index}].availability is unsupported"
            )
        object_id = raw["object_id"]
        if availability == "available":
            object_id = _required_text(
                object_id, f"{system}.records[{index}].object_id", 300
            )
        elif object_id is not None:
            raise EnterpriseSourceError(
                f"{system}.records[{index}].object_id must be null when missing"
            )
        predicate = _required_text(
            raw["predicate"], f"{system}.records[{index}].predicate", 120
        )
        if predicate not in _SYSTEM_PREDICATES[system]:
            raise EnterpriseSourceError(
                f"{system}.records[{index}].predicate is not authoritative for {system}"
            )
        records.append(
            {
                "source_system": system,
                "source_record_id": _required_text(
                    raw["source_record_id"],
                    f"{system}.records[{index}].source_record_id",
                    300,
                ),
                "observed_at": _required_text(
                    raw["observed_at"], f"{system}.records[{index}].observed_at", 80
                ),
                "subject_id": _required_text(
                    raw["subject_id"], f"{system}.records[{index}].subject_id", 300
                ),
                "predicate": predicate,
                "object_id": object_id,
                "availability": availability,
                "evidence_ref": _required_text(
                    raw["evidence_ref"], f"{system}.records[{index}].evidence_ref", 300
                ),
            }
        )
    return records


def _canonical_hash(value: object) -> str:
    content = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _render_source_text(context_text: str, records: list[dict[str, object]]) -> str:
    lines = [f"[CONTEXT] {context_text}"]
    for record in records:
        payload = {
            key: record[key]
            for key in (
                "source_record_id",
                "observed_at",
                "subject_id",
                "predicate",
                "object_id",
                "availability",
            )
        }
        lines.append(
            f"[{record['source_system']}:{record['evidence_ref']}] "
            + json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        )
    return "\n".join(lines)


def load_enterprise_source_bundle(
    manifest_path: Path,
    *,
    environ: Mapping[str, str] | None = None,
    opener: Callable[..., object] = urlopen,
) -> dict[str, object]:
    """Read exactly five enterprise sources without changing any upstream system."""
    path = Path(manifest_path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EnterpriseSourceError(f"cannot read source manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise EnterpriseSourceError("source manifest must be a JSON object")
    if manifest.get("schema") != "enterprise_source_manifest.v1":
        raise EnterpriseSourceError("schema must be enterprise_source_manifest.v1")
    evidence_scope = _required_text(manifest.get("evidence_scope"), "evidence_scope", 80)
    if evidence_scope != "synthetic_demo":
        raise EnterpriseSourceError("evidence_scope must be synthetic_demo")
    quality_signal_id = _required_text(
        manifest.get("quality_signal_id"), "quality_signal_id", 300
    )
    context_text = _required_text(manifest.get("context_text"), "context_text", 5000)
    raw_sources = manifest.get("sources")
    if not isinstance(raw_sources, list):
        raise EnterpriseSourceError("sources must be a list")

    source_by_system: dict[str, dict[str, object]] = {}
    for index, raw_source in enumerate(raw_sources):
        if not isinstance(raw_source, dict):
            raise EnterpriseSourceError(f"sources[{index}] must be an object")
        allowed = {"system", "transport", "location", "token_env"}
        unexpected = sorted(set(raw_source) - allowed)
        if unexpected:
            raise EnterpriseSourceError(
                f"sources[{index}] unexpected fields: {', '.join(unexpected)}"
            )
        system = _required_text(raw_source.get("system"), f"sources[{index}].system", 20).upper()
        transport = _required_text(
            raw_source.get("transport"), f"sources[{index}].transport", 30
        )
        if transport not in _TRANSPORTS:
            raise EnterpriseSourceError(f"unsupported transport: {transport}")
        if system in source_by_system:
            raise EnterpriseSourceError(f"duplicate source system: {system}")
        source_by_system[system] = {**raw_source, "system": system, "transport": transport}
    if set(source_by_system) != AUTHORITATIVE_SYSTEMS:
        raise EnterpriseSourceError(
            "sources must cover exactly ERP, MES, PLM, QMS, WMS"
        )

    normalized_records: list[dict[str, object]] = []
    source_summaries: list[dict[str, object]] = []
    runtime_environ = os.environ if environ is None else environ
    for system in sorted(source_by_system):
        source = source_by_system[system]
        payload = _read_json_payload(
            source, path.parent, runtime_environ, opener
        )
        records = _normalize_records(system, payload)
        records.sort(
            key=lambda item: (
                str(item["source_record_id"]).casefold(),
                str(item["source_system"]).casefold(),
            )
        )
        normalized_records.extend(records)
        source_summaries.append(
            {
                "system": system,
                "transport": source["transport"],
                "record_count": len(records),
                "content_hash": _canonical_hash(records),
            }
        )

    normalized_records.sort(
        key=lambda item: (
            str(item["source_record_id"]).casefold(),
            str(item["source_system"]).casefold(),
        )
    )
    record_ids = [str(item["source_record_id"]).casefold() for item in normalized_records]
    if len(record_ids) != len(set(record_ids)):
        raise EnterpriseSourceError("source_record_id must be unique across systems")
    snapshot = {
        "schema": "quality_source_snapshot.v1",
        "evidence_scope": evidence_scope,
        "quality_signal_id": quality_signal_id,
        "records": normalized_records,
    }
    source_text = _render_source_text(context_text, normalized_records)
    return {
        "schema": "enterprise_source_bundle.v1",
        "evidence_scope": evidence_scope,
        "quality_signal_id": quality_signal_id,
        "content_hash": _canonical_hash(
            {"context_text": context_text, "source_snapshot": snapshot}
        ),
        "sources": source_summaries,
        "source_snapshot": snapshot,
        "source_text": source_text,
        "boundaries": {
            "read_only": True,
            "source_systems_remain_authoritative": True,
            "external_write_executed": False,
        },
    }


def local_json_source_paths(manifest_path: Path) -> tuple[Path, ...]:
    """Resolve local read inputs so a CLI cannot overwrite them with its output."""
    path = Path(manifest_path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        raw_sources = manifest["sources"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise EnterpriseSourceError(f"cannot inspect source manifest: {exc}") from exc
    if not isinstance(raw_sources, list):
        raise EnterpriseSourceError("sources must be a list")
    resolved: list[Path] = []
    for index, source in enumerate(raw_sources):
        if not isinstance(source, dict):
            raise EnterpriseSourceError(f"sources[{index}] must be an object")
        if source.get("transport") != "json_file":
            continue
        location = _required_text(
            source.get("location"), f"sources[{index}].location", 2000
        )
        source_path = Path(location)
        if not source_path.is_absolute():
            source_path = path.parent / source_path
        resolved.append(source_path)
    return tuple(resolved)
