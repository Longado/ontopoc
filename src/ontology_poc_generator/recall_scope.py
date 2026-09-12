"""Bounded lookup of published event 95876; not a safety or impact evaluator."""
from datetime import date
import json
from pathlib import Path
import re

DEFAULT_CATALOG = Path(__file__).resolve().parents[2] / 'examples/recalls/95876.scope.json'
BOUNDARY = '仅核对事件 95876 的已公布召回范围；未匹配不代表安全，也不表示库存已控制。'


def _segments(text):
    positions = [m.start() for m in re.finditer(r'(?<!\d)[1-8]\.\s', text)]
    if len(positions) != 8:
        raise ValueError('event 95876 numbered product source changed; review required')
    return [text[a:b].strip() for a, b in zip(positions, positions[1:] + [len(text)])]


def _label_dates(text):
    november = re.search(r'November (\d+) - November (\d+), (\d{4})', text)
    if november:
        a, b, year = map(int, november.groups())
        return [date(year, 11, a).isoformat(), date(year, 11, b).isoformat()]
    numeric = re.findall(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', text)
    dates = [date(int(y), int(m), int(d)).isoformat() for m, d, y in numeric]
    return [dates[0], dates[-1]] if dates else None


def _upc(text):
    if not re.fullmatch(r'[0-9\s-]+', text):
        raise ValueError('UPC must contain only digits, spaces or hyphens')
    digits = re.sub(r'[\s-]', '', text)
    if len(digits) != 12:
        raise ValueError('UPC must have 12 digits')
    return digits


def validate_catalog(catalog, source):
    """Fail closed if reviewed product groupings differ from original source spans."""
    if (catalog.get('schema') != 'public_recall_catalog.v1'
            or catalog.get('evidence_scope') != 'public_recall'
            or catalog.get('event_id') != '95876'):
        raise ValueError('only public recall event 95876 is supported')
    expected_url = 'https://api.fda.gov/food/enforcement.json?search=event_id:95876&limit=100'
    if source.get('source_url') != expected_url or not source.get('retrieved_at'):
        raise ValueError('original openFDA source metadata is missing')
    records = source['response']['results']
    expected_ids = {f'F-{n:04d}-2025' for n in range(367, 372)}
    if (len(records) != 5 or {r['recall_number'] for r in records} != expected_ids
            or any(r['event_id'] != '95876' for r in records)):
        raise ValueError('event 95876 must include the five original records')
    expected = {}
    for r in records:
        key = r['recall_number']
        descriptions = _segments(r['product_description']) if key == 'F-0367-2025' else [r['product_description']]
        codes = _segments(r['code_info']) if key == 'F-0367-2025' else [r['code_info']]
        for index, (description, code) in enumerate(zip(descriptions, codes), 1):
            expected[f'{key}/{index}'] = (r, description, code)
    products = catalog.get('products', [])
    if len(products) != len(expected) or {p['product_key'] for p in products} != set(expected):
        raise ValueError('catalog must cover all 12 original product groups exactly once')
    for p in products:
        record, description, code = expected[p['product_key']]
        if (p['recall_number'] != record['recall_number']
                or p['description_quote'] != description or p['code_quote'] != code):
            raise ValueError('product/source segment mismatch')
        lots = re.findall(r'\bX\d{7}\b', code)
        if len(p['lots']) != len(set(p['lots'])) or sorted(p['lots']) != sorted(lots):
            raise ValueError('lot set differs from the cited product segment')
        match = re.search(r'UPC\s+([\d -]+)', description)
        expected_upc = _upc(match[1]) if match else None
        if p['upc'] != expected_upc or p['label_date_range'] != _label_dates(code):
            raise ValueError('UPC or label dates differ from original source')


def load_catalog(path=DEFAULT_CATALOG):
    path = Path(path)
    catalog = json.loads(path.read_text(encoding='utf-8'))
    source = json.loads(path.with_name('95876.openfda.json').read_text(encoding='utf-8'))
    validate_catalog(catalog, source)
    return {**catalog, 'source_url': source['source_url'],
            'retrieved_at': source['retrieved_at'],
            'records': {r['recall_number']: r for r in source['response']['results']}}


def match_recall(catalog, query):
    fields = {'product', 'lot', 'upc', 'label_date'}
    if not isinstance(query, dict) or set(query) - fields:
        raise ValueError('query fields must be product, lot, upc, label_date')
    if any(not isinstance(v, str) or len(v) > 300 for v in query.values()):
        raise ValueError('query values must be text of at most 300 characters')
    q = {key: query.get(key, '').strip() for key in fields}
    q['lot'] = q['lot'].upper()
    if q['upc']:
        q['upc'] = _upc(q['upc'])
    if q['label_date']:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', q['label_date']):
            raise ValueError('label_date must be YYYY-MM-DD')
        date.fromisoformat(q['label_date'])
    products = catalog['products']
    by_product = [p for p in products if q['product'] and q['product'].casefold() in
                  {p['product_key'].casefold(), p['name'].casefold()}]
    by_upc = [p for p in products if q['upc'] and p['upc'] == q['upc']]
    by_lot = [p for p in products if q['lot'] in p['lots']]
    selected = by_product or by_upc

    def result(status, reason, relevant=None):
        relevant = selected if relevant is None else relevant
        evidence = []
        for p in relevant:
            record = catalog['records'][p['recall_number']]
            evidence.append({
                'product_key': p['product_key'], 'name': p['name'],
                'recall_number': p['recall_number'], 'upc': p['upc'],
                'description_quote': p['description_quote'], 'code_quote': p['code_quote'],
                'label_date_range': p['label_date_range'],
                'reason_for_recall': record['reason_for_recall'],
                'distribution_pattern': record['distribution_pattern'],
                'recall_initiation_date': record['recall_initiation_date'],
                'source_url': catalog['source_url'],
            })
        return {'schema': 'public_recall_match.v1', 'event_id': '95876',
                'evidence_scope': 'public_recall', 'query': q, 'status': status,
                'reason': reason, 'evidence': evidence, 'boundary': BOUNDARY,
                'source_url': catalog['source_url'], 'retrieved_at': catalog['retrieved_at']}

    if q['product'] and q['upc']:
        if by_upc and by_product != by_upc:
            return result('conflict', '产品与 UPC 指向不同身份，请核对标签。', by_product + by_upc)
        if by_product and not by_upc:
            if any(p['upc'] for p in by_product):
                return result('conflict', '输入 UPC 与该产品公告中的 UPC 不一致。')
            return result('insufficient', '本公告未提供该产品 UPC，无法核验额外身份信息。')
    if not selected:
        if by_lot and (q['product'] or q['upc']):
            return result('conflict', '批号出现在公告中，但输入的产品身份不匹配，请复核。', by_lot)
        return result('insufficient' if not (q['product'] or q['upc']) else 'not_matched',
                      '请提供可核对的产品标识或 UPC。' if not (q['product'] or q['upc']) else
                      '未找到该产品身份；请核对名称或使用公告产品编号/UPC。', [])
    if not q['lot']:
        return result('insufficient', '缺少批号，请查看产品标签后补充。')
    if len(selected) != 1:
        return result('insufficient', '产品身份对应多个条目，需要进一步核对。')
    p = selected[0]
    if q['lot'] not in p['lots']:
        if by_lot:
            return result('conflict', '批号属于公告中的另一产品，请核对产品与批号。', selected + by_lot)
        return result('not_matched', '该批号未列在所选产品的本公告范围中；不代表安全。')
    if q['label_date']:
        bounds = p['label_date_range']
        if not bounds:
            return result('insufficient', '本公告未明确该产品的标签日期范围，无法核验输入日期。')
        if not bounds[0] <= q['label_date'] <= bounds[1]:
            return result('conflict', '批号匹配，但标签 Use/Sell By 日期不在公告范围内，请复核。')
    return result('matched', '产品身份与列明批号匹配本公告。' +
                  ('标签日期也在公告范围内。' if q['label_date'] else '未提供标签日期，未核对日期。'))
