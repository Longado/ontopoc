"""NHTSA recalls and complaints as a public source bundle; no judgement, only provenance."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Callable
from urllib.parse import urlencode
from urllib.error import HTTPError
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


# NHTSA returns recall dates day-first and complaint dates month-first (checked on the 2026-09-13 snapshot:
# all 42 recall values parse only as %d/%m/%Y where unambiguous, all 679 complaint values as %m/%d/%Y).
DATE_FORMATS = {
    'recalls': {'ReportReceivedDate': '%d/%m/%Y'},
    'complaints': {'dateComplaintFiled': '%m/%d/%Y', 'dateOfIncident': '%m/%d/%Y'},
}
_ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
# NHTSA's own test rows appear in complaint product lists as make TBD / year 9999, maker "ODI Demo Co".
_DEMO_MAKER = 'ODI Demo Co'
_DEMO_RULE = f'complaints.products[] entries with manufacturer "{_DEMO_MAKER}" (NHTSA test placeholders)'
_CAMPAIGN_REF = re.compile(r'\b(\d{2})V-?(\d{3})(\d{3})?\b')


class PublicSourceError(ValueError):
    """A public source bundle is incomplete or could not be retrieved."""


def build_nhtsa_bundle(responses: list[dict], *, decision: str, scope: dict | None = None) -> dict:
    """Merge raw API responses into one bundle: deduplicated, sorted, with every request kept."""
    sources = {kind: {'requests': [], 'records': {}} for kind in _URLS}
    for item in responses:
        kind = item.get('kind')
        if kind not in sources:
            raise PublicSourceError(f'unknown source kind: {kind!r}')
        results = (item.get('payload') or {}).get('results')
        if not isinstance(results, list):
            raise PublicSourceError(f'{kind} response has no results list: {item.get("url")}')
        sources[kind]['requests'].append({'url': item.get('url'), 'retrieved_at': item.get('retrieved_at'),
                                          **({'note': item['note']} if item.get('note') else {})})
        for record in results:
            sources[kind]['records'].setdefault(_RECORD_KEY[kind](record), copy.deepcopy(record))
    bundle = {
        'schema': SCHEMA,
        'evidence_scope': 'public_data',
        'decision': decision,
        **({'scope': scope} if scope is not None else {}),
        'date_fields': DATE_FORMATS,
        'sources': {kind: {
            'requests': sorted(s['requests'], key=lambda r: r['url']),
            'records': [_iso_dates(kind, s['records'][k]) for k in sorted(s['records'])],
        } for kind, s in sources.items()},
    }
    cleaned = drop_demo_products(bundle)
    return validate_bundle(drop_unrequested_models(cleaned) if scope is not None else cleaned)


def drop_demo_products(bundle: dict) -> dict:
    """Return a copy without NHTSA demo placeholder products, noting how many were removed."""
    removed = 0
    records = []
    for record in bundle['sources']['complaints']['records']:
        products = record.get('products')
        if isinstance(products, list):
            kept = [p for p in products if not (isinstance(p, dict) and p.get('manufacturer') == _DEMO_MAKER)]
            removed += len(products) - len(kept)
            record = {**record, 'products': kept}
        records.append(record)
    complaints = {**bundle['sources']['complaints'], 'records': records}
    return {**bundle, 'cleaning': [*bundle.get('cleaning', []), {'source': 'complaints', 'rule': _DEMO_RULE, 'removed': removed}],
            'sources': {**bundle['sources'], 'complaints': complaints}}


_VIN_PREFIX = 8  # manufacturer, model line, body and motor: enough to tell an electric Kona from a gasoline one


def drop_unrequested_models(bundle: dict) -> dict:
    """NHTSA matches complaint model names loosely (\"kona electric\" also returns gasoline \"KONA\");
    keep complaints that name a requested model, plus those whose VIN prefix matches one of them (owners
    sometimes file an electric Kona as plain \"KONA\"). Dropped and rescued complaints are listed by id."""
    wanted = {m.upper() for m in _scope(bundle)['models']}
    records = bundle['sources']['complaints']['records']

    def names_wanted(r):
        return any(isinstance(p, dict) and str(p.get('productModel', '')).upper() in wanted for p in r.get('products') or [])

    def prefix(r):
        vin = str(r.get('vin') or '')
        return vin[:_VIN_PREFIX] if len(vin) >= _VIN_PREFIX else None
    prefixes = {prefix(r) for r in records if names_wanted(r)} - {None}
    rescued = [r for r in records if not names_wanted(r) and prefix(r) in prefixes]
    kept = [r for r in records if names_wanted(r) or prefix(r) in prefixes]
    dropped = [r for r in records if not names_wanted(r) and prefix(r) not in prefixes]
    models = ', '.join(sorted(wanted))
    notes = [
        {'source': 'complaints', 'rule': f'complaints naming none of the requested models {models} (NHTSA matches model names loosely)',
         'removed': len(dropped), 'records': [r.get('odiNumber') for r in dropped]},
        {'source': 'complaints', 'rule': f'complaints naming another model but sharing a {_VIN_PREFIX}-character VIN prefix '
         f'with complaints that name {models} (kept)', 'kept': len(rescued), 'records': [r.get('odiNumber') for r in rescued]},
    ]
    complaints = {**bundle['sources']['complaints'], 'records': kept}
    return {**bundle, 'cleaning': [*bundle.get('cleaning', []), *notes], 'sources': {**bundle['sources'], 'complaints': complaints}}


def _iso_dates(kind: str, record: dict) -> dict:
    out = dict(record)
    for field, fmt in DATE_FORMATS[kind].items():
        value = record.get(field)
        if value in (None, ''):
            continue
        try:
            out[field] = datetime.strptime(str(value), fmt).date().isoformat()
        except ValueError as exc:
            raise PublicSourceError(f'{kind}.{field}: {value!r} does not match {fmt}') from exc
    return out


def fetch_nhtsa_bundle(make: str, models: list[str], years: list[int], *, decision: str,
                       opener: Callable[..., object] = urlopen,
                       clock: Callable[[], str] = lambda: datetime.now(timezone.utc).isoformat(),
                       timeout_seconds: float = 90) -> dict:
    responses = []
    for model in models:
        for year in years:
            for kind, base in _URLS.items():
                url = f'{base}?{urlencode({"make": make, "model": model, "modelYear": year})}'
                note = None
                try:
                    with opener(Request(url, headers={'Accept': 'application/json'}),
                                timeout=timeout_seconds) as reply:
                        payload = json.loads(reply.read().decode('utf-8'))
                except HTTPError as exc:
                    payload, note = _missing_model_year(exc, url)
                except (OSError, ValueError) as exc:
                    raise PublicSourceError(f'NHTSA request failed: {url}: {exc}') from exc
                responses.append({'kind': kind, 'url': url, 'retrieved_at': clock(), 'payload': payload, 'note': note})
    scope = {'make': make, 'models': list(models), 'years': [min(years), max(years)]}
    return build_nhtsa_bundle(responses, decision=decision, scope=scope)


def _missing_model_year(exc: HTTPError, url: str) -> tuple[dict, str]:
    """NHTSA answers 400 with count 0 when the model name does not exist for that year; anything else is an error."""
    try:
        body = json.loads(exc.read().decode('utf-8')) if exc.code == 400 else None
    except (OSError, ValueError):
        body = None
    if isinstance(body, dict) and body.get('count', body.get('Count')) == 0:
        return {'results': []}, 'HTTP 400 with count 0: this model name does not exist for this year'
    raise PublicSourceError(f'NHTSA request failed: {url}: HTTP {exc.code}') from exc


def validate_bundle(bundle: object) -> dict:
    if not isinstance(bundle, dict) or bundle.get('schema') != SCHEMA:
        raise PublicSourceError(f'schema must be {SCHEMA}')
    if bundle.get('evidence_scope') != 'public_data':
        raise PublicSourceError('evidence_scope must be public_data')
    if not isinstance(bundle.get('decision'), str) or not bundle['decision'].strip():
        raise PublicSourceError('decision text is required')
    if 'scope' in bundle:
        _check_scope(bundle['scope'])
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
    for name, fields in (bundle.get('date_fields') or {}).items():
        for field in fields:
            for record in sources.get(name, {}).get('records', []):
                value = record.get(field)
                if value in (None, ''):
                    continue
                try:
                    valid = bool(_ISO_DATE.match(str(value))) and datetime.fromisoformat(str(value)) is not None
                except ValueError:
                    valid = False
                if not valid:
                    raise PublicSourceError(f'{name}.{field}: {value!r} is not an ISO date')
    return bundle


def _check_scope(scope) -> None:
    ok = (isinstance(scope, dict) and isinstance(scope.get('make'), str) and scope['make'].strip()
          and isinstance(scope.get('models'), list) and scope['models']
          and all(isinstance(m, str) and m.strip() for m in scope['models'])
          and isinstance(scope.get('years'), list) and len(scope['years']) == 2
          and all(isinstance(y, int) for y in scope['years']) and scope['years'][0] <= scope['years'][1])
    if not ok:
        raise PublicSourceError('scope needs make, a non-empty models list and years [first, last]')


def _scope(bundle: dict) -> dict:
    if 'scope' not in bundle:
        raise PublicSourceError('bundle has no scope (make, models, years); refetch or add it')
    _check_scope(bundle['scope'])
    return bundle['scope']


def dataset_id(bundle: dict) -> str:
    s = _scope(bundle)
    words = [s['make'], *s['models'], str(s['years'][0]), str(s['years'][1])]
    return 'nhtsa-' + re.sub(r'[^a-z0-9]+', '-', ' '.join(words).lower()).strip('-')


def dataset_label(bundle: dict) -> str:
    s = _scope(bundle)
    return f'{s["make"].upper()} {" / ".join(m.upper() for m in s["models"])} · {s["years"][0]}–{s["years"][1]}'


def load_source_bundle(path: str | Path) -> dict:
    try:
        bundle = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise PublicSourceError(f'cannot read source bundle {path}: {exc}') from exc
    return validate_bundle(bundle)


def bundle_content_hash(bundle: dict) -> str:
    canonical = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def referenced_campaigns(text: str, campaign_ids: list[str]) -> list[str]:
    """Campaigns a recall text names explicitly, e.g. "previously remedied under recall number 21V-650"."""
    keys = {f'{year}V{number}' for year, number, _ in _CAMPAIGN_REF.findall(text or '')}
    return [c for c in campaign_ids if c[:6] in keys]
