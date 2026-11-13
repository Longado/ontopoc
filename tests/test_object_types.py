"""Object types on the workspace, walked through the real service with two builders on the seven planted tables: a type is built from a dataset with its key
checked on every row, its code meanings are confirmed by someone other than the one who proposed them, and a re-upload that shifts the codes sends the
confirmation back to "needs another look" with the reason. Expected numbers come from the planted fixtures, counted by hand."""
import base64
import csv
import io
import json
import sqlite3
import unittest
from urllib.parse import quote

from ontology_poc_generator.recognition import ModelCompletion
from ontology_poc_generator.workspace_store import open_workspace
from tests import test_workspace_store as planted
from tests.test_two_person import SigningTestCase

TABLES = [{'filename': p.name, 'content_base64': base64.b64encode(p.read_bytes()).decode()} for p in sorted(planted.PLANTED.glob('*.xlsx'))]
MEANINGS = [{'value': '0', 'label': '已交付'}, {'value': '1', 'label': '生产中'}, {'value': '2', 'label': '已取消'}]
ORDER = {'english_name': 'order', 'name': '订单', 'dataset': '订单', 'key': ['订单号'], 'description': '客户下的一张订单',
         'properties': [{'column': '订单号'}, {'column': '金额'}, {'column': '状态码', 'enum': True}], 'enums': {'状态码': MEANINGS}}
SHIFTED = {'0': '1', '1': '2', '2': '3'}   # the same rows, each code one higher: 1/2/3 where the file had 0/1/2


def shifted_orders_csv() -> dict:
    """The 订单 table as a CSV, with every 状态码 shifted by one: an overwrite that makes 0 disappear and 3 appear."""
    records = planted.planted_bundle()['sources']['订单']['records']
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows({**r, '状态码': SHIFTED[r['状态码']]} for r in records)
    return {'filename': '订单.csv', 'content_base64': base64.b64encode(out.getvalue().encode('utf-8')).decode(), 'target': '订单', 'mode': 'overwrite'}


class Suggester:
    """A model that answers with what it is given and remembers what it was asked."""

    def __init__(self, reply):
        self.reply, self.asked = reply, []

    def complete_json(self, *, system_prompt, user_prompt):
        self.asked.append(user_prompt)
        return ModelCompletion('test', 'test-model', json.dumps(self.reply, ensure_ascii=False))


