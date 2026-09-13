"""NHTSA recalls and complaints as a public source bundle; no judgement, only provenance."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA = 'public_source_bundle.v1'
RECALL_SCOPE_DECISION = ('一次汽车召回发布后，判断：哪些车型年款在召回范围内；哪些车主投诉指向同一部件'
                         '，其中哪些车辆不在任何同部件召回的范围里（范围外疑似同类问题，需要质量工程师复核）。')
_URLS = {
    'recalls': 'https://api.nhtsa.gov/recalls/recallsByVehicle',
    'complaints': 'https://api.nhtsa.gov/complaints/complaintsByVehicle',
}
_RECORD_KEY = {
    'recalls': lambda r: (str(r.get('NHTSACampaignNumber')), str(r.get('Model')), str(r.get('ModelYear'))),
    'complaints': lambda r: (str(r.get('odiNumber')),),
}


class PublicSourceError(ValueError):
    """A public source bundle is incomplete or could not be retrieved."""


def build_nhtsa_bundle(responses: list[dict], *, decision: str) -> dict:
    """Merge raw API responses into one bundle: deduplicated, sorted, with every request kept."""
    sources = {kind: {'requests': [], 'records': {}} for kind in _URLS}
    for item in responses:
        kind = item.get('kind')
        if kind not in sources:
            raise PublicSourceError(f'unknown source kind: {kind!r}')
        results = (item.get('payload') or {}).get('results')
        if not isinstance(results, list):
            raise PublicSourceError(f'{kind} response has no results list: {item.get("url")}')
        sources[kind]['requests'].append({'url': item.get('url'), 'retrieved_at': item.get('retrieved_at')})
        for record in results:
            sources[kind]['records'].setdefault(_RECORD_KEY[kind](record), record)
    bundle = {
        'schema': SCHEMA,
        'evidence_scope': 'public_data',
        'decision': decision,
        'sources': {kind: {
            'requests': sorted(s['requests'], key=lambda r: r['url']),
            'records': [s['records'][k] for k in sorted(s['records'])],
        } for kind, s in sources.items()},
    }
    return validate_bundle(bundle)


def fetch_nhtsa_bundle(make: str, models: list[str], years: list[int], *, decision: str,
                       opener: Callable[..., object] = urlopen,
                       clock: Callable[[], str] = lambda: datetime.now(timezone.utc).isoformat(),
                       timeout_seconds: float = 90) -> dict:
    responses = []
    for model in models:
        for year in years:
            for kind, base in _URLS.items():
                url = f'{base}?{urlencode({"make": make, "model": model, "modelYear": year})}'
                try:
                    with opener(Request(url, headers={'Accept': 'application/json'}),
                                timeout=timeout_seconds) as reply:
                        payload = json.loads(reply.read().decode('utf-8'))
                except (OSError, ValueError) as exc:
                    raise PublicSourceError(f'NHTSA request failed: {url}: {exc}') from exc
                responses.append({'kind': kind, 'url': url, 'retrieved_at': clock(), 'payload': payload})
    return build_nhtsa_bundle(responses, decision=decision)


def validate_bundle(bundle: object) -> dict:
    if not isinstance(bundle, dict) or bundle.get('schema') != SCHEMA:
        raise PublicSourceError(f'schema must be {SCHEMA}')
    if bundle.get('evidence_scope') != 'public_data':
        raise PublicSourceError('evidence_scope must be public_data')
    if not isinstance(bundle.get('decision'), str) or not bundle['decision'].strip():
        raise PublicSourceError('decision text is required')
    sources = bundle.get('sources')
    if not isinstance(sources, dict) or not sources:
        raise PublicSourceError('sources must be a non-empty object')
    for name, source in sources.items():
        requests = source.get('requests') if isinstance(source, dict) else None
        if not isinstance(requests, list) or not requests:
            raise PublicSourceError(f'{name}: at least one request with provenance is required')
        for request in requests:
            if not isinstance(request, dict) or not str(request.get('url', '')).startswith('https://') \
                    or not request.get('retrieved_at'):
                raise PublicSourceError(f'{name}: every request needs an https url and retrieved_at')
        if not isinstance(source.get('records'), list) or \
                any(not isinstance(r, dict) for r in source['records']):
            raise PublicSourceError(f'{name}: records must be a list of objects')
    return bundle


def load_source_bundle(path: str | Path) -> dict:
    try:
        bundle = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise PublicSourceError(f'cannot read source bundle {path}: {exc}') from exc
    return validate_bundle(bundle)


def bundle_content_hash(bundle: dict) -> str:
    canonical = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
