"""What acceptance sent back on the changed-since rule, walked through the real service.

1. The record of who changed a definition is read only when the whole of it is well formed: every field, every nested field, every type. Anything else is no record
   (who changed it is read from the log, with its proposer; putting the words back does not confirm by itself), and no route that reads or writes it answers 5xx.
   The same for an expectation's record. The fuzz below takes a record the service wrote and breaks one field at a time.
2. The Leader's ruling: a pipeline is a definition. A change of its description by anyone counts as a change of the pipeline exactly as a changed step does (a new
   definition version, waiting for a second person, its writer barred, what reads its outputs sent back); words put back are a change like steps put back."""
import copy
import io
import json
import sqlite3
import zipfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from tests.test_changed_since_confirm import ELEMENTS, Q, Team, text
from tests.test_changed_since_review import NeededTeam
from tests.test_needed_questions import NEEDED, number
from tests.test_pipeline_server import JOIN, PIPELINES, SPEC, TOTAL_TYPE


def mutations(record: dict, path=()):
    """(where, what it becomes) for every field of the record, nested ones included: taken away, null, the wrong type, empty, and a list or map with an item of the
    wrong type. The record as a whole too."""
    out = []
    if not path:
        out += [((), bad) for bad in (None, 5, 'x', [], [1], {})]
    for key, value in record.items():
        here = (*path, key)
        out += [(here, '<gone>'), (here, None), (here, 5), (here, 'x'), (here, True), (here, []), (here, {}), (here, [None]), (here, [1]), (here, ['x']), (here, {'x': 1})]
        if isinstance(value, dict) and value:
            out += mutations(value, here)
        if isinstance(value, list) and value:
            out += [(here, [*value[:-1], {'x': 1}]), (here, [*value, None])]
    return out


S, S_, I_ = (lambda v: isinstance(v, str)), (lambda v: v is None or isinstance(v, str)), (lambda v: v is None or (isinstance(v, int) and not isinstance(v, bool)))
INT = lambda v: isinstance(v, int) and not isinstance(v, bool)
IDS = lambda v: isinstance(v, list) and all(INT(i) for i in v)


def exactly(value, fields: dict) -> bool:
    return isinstance(value, dict) and set(value) == set(fields) and all(check(value[k]) for k, check in fields.items())


def well_formed(record) -> bool:
    """This test's own reading of a well formed record of a definition (written apart from the service's, to check it)."""
    was = {'content_json': S, 'evidence_ref': S_, 'confirmed_by': S_, 'confirmed_at': S_, 'anchors_json': S_, 'proposed_by': S_, 'confirmed_by_user_id': I_,
           'proposed_by_user_id': I_, 'deps': lambda v: isinstance(v, list) and all(isinstance(d, str) for d in v),
           'reads': lambda v: isinstance(v, dict) and all(isinstance(m, list) and len(m) == 2 and S_(m[0]) and I_(m[1]) for m in v.values())}
    if not isinstance(record, dict):
        return False
    base = {'by': IDS, 'of': S_}
    return exactly(record, base) or exactly(record, {**base, 'was': lambda v: exactly(v, was)})


def well_formed_expectation(record) -> bool:
    was = {'state': lambda v: v == 'confirmed', 'expect_version': INT, 'written_by': S_, 'written_by_user_id': I_, 'written_at': S_, 'confirmed_by': S_,
           'confirmed_by_user_id': I_, 'confirmed_at': S_, 'self_confirmed': INT, 'basis_json': S_, 'look_json': S_}
    if not isinstance(record, dict):
        return False
    base = {'by': IDS, 'of': S_}
    return any(exactly(record, {**base, **more}) for more in ({}, {'confirmed': S}, {'confirmed': S, 'was': lambda v: exactly(v, was)}))


def applied(record: dict, where: tuple, bad):
    if not where:
        return bad
    out = copy.deepcopy(record)
    at = out
    for key in where[:-1]:
        at = at[key]
    if bad == '<gone>':
        del at[where[-1]]
    else:
        at[where[-1]] = bad
    return out


