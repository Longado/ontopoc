"""Every operator a pipeline had before `extract` gives what main gave: golden/pipeline_ops_main.json is what main (eaf0aaa2, before the extract operator) answered, through
the real service with two builders on the seven planted tables, for four pipelines that between them use every earlier operator (filter with nested groups, in,
between and is_null; fill_null with a constant, a column and an expression; text_clean with every action, a literal replace included; cast to every type, with a
format, thousands and failures; calc; aggregate with every function; dedupe by key and by whole row; label with a mapping and each kind of unmapped) and joins, a split,
a union and outputs with a kept and a built key. For each pipeline: the answer to putting it forward, its page, its stored definition, the trial run of the whole graph
and the preview of every step and of every operator of each transform (in Chinese and in English), the run and its record, the dataset it wrote, its versions, and
the confirmation by the second builder. After that every row the walk left in the file but the accounts. Times and durations are blanked; the rest is kept as a
digest beside a few fields to read.

The operator list (/pipelines/options) is main's with exactly one entry added at the end, extract; nothing else in it changes.

To record it again, on a checkout of main with this file copied into its tests folder: ONTOPOC_RECORD_GOLDEN=1 PYTHONPATH=src python -m unittest tests.test_pipeline_ops_main
(the file is then written next to that copy; copy it back here). Only when main itself changes these answers."""
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
from urllib.parse import quote

from tests.test_fan_sum_unmarked import stored
from tests.test_object_relations import table_csv
from tests.test_object_types import TABLES
from tests.test_two_person import SigningTestCase

GOLDEN = Path(__file__).parent / 'golden' / 'pipeline_ops_main.json'
RECORD = os.environ.get('ONTOPOC_RECORD_GOLDEN') == '1'
TIME = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?')
OWNER = re.compile(r'^[0-9a-f]{32}$')
PIPELINES = '/api/workspace/pipelines'
ENGLISH = {'headers': {'Accept-Language': 'en'}}

