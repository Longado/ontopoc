from __future__ import annotations

import hashlib
import json


def _stable_id(prefix: str, parts: tuple[str, ...]) -> str:
    canonical = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def stable_binding_id(
    decision_key: str,
    role_key: str,
    semantic_key: str,
) -> str:
    """Return an identity that is independent of labels, position, and time."""
    return _stable_id("binding", (decision_key, role_key, semantic_key))


def stable_suggestion_id(
    unit_id: str,
    unit_version: str,
    semantic_key: str,
    input_binding_ids: tuple[str, ...],
) -> str:
    """Return an instantiated suggestion identity from stable semantic inputs."""
    return _stable_id(
        "suggestion",
        (unit_id, unit_version, semantic_key, *input_binding_ids),
    )