class RecordFuzzTests(Team):
    def raw(self, client, path, payload=None):
        """The status of a request, whatever it answers: a 5xx or a dropped connection is what this test looks for."""
        try:
            return client.call('POST' if payload is not None else 'GET', path, payload)[0]
        except HTTPError as exc:
            return exc.code
        except Exception as exc:   # a dropped connection, a body that is not JSON
            return f'{type(exc).__name__}'

    def test_every_field_of_the_record_broken_one_at_a_time_breaks_no_route_and_never_confirms_by_itself(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            ann, bob, cat = team['ann'], team['bob'], team['cat']
            self.assertEqual(self.put(cat, 'view', {'description': 'ZZ'})[0], 200)   # sent back, with the confirmed row kept to put back
            good = json.loads(self.db('SELECT changed_json FROM element_state WHERE element_id = ?', (ELEMENTS['view'],))[0][0])
            self.assertIn('was', good)
            self.assertTrue(good['was']['deps'] and good['was']['reads'])
            broken, statuses = 0, {}
            for where, bad in mutations(good):
                if self.state_of('view') == 'confirmed':
                    self.assertEqual(self.put(cat, 'view', {'description': 'ZZ'})[0], 200)
                    good = json.loads(self.db('SELECT changed_json FROM element_state WHERE element_id = ?', (ELEMENTS['view'],))[0][0])
                record = applied(good, where, bad)
                self.db('UPDATE element_state SET changed_json = ? WHERE element_id = ?', (json.dumps(record, ensure_ascii=False), ELEMENTS['view']))
                seen = [self.raw(bob, '/api/workspace/types/order/views'), self.raw(bob, '/api/workspace/queue'), self.raw(bob, '/api/workspace/agent/standing'),
                        self.raw(bob, '/api/workspace/types/order'), self.raw(ann, '/api/workspace/notices')]
                status, _ = self.put(cat, 'view', {'description': ''})   # the words Bob confirmed
                seen.append(status)
                restored = self.state_of('view') == 'confirmed'
                if not restored:
                    shown = self.detail(bob, 'view')
                    seen.append(self.raw(cat, '/api/workspace/types/views/confirm', {'id': shown['name'], 'version': shown['version'], 'seen': shown['seen']}))
                    seen.append(self.raw(bob, '/api/workspace/types/views/confirm', {'id': shown['name'], 'version': shown['version'], 'seen': shown['seen']}))
                key = f'{".".join(where) or "(whole)"} = {json.dumps(bad, ensure_ascii=False)}'
                statuses[key] = [s for s in seen if not isinstance(s, int) or s >= 500]
                if restored:   # only a record still well formed may put it back
                    self.assertTrue(well_formed(record), key)
                else:
                    broken += 1
            self.assertEqual({k: v for k, v in statuses.items() if v}, {})
            self.assertGreater(broken, 100)

    def test_a_send_back_and_a_group_read_a_broken_was_without_failing(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            self.assertEqual(self.put(team['cat'], 'view', {'description': 'ZZ'})[0], 200)
            good = json.loads(self.db('SELECT changed_json FROM element_state WHERE element_id = ?', (ELEMENTS['view'],))[0][0])
            self.db('UPDATE element_state SET changed_json = ? WHERE element_id = ?', (json.dumps(applied(good, ('was', 'deps'), [1])), ELEMENTS['view']))
            self.assertEqual(self.put(team['cat'], 'view', {'description': ''})[0], 200)   # acceptance's case: was.deps = [1] failed this save
            self.assertEqual(self.state_of('view'), 'checked')
            item = self.detail(team['bob'], 'view')
            status, body = team['bob'].post('/api/workspace/queue/send-back', {'element': ELEMENTS['view'], 'version': item['version'], 'reason': '不对'})
            self.assertEqual(status, 200, body)


class NeededFuzzTests(NeededTeam):
    def stored(self, out):
        conn = sqlite3.connect(out / 'workspace.sqlite')
        try:
            return conn.execute('SELECT changed_json, state FROM needed_question').fetchone()
        finally:
            conn.close()

    def test_every_field_of_an_expectations_record_broken_one_at_a_time_breaks_no_route(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, cat = team['ann'], team['bob'], team['cat']
            self.write(ann, Q, number(5))
            self.confirm(bob, Q)
            self.change(cat, expect=number(6))
            good = json.loads(self.stored(out)[0])
            self.assertIn('was', good)
            failures = {}
            for where, bad in mutations(good):
                if self.stored(out)[1] == 'confirmed':
                    self.change(cat, expect=number(6))
                    good = json.loads(self.stored(out)[0])
                conn = sqlite3.connect(out / 'workspace.sqlite')
                conn.execute('UPDATE needed_question SET changed_json = ?', (json.dumps(applied(good, where, bad), ensure_ascii=False),))
                conn.commit()
                conn.close()
                seen = [bob.get(NEEDED)[0]]
                found = self.item(cat, Q)
                seen.append(cat.post(f'{NEEDED}/update', {'id': found['id'], 'version': found['version'], 'expect': number(5)})[0])
                found = self.item(cat, Q)
                if found['state'] != 'confirmed':
                    seen.append(cat.post(f'{NEEDED}/confirm', {'id': found['id'], 'version': found['version']})[0])
                    seen.append(bob.post(f'{NEEDED}/confirm', {'id': found['id'], 'version': found['version']})[0])
                elif not well_formed_expectation(applied(good, where, bad)):
                    failures[f'{".".join(where) or "(whole)"} = {bad!r}'] = 'put back confirmed it from a broken record'
                bad_status = [s for s in seen if s >= 500]
                if bad_status:
                    failures[f'{".".join(where) or "(whole)"} = {bad!r}'] = bad_status
            self.assertEqual(failures, {})


class PipelineWordsTests(Team):
    def pipeline(self, client):
        return client.get(f'{PIPELINES}/{quote("客户合计")}')[1]

    def save(self, client, **fields):
        now = self.pipeline(client)
        return client.post(f'{PIPELINES}/update', {'id': '客户合计', 'version': now['version'], **fields})

    def confirm_pipeline(self, client):
        shown = self.pipeline(client)
        return client.post(f'{PIPELINES}/confirm', {'id': '客户合计', 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})[0]

    def world_with_total(self, team):
        """The world Ann proposed and Bob confirmed, with the type 客户合计 on the pipeline's output, put forward by Ann and confirmed by Bob."""
        self.world(team)
        self.assertEqual(team['ann'].post('/api/workspace/types', TOTAL_TYPE)[0], 200)
        shown = team['bob'].get('/api/workspace/types/customer_total')[1]
        self.assertEqual(team['bob'].post('/api/workspace/types/confirm', {'id': 'customer_total', 'version': shown['version'], 'seen': shown['seen']})[0], 200)

    def after(self, change):
        """What one change by Cat to the confirmed pipeline does: its state, definition version, proposer and who it waits for; the type on its output; whether a
        schedule would run it."""
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world_with_total(team)
            status, body = self.save(team['cat'], **change)
            self.assertEqual(status, 200, body)
            shown = self.pipeline(team['bob'])
            total = self.db("SELECT state, cause FROM element_state WHERE element_id = 'objtype:customer_total'")[0]
            from ontology_poc_generator.workspace_schedules import runnable
            held = self.db("SELECT state, cause, via FROM element_state WHERE element_id = 'pipeline:客户合计'")[0]
            schedule_runs = runnable(dict(zip(('state', 'cause', 'via'), held)))
            return {'schedule_runs': schedule_runs, 'state': shown['state'], 'definition_version': shown['definition_version'], 'proposed_by': shown['proposed_by'], 'editors': shown['editors'],
                    'cat_may_confirm': self.pipeline(team['cat'])['can_confirm'], 'total_type': total}

    def test_a_new_description_does_to_a_confirmed_pipeline_exactly_what_a_new_step_does(self):
        by_words = self.after({'description': 'ZZ卡写的'})
        by_step = self.after({'spec': {**SPEC, 'steps': [{**s, 'how': 'inner'} if s['id'] == JOIN['id'] else s for s in SPEC['steps']]}})
        self.assertEqual(by_words, by_step)
        self.assertEqual((by_words['state'], by_words['definition_version'], by_words['editors'], by_words['cat_may_confirm']), ('checked', 2, ['Cat'], False))
        self.assertEqual((by_words['total_type'][0], by_words['schedule_runs']), ('needs_look', False))   # questions on 客户合计 are refused; a schedule skips the pipeline

    def test_the_acceptance_sequence_cat_cannot_confirm_her_own_words_after_ann_changes_a_step(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            self.assertEqual(self.save(team['cat'], description='CAT 写的')[0], 200)
            self.assertEqual(self.pipeline(team['bob'])['state'], 'checked')
            self.assertEqual(self.save(team['ann'], spec={**SPEC, 'steps': [{**s, 'how': 'inner'} if s['id'] == JOIN['id'] else s for s in SPEC['steps']]})[0], 200)
            self.assertEqual([self.confirm_pipeline(team[p]) for p in ('cat', 'ann', 'bob')], [403, 403, 200])

    def test_words_put_back_are_a_change_like_steps_put_back(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            first = self.pipeline(team['bob'])['description']
            self.assertEqual(self.save(team['cat'], description='ZZ')[0], 200)
            self.assertEqual(self.save(team['cat'], description=first)[0], 200)
            shown = self.pipeline(team['bob'])
            self.assertEqual((shown['state'], shown['definition_version']), ('checked', 3))
            self.assertEqual([self.confirm_pipeline(team[p]) for p in ('cat', 'bob')], [403, 200])

    def test_saving_the_same_words_changes_nothing(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            first = self.pipeline(team['bob'])['description']
            self.assertEqual(self.save(team['cat'], description=first)[0], 200)
            shown = self.pipeline(team['bob'])
            self.assertEqual((shown['state'], shown['definition_version']), ('confirmed', 1))

    def test_no_reading_shows_a_pipelines_waiting_words(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world_with_total(team)
            self.assertEqual(self.save(team['cat'], description='ZZ管道说明')[0], 200)
            bob = team['bob']
            with urlopen(Request(bob.base + '/api/workspace/agent/skill', headers={'Cookie': f'{bob.cookie_name}={bob.cookie}'}), timeout=30) as response:
                packed = zipfile.ZipFile(io.BytesIO(response.read()))
                skill = ''.join(packed.read(n).decode() for n in packed.namelist())
            read = [text(bob, '/api/workspace/agent/standing?format=csv')[1], text(bob, '/api/workspace/agent/schema?file=ontology')[1], text(bob, '/api/workspace/agent/schema?file=shapes')[1],
                    json.dumps(bob.get('/api/workspace/agent/standing')[1], ensure_ascii=False), json.dumps(bob.get('/api/workspace/agent/definitions')[1], ensure_ascii=False), skill]
            for body in read:
                self.assertNotIn('ZZ管道说明', body)