class ObjectTypeTests(SigningTestCase):
    def team(self, base, *names, roles=None):
        team = self.people(base, *names, roles=roles)
        status, body = team[names[0]].post('/api/workspace/datasets/upload', {'files': TABLES})
        self.assertEqual(status, 200, body)
        return team

    def detail(self, client, name='order'):
        status, body = client.get(f'/api/workspace/types/{name}')
        self.assertEqual(status, 200, body)
        return body

    def meanings(self, detail, column='状态码'):
        return next(p for p in detail['properties'] if p['column'] == column)['meanings']

    def confirm_all(self, proposer, confirmer):
        """The planted 订单 type with its code meanings, put forward by one builder and confirmed by the other."""
        self.assertEqual(proposer.post('/api/workspace/types', ORDER)[0], 200)
        detail = self.detail(confirmer)
        for payload in ({'id': 'order', 'column': '状态码', 'version': self.meanings(detail)['version']}, {'id': 'order', 'version': detail['version']}):
            status, body = confirmer.post('/api/workspace/types/confirm', payload)
            self.assertEqual(status, 200, body)

    def test_a_type_built_from_a_dataset_is_confirmed_by_the_other_builder_and_not_by_its_proposer(self):
        with self.service() as (base, out):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            status, body = ann.post('/api/workspace/types', ORDER)
            self.assertEqual(status, 200, body)
            detail = self.detail(ann)
            self.assertEqual((detail['state'], detail['proposed_by'], detail['rows'], detail['key']), ('checked', 'Ann', 160, ['订单号']))
            self.assertEqual((detail['can_confirm'], detail['confirmers']), (False, ['Bob', '管理员']))   # the proposer sees no button, and who could
            meanings = self.meanings(detail)
            self.assertEqual(([(v['value'], v['label'], v['rows']) for v in meanings['values']]), [('0', '已交付', 96), ('1', '生产中', 48), ('2', '已取消', 16)])
            confirm = {'id': 'order', 'column': '状态码', 'version': meanings['version']}
            status, body = ann.post('/api/workspace/types/confirm', confirm)
            self.assertEqual((status, body['error']), (403, '这一条是你自己提的，要另一位来确认'))
            self.assertEqual(ann.post('/api/workspace/types/confirm', {'id': 'order', 'version': detail['version']})[0], 403)
            status, body = bob.post('/api/workspace/types/confirm', {**confirm, 'who': 'Ann'})   # a name typed into the request is ignored
            self.assertEqual(status, 200, body)
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': detail['version']})[0], 200)
            detail = self.detail(bob)
            self.assertEqual((detail['state'], detail['confirmed_by'], detail['confirmed_on'], detail['can_confirm']), ('confirmed', 'Bob', {'订单': 1}, False))
            self.assertEqual((self.meanings(detail)['state'], self.meanings(detail)['confirmed_by']), ('confirmed', 'Bob'))
            conn = sqlite3.connect(out / 'workspace.sqlite')
            snapshots = conn.execute('SELECT element_id, confirmed_by, proposed_by, dataset_versions_json, self_confirmed FROM confirmation ORDER BY id').fetchall()
            self.assertEqual(snapshots, [('enum:order:状态码', 'Bob', 'Ann', '{"订单": 1}', 0), ('objtype:order', 'Bob', 'Ann', '{"订单": 1}', 0)])
            self.assertEqual(set(conn.execute("SELECT depends_on FROM element_dep WHERE element_id = 'objtype:order'").fetchall()), {('dataset:订单',), ('enum:order:状态码',)})
            self.assertEqual(conn.execute("SELECT depends_on FROM element_dep WHERE element_id = 'enum:order:状态码'").fetchall(), [('column:订单.状态码',)])
            conn.close()

    def test_shifted_codes_in_a_new_version_send_the_confirmed_meaning_back_and_the_log_names_both_accounts(self):
        with self.service() as (base, out):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirm_all(ann, bob)
            before = self.detail(bob)
            self.assertEqual(self.meanings(before)['state'], 'confirmed')
            status, body = ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})
            self.assertEqual((status, body['results'][0]['version']), (200, 2))
            detail = self.detail(bob)
            meaning = self.meanings(detail)
            self.assertEqual(meaning['state'], 'needs_look')
            self.assertIn('新出现 3（16 行，没有含义）', meaning['reason'])
            self.assertIn('不再出现 0（原来是「已交付」）', meaning['reason'])
            self.assertIn('第 2 版（Ann上传）', meaning['reason'])
            self.assertEqual([(v['value'], v['label'], v['rows_at_confirmation'], v['rows']) for v in meaning['values']],
                             [('0', '已交付', 96, None), ('1', '生产中', 48, 96), ('2', '已取消', 16, 48), ('3', '', None, 16)])
            self.assertEqual(detail['state'], 'needs_look')   # the type reads its meanings: it moves with them
            self.assertIn('需要再看', detail['reason'])
            self.assertEqual(detail['confirmed_by'], 'Bob')   # who confirmed it before is still there, beside the reason
            log = bob.get('/api/workspace/types/order/log')[1]['log']
            moved = next(e for e in log if e['element'] == 'meaning' and e['to'] == 'needs_look')
            self.assertEqual((moved['who'], moved['from'], moved['caused_by']), ('system', 'confirmed', 'Ann'))
            self.assertIn('新出现 3', moved['reason'])
            names = {e['who'] for e in log} - {'system'}
            self.assertEqual(names, {'Ann', 'Bob'})   # the proposer, the confirmer and (as Ann) the upload are all in it
            self.assertTrue(any(e['element'] == 'dataset' and e['who'] == 'Ann' and 'import v2' in e['text'] for e in log))
            status, body = bob.post('/api/workspace/types/confirm', {'id': 'order', 'column': '状态码', 'version': meaning['version']})
            self.assertEqual(status, 409)   # as it was it cannot be confirmed again: meanings are put forward anew
            # Bob puts the new meanings forward; Ann (who proposed the type) confirms them but cannot confirm the type, Bob can
            new = [{'value': '0', 'label': ''}, {'value': '1', 'label': '已交付'}, {'value': '2', 'label': '生产中'}, {'value': '3', 'label': '已取消'}]
            self.assertEqual(bob.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': new})[1], {'changed': True})
            meaning = self.meanings(self.detail(ann))
            self.assertEqual((meaning['state'], meaning['proposed_by'], [(v['value'], v['label']) for v in meaning['values']]),
                             ('checked', 'Bob', [('1', '已交付'), ('2', '生产中'), ('3', '已取消')]))
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'column': '状态码', 'version': meaning['version']})[0], 403)
            self.assertEqual(ann.post('/api/workspace/types/confirm', {'id': 'order', 'column': '状态码', 'version': meaning['version']})[0], 200)
            self.assertEqual(ann.post('/api/workspace/types/confirm', {'id': 'order', 'version': self.detail(ann)['version']})[0], 403)   # Ann proposed the type
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': self.detail(bob)['version']})[0], 200)
            self.assertEqual(self.detail(bob)['state'], 'confirmed')

    def test_a_confirmation_names_the_version_the_reviewer_saw(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            team['ann'].post('/api/workspace/types', ORDER)
            seen = self.detail(team['bob'])['version']
            team['ann'].post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': seen, 'name': '客户订单'})
            status, body = team['bob'].post('/api/workspace/types/confirm', {'id': 'order', 'version': seen})
            self.assertEqual(status, 409, body)
            self.assertEqual(team['bob'].post('/api/workspace/types/confirm', {'id': 'order'})[0], 409)   # no version at all
            status, body = team['ann'].post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': seen})
            self.assertEqual(status, 409)   # a save carries the revision it was based on

    def test_a_key_that_repeats_is_refused_and_the_repeated_values_are_named(self):
        with self.service() as (base, _):
            ann = self.team(base, 'ann')['ann']
            customer = {'english_name': 'customer', 'name': '客户', 'dataset': '客户', 'key': ['客户编号']}
            status, body = ann.post('/api/workspace/types', customer)
            self.assertEqual(status, 400)
            self.assertIn('KH012', body['error'])
            self.assertEqual((body['key_check']['rows_checked'], body['key_check']['violations'], body['key_check']['repeated']), (31, 1, [{'key': ['KH012'], 'rows': 2}]))
            self.assertEqual(ann.get('/api/workspace/types')[1], {'types': []})   # nothing was saved
            status, body = ann.post('/api/workspace/types/key-check', {'dataset': '订单承诺', 'key': ['订单号']})
            self.assertEqual((status, body['key_check']['violations']), (400, 61))
            status, body = ann.post('/api/workspace/types/key-check', {'dataset': '订单承诺', 'key': ['订单号', '承诺版本']})   # a composite key is fine
            self.assertEqual((status, body['rows_checked']), (200, 121))

    def test_a_decimal_or_yes_no_key_is_refused_and_a_date_key_warns(self):
        with self.service() as (base, _):
            ann = self.team(base, 'ann')['ann']
            status, body = ann.post('/api/workspace/types/key-check', {'dataset': '交付统计', 'key': ['交付天数P50']})
            self.assertEqual(status, 400)
            self.assertIn('小数', body['error'])
            status, body = ann.post('/api/workspace/types/key-check', {'dataset': '订单', 'key': ['订单号', '下单日期']})
            self.assertEqual(status, 200)
            self.assertEqual(len(body['warnings']), 1)
            self.assertIn('下单日期', body['warnings'][0])

    def test_only_what_a_confirmation_was_about_resets_it(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirm_all(ann, bob)
            version = self.detail(bob)['version']
            status, body = bob.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': version, 'name': '客户订单', 'description': '改了说明'})
            self.assertEqual((status, body['state'], body['reset']), (200, 'confirmed', []))   # a name and a description are not what was confirmed
            detail = self.detail(bob)
            self.assertEqual((detail['name'], detail['description'], detail['state'], detail['confirmed_by']), ('客户订单', '改了说明', 'confirmed', 'Bob'))
            log = bob.get('/api/workspace/types/order/log')[1]['log']
            self.assertTrue(any(e['change'] == 'edited' and e['who'] == 'Bob' for e in log))
            properties = [{'column': '订单号'}, {'column': '金额', 'type': 'text'}, {'column': '状态码', 'enum': True}]   # the amount is text now
            status, body = bob.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': detail['version'], 'properties': properties})
            self.assertEqual((status, body['state'], body['reset']), (200, 'checked', ['属性的类型']))
            detail = self.detail(ann)
            self.assertEqual((detail['proposed_by'], detail['can_confirm']), ('Bob', True))   # Bob put it forward again: now Ann may confirm
            self.assertEqual(self.meanings(detail)['state'], 'confirmed')   # the meanings were not touched
            status, body = ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': detail['version'], 'properties': [{'column': '数量', 'type': 'decimal'}, {'column': '状态码', 'enum': True}]})
            self.assertEqual(status, 200)   # an integer column read as decimal fits
            status, body = ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': self.detail(ann)['version'], 'properties': [{'column': '下单日期', 'type': 'integer'}]})
            self.assertEqual(status, 400)   # a date does not fit an integer

    def test_a_code_column_is_an_integer_or_text_never_a_yes_no_and_has_few_values(self):
        with self.service() as (base, _):
            ann = self.team(base, 'ann')['ann']
            for column, kind in (('状态码', 'boolean'), ('订单号', None)):
                status, body = ann.post('/api/workspace/types', {**ORDER, 'properties': [{'column': column, 'enum': True, **({'type': kind} if kind else {})}], 'enums': {}})
                self.assertEqual(status, 400, (column, body))   # 160 order numbers are not a code list; a code is not a boolean
            status, body = ann.post('/api/workspace/types', {**ORDER, 'enums': {'状态码': [{'value': '7', 'label': '没有这个值'}]}})
            self.assertEqual((status, '没有取值 7' in body['error']), (400, True))

    def test_a_viewer_sees_only_confirmed_types_and_cannot_write(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob', 'vic', roles={'vic': 'viewer'})
            team['ann'].post('/api/workspace/types', ORDER)
            self.assertEqual(team['vic'].get('/api/workspace/types')[1], {'types': []})
            self.assertEqual(team['vic'].get('/api/workspace/types/order')[0], 404)
            self.assertEqual(team['vic'].post('/api/workspace/types/confirm', {'id': 'order', 'version': 1})[0], 403)
            self.assertEqual(team['vic'].post('/api/workspace/types', ORDER)[0], 403)
            detail = self.detail(team['bob'])
            team['bob'].post('/api/workspace/types/confirm', {'id': 'order', 'version': detail['version']})
            self.assertEqual([t['id'] for t in team['vic'].get('/api/workspace/types')[1]['types']], ['order'])
            self.assertEqual(self.detail(team['vic'])['can_confirm'], False)

    def test_a_dataset_that_a_type_reads_cannot_be_deleted_and_says_which(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann')
            team['ann'].post('/api/workspace/types', ORDER)
            status, body = team['ann'].post('/api/workspace/datasets/delete', {'name': '订单'})
            self.assertEqual(status, 409)
            self.assertEqual(body['readers'], [{'kind': '对象类型', 'name': '订单'}])
            page = team['ann'].get('/api/workspace/datasets/' + quote('订单'))[1]
            self.assertEqual(page['readers'], [{'kind': '对象类型', 'name': '订单'}])
            self.assertEqual({d['name']: d['used_by'] for d in team['ann'].get('/api/workspace/datasets')[1]['datasets']}['订单'], 1)

    def test_objects_are_the_rows_of_the_current_version_with_the_meanings_that_are_confirmed(self):
        with self.service() as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            ann.post('/api/workspace/types', ORDER)
            objects = ann.get('/api/workspace/types/order/objects')[1]
            self.assertEqual((objects['total'], len(objects['rows']), objects['pages'], objects['dataset_version']), (160, 50, 4, 1))
            self.assertEqual([c['column'] for c in objects['columns']], ['订单号', '金额', '状态码'])
            self.assertEqual((objects['enums']['状态码']['state'], objects['enums']['状态码']['labels']), ('checked', {'0': '已交付', '1': '生产中', '2': '已取消'}))
            self.assertEqual(ann.get('/api/workspace/types/order/objects?page=9')[1]['page'], 4)

    def test_with_one_person_who_can_confirm_the_rule_is_off_and_the_log_marks_a_self_confirmation(self):
        with self.service() as (base, out):
            admin = self.people(base)['admin']
            self.assertEqual(admin.post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
            self.assertEqual(admin.post('/api/workspace/types', ORDER)[0], 200)
            detail = self.detail(admin)
            self.assertEqual(detail['can_confirm'], True)
            self.assertEqual(admin.post('/api/workspace/types/confirm', {'id': 'order', 'version': detail['version']})[0], 200)
            log = admin.get('/api/workspace/types/order/log')[1]['log']
            self.assertEqual([e['self_confirmed'] for e in log if e['element'] == 'type' and e['to'] == 'confirmed'], [True])

    def test_the_model_suggests_only_what_the_purpose_needs_and_every_suggestion_is_a_draft(self):
        reply = {'object_types': [
            {'name': '订单', 'english_name': 'order', 'dataset': '订单', 'key': ['订单号'], 'basis': '一行一张订单，订单号不重复',
             'properties': [{'column': '订单号', 'needed_for': '数订单'}, {'column': '状态码', 'needed_for': '数已取消的'}, {'column': '金额'}]},
            {'name': '客户', 'english_name': 'customer', 'dataset': '客户', 'key': ['客户编号'], 'basis': '一行一个客户', 'properties': []},
            {'name': '库存', 'english_name': 'stock', 'dataset': '库存快照', 'key': ['快照月份', '产品编号'], 'basis': '月份加产品',
             'properties': [{'column': '库存数量', 'needed_for': '看库存'}]}]}
        model = Suggester(reply)
        with self.service(gateway=model) as (base, _):
            team = self.team(base, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            status, body = ann.post('/api/workspace/types/suggest', {'datasets': ['订单', '客户', '库存快照'], 'purpose': '数已取消的订单'})
            self.assertEqual(status, 200, body)
            self.assertEqual([p['id'] for p in body['proposed']], ['order', 'stock'])
            self.assertEqual([r['name'] for r in body['rejected']], ['客户'])
            self.assertIn('KH012', body['rejected'][0]['reason'])   # the key checks a person's definition goes through caught the repeated customer
            self.assertEqual(len(model.asked), 1)
            self.assertIn('状态码', model.asked[0])   # it saw the column names
            self.assertNotIn('DD20260001', model.asked[0])   # and no row
            detail = self.detail(ann)
            self.assertEqual((detail['state'], detail['proposed_by'], detail['model_draft'], detail['can_confirm']), ('proposed', None, True, True))
            self.assertEqual([p['column'] for p in detail['properties']], ['订单号', '状态码'])   # the amount had no reason, the other columns were not asked for
            tasks = ann.get('/api/workspace/tasks')[1]['tasks']
            task = next(t for t in tasks if t['kind'] == 'suggest')
            self.assertEqual((task['state'], task['who'], task['title'], [p['id'] for p in task['proposed']]), ('done', 'Ann', '订单、客户、库存快照', ['order', 'stock']))
            # a draft a person saves is theirs, and checked; another builder confirms
            status, saved = ann.post('/api/workspace/types/update', {'id': 'order', 'version': detail['version'], 'name': '订单', 'english_name': 'order', 'dataset': '订单',
                                                                       'key': ['订单号'], 'properties': [{'column': '订单号'}, {'column': '状态码'}]})
            self.assertEqual((status, saved['state']), (200, 'checked'))
            self.assertEqual(self.detail(ann)['proposed_by'], 'Ann')
            self.assertEqual(self.detail(bob)['can_confirm'], True)

    def test_a_failed_model_request_is_a_failed_task_with_nothing_proposed(self):
        class Down:
            def complete_json(self, **_):
                from ontology_poc_generator.recognition import RecognitionError
                raise RecognitionError('model request failed: timed out')
        with self.service(gateway=Down()) as (base, _):
            ann = self.team(base, 'ann')['ann']
            status, body = ann.post('/api/workspace/types/suggest', {'datasets': ['订单'], 'purpose': 'x'})
            self.assertEqual(status, 502)
            self.assertEqual(ann.get('/api/workspace/types')[1], {'types': []})
            task = next(t for t in ann.get('/api/workspace/tasks')[1]['tasks'] if t['kind'] == 'suggest')
            self.assertEqual(task['state'], 'failed')
            self.assertIn('请稍后重试', task['error'])
        with self.service() as (base, _):   # no model configured
            ann = self.team(base, 'ann')['ann']
            self.assertEqual(ann.post('/api/workspace/types/suggest', {'datasets': ['订单'], 'purpose': 'x'})[0], 503)


class OlderFileTests(unittest.TestCase):
    def test_a_workspace_file_made_before_needs_look_existed_takes_it_and_keeps_its_rows(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'workspace.sqlite'
            old = sqlite3.connect(path)
            old.executescript("""
                CREATE TABLE element_state (
                    element_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL CHECK (state IN ('proposed', 'checked', 'confirmed', 'rejected')),
                    evidence_ref TEXT, confirmed_by TEXT, confirmed_at TEXT, version INTEGER NOT NULL, content_json TEXT, anchors_json TEXT);
                INSERT INTO element_state VALUES ('view:k:v', 'confirmed', NULL, '王工', '2026-10-01T00:00:00+00:00', 3, '{"a": 1}', NULL);""")
            old.commit()
            old.close()
            conn = open_workspace(path)
            conn.execute("UPDATE element_state SET state = 'needs_look', reason = 'x' WHERE element_id = 'view:k:v'")
            self.assertEqual(conn.execute('SELECT state, confirmed_by, version, content_json, reason FROM element_state').fetchall(), [('needs_look', '王工', 3, '{"a": 1}', 'x')])
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE element_state SET state = 'somewhere'")
            conn.close()


if __name__ == '__main__':
    unittest.main()