SPECS = [
    ('客户合计', {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 't', 'type': 'input', 'dataset': '售后工单'},
                        {'id': 'j', 'type': 'join', 'left': 'o', 'right': 't', 'how': 'left', 'on': [{'left': '订单号', 'right': '订单号'}]},
                        {'id': 'g', 'type': 'transform', 'from': 'j', 'operators': [{'op': 'aggregate', 'group_by': ['客户编号'], 'aggregations': [
                            {'fn': 'sum', 'column': '金额', 'as': '合计'}, {'fn': 'count', 'column': '订单号', 'as': '行数'}]}]},
                        {'id': 'out', 'type': 'output', 'from': 'g', 'name': '客户合计', 'key': {'columns': ['客户编号']}}]}),
    ('订单清洗', {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 't', 'type': 'transform', 'from': 'o', 'operators': [
        {'op': 'filter', 'where': {'all': [{'column': '金额', 'cmp': 'gt', 'value': 0}, {'any': [{'column': '状态码', 'cmp': 'in', 'values': [0, 1, 2, 3]},
                                                                                              {'column': '交付天数', 'cmp': 'is_null'}]},
                                           {'column': '数量', 'cmp': 'between', 'low': 1, 'high': 1000}]}},
        {'op': 'fill_null', 'columns': ['交付天数'], 'with': {'constant': 0}},
        {'op': 'fill_null', 'columns': ['产品编号'], 'with': {'column': '客户编号'}, 'empty_as_null': True},
        {'op': 'fill_null', 'columns': ['数量'], 'with': {'expression': '金额 / 100'}},
        {'op': 'text_clean', 'columns': ['订单号'], 'steps': [{'do': 'trim'}, {'do': 'whitespace'}, {'do': 'lower'}, {'do': 'replace', 'find': 'dd', 'with': 'D-'}, {'do': 'upper'}]},
        {'op': 'text_clean', 'columns': ['客户编号'], 'steps': [{'do': 'replace', 'find': 'K.', 'with': '?'}]},
        {'op': 'cast', 'column': '下单日期', 'to': 'date', 'format': 'YYYY-MM-DD', 'as': '日期'},
        {'op': 'cast', 'column': '下单日期', 'to': 'datetime', 'as': '时间'},
        {'op': 'cast', 'column': '数量', 'to': 'decimal', 'thousands': True, 'as': '数量小数'},
        {'op': 'cast', 'column': '订单号', 'to': 'integer', 'as': '订单数字'},
        {'op': 'cast', 'column': '状态码', 'to': 'boolean', 'as': '是否'},
        {'op': 'calc', 'name': '单价', 'expression': 'round(金额 / 数量, 2)'},
        {'op': 'calc', 'name': '周', 'expression': "date_trunc('week', 日期)"},
        {'op': 'label', 'column': '状态码', 'mapping': [{'value': '0', 'label': '新'}, {'value': '1', 'label': '已付'}], 'unmapped': 'other', 'other': '其他', 'as': '状态'},
        {'op': 'label', 'column': '状态码', 'mapping': [{'value': '2', 'label': '取消'}], 'unmapped': 'keep', 'as': '状态2'},
        {'op': 'dedupe', 'keys': ['客户编号'], 'keep': 'last', 'order_by': '日期'}]},
        {'id': 'out', 'type': 'output', 'from': 't', 'name': '订单清洗', 'key': {'columns': ['客户编号']}}]}),
    ('产品统计', {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 'g', 'type': 'transform', 'from': 'o', 'operators': [
        {'op': 'label', 'column': '状态码', 'mapping': [{'value': '0', 'label': '新'}], 'as': '状态'},
        {'op': 'aggregate', 'group_by': ['产品编号'], 'aggregations': [{'fn': f, 'column': '金额'} for f in ('sum', 'count', 'count_distinct', 'avg', 'min', 'max', 'median', 'p25', 'p75')]
         + [{'fn': 'count'}, {'fn': 'count_distinct', 'column': '状态', 'as': '状态数'}]}]},
        {'id': 'out', 'type': 'output', 'from': 'g', 'name': '产品统计', 'key': {'columns': ['产品编号']}}]}),
    ('工单拆合', {'steps': [{'id': 't', 'type': 'input', 'dataset': '售后工单'}, {'id': 'c', 'type': 'transform', 'from': 't', 'operators': [
        {'op': 'text_clean', 'columns': ['问题描述', '负责工程师'], 'steps': [{'do': 'whitespace'}, {'do': 'upper'}]},
        {'op': 'fill_null', 'columns': ['负责工程师'], 'with': {'column': '处理状态'}},
        {'op': 'cast', 'column': '创建日期', 'to': 'date'},
        {'op': 'cast', 'column': '工单号', 'to': 'integer', 'as': '工单数字'}]},
        {'id': 's', 'type': 'split', 'from': 'c', 'branches': [{'id': 'doing', 'where': {'column': '处理状态', 'cmp': 'eq', 'value': '处理中'}}, {'id': 'rest', 'rest': True}]},
        {'id': 'u', 'type': 'union', 'inputs': ['doing', 'rest'], 'source_column': '来源'},
        {'id': 'd', 'type': 'transform', 'from': 'u', 'operators': [{'op': 'dedupe'}]},
        {'id': 'out', 'type': 'output', 'from': 'd', 'name': '工单拆合', 'key': {'columns': ['工单号', '来源'], 'separator': '|', 'as': '键'}}]}),
]


def blank(value):
    """Times, durations and a random owner: what two walks never share."""
    if isinstance(value, str):
        return OWNER.sub('<owner>', TIME.sub('<time>', value))
    if isinstance(value, (list, tuple)):
        return [blank(v) for v in value]
    if isinstance(value, dict):
        return {k: '<ms>' if k in ('duration_ms', 'took_ms') else '<clock>' if k == 'at' and isinstance(v, float) else blank(v) for k, v in value.items()}
    return value


def seen(what: str, status, body) -> dict:
    whole = blank(json.loads(json.dumps({'status': status, 'body': body}, ensure_ascii=False)))
    shown = body if isinstance(body, dict) else {}
    return {'what': what, 'status': status, 'error': shown.get('error'), 'rows': shown.get('rows') if isinstance(shown.get('rows'), int) else len(shown.get('rows') or []) or None,
            'digest': hashlib.sha256(json.dumps(whole, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}


def steps_to_preview(spec: dict) -> list[dict]:
    out = []
    for s in spec['steps']:
        out.append({'node': s['id']})
        if s['type'] == 'transform':
            out += [{'node': s['id'], 'operator': i} for i in range(len(s['operators']))]
    return out


class AgainstMain(SigningTestCase):
    def walk(self) -> dict:
        walked = {'calls': []}
        calls = walked['calls']
        with self.service() as (base, out):
            team = self.people(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            status, body = ann.post('/api/workspace/datasets/upload', {'files': TABLES})
            self.assertEqual(status, 200, body)
            for lang, more in (('zh', {}), ('en', ENGLISH)):
                walked[f'options_{lang}'] = blank(ann.get(f'{PIPELINES}/options', **more))
            for name, spec in SPECS:
                calls.append(seen(f'{name} create', *ann.post(PIPELINES, {'name': name, 'description': f'{name}的说明', 'spec': spec})))
                calls.append(seen(f'{name} detail', *ann.get(f'{PIPELINES}/{quote(name)}')))
                for lang, more in (('zh', {}), ('en', ENGLISH)):
                    calls.append(seen(f'{name} summary {lang}', *ann.post(f'{PIPELINES}/summary', {'id': name}, **more)))
                    calls.append(seen(f'{name} draft summary {lang}', *ann.post(f'{PIPELINES}/summary', {'spec': spec}, **more)))
                    for p in steps_to_preview(spec):
                        calls.append(seen(f'{name} preview {p} {lang}', *ann.post(f'{PIPELINES}/preview', {'id': name, **p}, **more)))
                    calls.append(seen(f'{name} review {lang}', *ann.post(f'{PIPELINES}/review', {'id': name}, **more)))
                status, run = ann.post(f'{PIPELINES}/run', {'id': name})
                calls.append(seen(f'{name} run', status, run))
                self.assertEqual((status, run.get('status')), (200, 'success'), run)
                calls.append(seen(f'{name} run record', *ann.get(f'{PIPELINES}/{quote(name)}/runs/{run["id"]}')))
                calls.append(seen(f'{name} run record en', *ann.get(f'{PIPELINES}/{quote(name)}/runs/{run["id"]}', **ENGLISH)))
                calls.append(seen(f'{name} runs', *ann.get(f'{PIPELINES}/{quote(name)}/runs')))
                calls.append(seen(f'{name} versions', *ann.get(f'{PIPELINES}/{quote(name)}/versions')))
                calls.append(seen(f'{name} dataset', *ann.get(f'/api/workspace/datasets/{quote(name)}')))
                shown = bob.get(f'{PIPELINES}/{quote(name)}')[1]
                calls.append(seen(f'{name} confirm', *bob.post(f'{PIPELINES}/confirm', {'id': name, 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})))
                calls.append(seen(f'{name} detail after', *bob.get(f'{PIPELINES}/{quote(name)}')))
            calls.append(seen('list', *ann.get(PIPELINES)))
            kept = blank(json.loads(json.dumps(stored(out), ensure_ascii=False, default=str)))
            walked['stored'] = {table: hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest() for table, rows in kept.items()}
            walked['stored_specs'] = [r['definition_json'] for r in kept.get('pipeline_version', [])]
        return walked

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.main = None if RECORD else json.loads(GOLDEN.read_text(encoding='utf-8'))

    def test_every_earlier_operator_gives_mains_answers_stored_definitions_runs_and_rows(self):
        walked = self.walk()
        if RECORD:
            GOLDEN.parent.mkdir(exist_ok=True)
            GOLDEN.write_text(json.dumps(walked, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
            self.skipTest('recorded')
        main = self.main
        self.assertEqual(len(walked['calls']), len(main['calls']))
        for now, then in zip(walked['calls'], main['calls']):
            with self.subTest(what=now['what']):
                self.assertEqual(now, then)
        self.assertEqual(walked['stored_specs'], main['stored_specs'])
        self.assertEqual(walked['stored'], main['stored'])
        for lang in ('zh', 'en'):
            with self.subTest(options=lang):
                status, now = walked[f'options_{lang}']
                then = main[f'options_{lang}'][1]
                self.assertEqual(status, main[f'options_{lang}'][0])
                self.assertEqual([o['op'] for o in now['operators']], [o['op'] for o in then['operators']] + ['extract'])   # one operator added, at the end
                self.assertEqual(now['operators'][:-1], then['operators'])
                self.assertEqual({k: v for k, v in now.items() if k != 'operators'}, {k: v for k, v in then.items() if k != 'operators'})


if __name__ == '__main__':
    unittest.main()
