"""What the independent review of the changed-since rule found, walked through the real service (tests/test_changed_since_confirm.py has the rule itself).

1. An undo confirms a definition again only if it would still be confirmed today had the edit never happened: the data it was confirmed on is still current, and
   nothing it reads (directly or through what those read) was changed, sent back or confirmed again since the edit set it aside. Otherwise it waits for a person.
2. A record of who changed a definition that is not well formed is read as "not known": nobody is freed by it, nothing crashes, and an undo does not confirm.
3. Confirming a group says who holds an item and the ways out, as the other routes do.
4. A person sending a definition back means putting its words back no longer confirms it by itself.
Also: the standing an agent reads names no confirmer beside words nobody confirmed; an expectation's version number is never used twice; the MCP tools write no
definition of the team workspace; a dbt import and a model's draft follow the rule."""
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote

from tests.test_changed_since_confirm import ELEMENTS, HELD_ZH, Q, Team, customer_properties
from tests.test_derived_properties import CANCELLED, ORDER
from tests.test_needed_questions import NEEDED, NeededCase, number
from tests.test_object_types import orders_upload

SWAP = [{'value': '0', 'label': '已交付'}, {'value': '1', 'label': '已取消'}, {'value': '2', 'label': '生产中'}]   # what codes 1 and 2 mean, swapped


class Moved(Team):
    def put_order(self, client, **fields):
        now = client.get('/api/workspace/types/order')[1]
        return client.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': now['version'], 'description': ORDER['description'], 'enums': {}, **fields})

    def confirm_order(self, client):
        shown = client.get('/api/workspace/types/order')[1]
        if shown['state'] != 'confirmed':
            self.assertEqual(client.post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen']})[0], 200)

    def state(self, element_id):
        return self.db('SELECT state FROM element_state WHERE element_id = ?', (element_id,))[0][0]

    def walk(self, edit, back, move, before=None):
        """The world Ann proposed and Bob confirmed: `before(team)` if given; Cat makes `edit` (element, the change); `move(team)` changes what it reads and Bob,
        who changed none of it, confirms that again; Cat makes `back`. The state of the element after, and whether it is confirmed by an undo."""
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            if before:
                before(team)
            element = edit(team)
            self.assertNotEqual(self.state(element), 'confirmed')
            move(team)
            back(team)
            return self.state(element)

    def swap_meanings(self, team):
        self.assertEqual(self.put(team['cat'], 'meanings', SWAP)[0], 200)
        self.assertEqual(self.confirm_kind(team['bob'], 'meanings')[0], 200)
        self.confirm_order(team['bob'])
        if self.state_of('relation') != 'confirmed':   # it went back with the order type
            self.assertEqual(self.confirm_kind(team['bob'], 'relation')[0], 200)

    def test_the_reviewers_sequence_a_view_put_back_after_its_meanings_were_swapped_waits_for_a_person(self):
        def edit(team):
            self.assertEqual(self.put(team['cat'], 'view', {'description': 'ZZ'})[0], 200)
            return ELEMENTS['view']
        state = self.walk(edit, lambda team: self.assertEqual(self.put(team['cat'], 'view', {'description': ''})[0], 200), self.swap_meanings)
        self.assertNotEqual(state, 'confirmed')

    def test_a_derived_property_on_a_flag_put_back_after_its_meanings_were_swapped_waits(self):
        def edit(team):
            self.assertEqual(self.put(team['cat'], 'derived', {'name': 'ZZ派生'})[0], 200)
            return ELEMENTS['derived']
        def back(team):
            status, body = self.put(team['cat'], 'derived', {'name': CANCELLED['name']})
            self.assertEqual(status, 200, body)
        state = self.walk(edit, back, self.swap_meanings)
        self.assertNotEqual(state, 'confirmed')

    def test_a_relation_put_back_after_the_key_of_a_type_it_joins_changed_waits(self):
        def edit(team):
            self.assertEqual(self.put(team['cat'], 'relation', {'name': 'ZZ关系'})[0], 200)
            return ELEMENTS['relation']

        def move(team):
            status, body = self.put(team['cat'], 'type', {'key': ['客户编号']})
            self.assertEqual(status, 200, body)
            self.assertEqual(self.confirm_kind(team['bob'], 'type')[0], 200)
        from tests.test_changed_since_confirm import ORDER_CUSTOMER
        state = self.walk(edit, lambda team: self.assertEqual(self.put(team['cat'], 'relation', {'name': ORDER_CUSTOMER['name']})[0], 200), move)
        self.assertNotEqual(state, 'confirmed')

    def test_an_action_put_back_after_a_property_of_its_type_changed_waits(self):
        def edit(team):
            self.assertEqual(self.put(team['cat'], 'action', {'description': 'ZZ'})[0], 200)
            return ELEMENTS['action']

        def move(team):
            props = [{**p, 'name': 'ZZ天数'} if p['column'] == '交付天数' else p for p in ORDER['properties']]
            self.assertEqual(self.put_order(team['cat'], properties=props)[0], 200)
            self.confirm_order(team['bob'])
        from tests.test_notices import ACTION
        state = self.walk(edit, lambda team: self.assertEqual(self.put(team['cat'], 'action', {'description': ACTION['description']})[0], 200), move)
        self.assertNotEqual(state, 'confirmed')

    def test_a_view_put_back_after_a_meaning_it_reads_got_another_name_waits(self):
        def edit(team):
            self.assertEqual(self.put(team['cat'], 'view', {'description': 'ZZ'})[0], 200)
            return ELEMENTS['view']

        def move(team):
            self.assertEqual(self.put(team['cat'], 'meanings', [{'value': '2', 'label': '已取消', 'other_names': ['作废']}])[0], 200)
            self.assertEqual(self.confirm_kind(team['bob'], 'meanings')[0], 200)
            self.confirm_order(team['bob'])
        state = self.walk(edit, lambda team: self.assertEqual(self.put(team['cat'], 'view', {'description': ''})[0], 200), move)
        self.assertNotEqual(state, 'confirmed')

    def test_a_type_whose_value_rule_reads_its_meanings_put_back_after_the_meanings_changed_waits(self):
        rule = [{'column': '状态码', 'check': 'in_codes'}]

        def before(team):
            self.assertEqual(self.put_order(team['ann'], rules=rule)[0], 200)
            self.confirm_order(team['bob'])

        def edit(team):
            self.assertEqual(self.put_order(team['cat'], description='ZZ', rules=rule)[0], 200)
            return 'objtype:order'

        def move(team):
            self.assertEqual(self.put(team['cat'], 'meanings', [{'value': '1', 'label': '生产中', 'description': 'ZZ在工厂里'}])[0], 200)
            self.assertEqual(self.confirm_kind(team['bob'], 'meanings')[0], 200)
        state = self.walk(edit, lambda team: self.assertEqual(self.put_order(team['cat'], rules=rule)[0], 200), move, before)
        self.assertNotEqual(state, 'confirmed')

    def test_a_derived_property_put_back_after_a_type_on_its_path_was_changed_and_confirmed_again_waits(self):
        def edit(team):
            self.assertEqual(self.put(team['cat'], 'derived', {'name': 'ZZ派生'})[0], 200)
            return ELEMENTS['derived']

        def move(team):   # the customer type changes and is confirmed again; so is the relation that went back with it
            self.assertEqual(self.put(team['cat'], 'type', {'description': 'ZZ客户'})[0], 200)
            self.assertEqual(self.confirm_kind(team['bob'], 'type')[0], 200)
            self.assertEqual(self.confirm_kind(team['bob'], 'relation')[0], 200)
        state = self.walk(edit, lambda team: self.assertEqual(self.put(team['cat'], 'derived', {'name': CANCELLED['name']})[0], 200), move)
        self.assertNotEqual(state, 'confirmed')

    def test_a_type_put_back_after_the_pipeline_behind_its_dataset_changed_waits(self):
        """Through what it reads: the type reads the dataset 客户合计, which the pipeline 客户合计 writes. A change of the pipeline (here its description, which keeps the
        pipeline confirmed at a new version under its own rule) moves nothing the type reads directly, and still the type waits for a person."""
        from tests.test_pipeline_server import PIPELINES, TOTAL_TYPE

        def before(team):
            self.assertEqual(team['ann'].post('/api/workspace/types', TOTAL_TYPE)[0], 200)
            shown = team['bob'].get('/api/workspace/types/customer_total')[1]
            self.assertEqual(team['bob'].post('/api/workspace/types/confirm', {'id': 'customer_total', 'version': shown['version'], 'seen': shown['seen']})[0], 200)

        def put(client, description):
            now = client.get('/api/workspace/types/customer_total')[1]
            return client.post('/api/workspace/types/update', {**TOTAL_TYPE, 'id': 'customer_total', 'version': now['version'], 'description': description})

        def edit(team):
            self.assertEqual(put(team['cat'], 'ZZ')[0], 200)
            return 'objtype:customer_total'

        def move(team):
            now = team['ann'].get(f'{PIPELINES}/{quote("客户合计")}')[1]
            self.assertEqual(team['ann'].post(f'{PIPELINES}/update', {'id': '客户合计', 'version': now['version'], 'description': 'ZZ管道'})[0], 200)
            self.assertEqual(self.state('pipeline:客户合计'), 'confirmed')
        state = self.walk(edit, lambda team: self.assertEqual(put(team['cat'], '')[0], 200), move, before)
        self.assertNotEqual(state, 'confirmed')

    def test_a_dependency_sent_back_and_still_waiting_keeps_the_put_back_definition_waiting(self):
        def edit(team):
            self.assertEqual(self.put(team['cat'], 'view', {'description': 'ZZ'})[0], 200)
            return ELEMENTS['view']

        def move(team):   # the meanings are changed and nobody confirms them: undone too, by Ann, so they are confirmed again as they were
            self.assertEqual(self.put(team['cat'], 'meanings', SWAP)[0], 200)
            self.assertEqual(self.put(team['ann'], 'meanings', [{'value': '1', 'label': '生产中'}, {'value': '2', 'label': '已取消'}])[0], 200)
        state = self.walk(edit, lambda team: self.assertEqual(self.put(team['cat'], 'view', {'description': ''})[0], 200), move)
        self.assertNotEqual(state, 'confirmed')   # the order type the meanings sent back still waits; when in doubt, a person looks


BAD = ('garbage{', 'null', '[]', '5', '"x"', '{"by": [null]}', '{"by": "23"}', '{"by": [true], "of": null}', '{"by": [], "of": 5, "was": "x"}')


class MalformedRecordTests(Team):
    def test_a_record_that_is_not_well_formed_is_read_as_not_known_and_breaks_nothing(self):
        facts = {}
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            ann, bob, cat = team['ann'], team['bob'], team['cat']
            for n, bad in enumerate(BAD):
                if self.state_of('type') == 'confirmed':
                    self.assertEqual(self.put(ann, 'type', {'description': f'ZZ{n}'})[0], 200)   # Ann changes it: she is its proposer and in the log
                self.db('UPDATE element_state SET changed_json = ? WHERE element_id = ?', (bad, ELEMENTS['type']))
                seen = (bob.get('/api/workspace/types/customer')[0], bob.get('/api/workspace/queue')[0], bob.get('/api/workspace/types')[0],
                        bob.get('/api/workspace/agent/standing')[0], self.put(cat, 'type', {'description': f'ZZ卡{n}'})[0])
                self.db('UPDATE element_state SET changed_json = ? WHERE element_id = ?', (bad, ELEMENTS['type']))
                back = self.put(cat, 'type', {'description': ''})[0]   # the words Bob confirmed: with no record to trust, it does not confirm itself
                facts[bad] = (*seen, back, self.state_of('type'), self.confirm_kind(ann, 'type')[0])
                if self.state_of('type') != 'confirmed':
                    self.assertEqual(self.confirm_kind(bob, 'type')[0], 200, bad)
        self.assertEqual(facts, {bad: (200, 200, 200, 200, 200, 200, 'checked', 403) for bad in BAD})

    def test_a_send_back_reads_a_bad_record_without_failing(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            self.assertEqual(self.put(team['cat'], 'view', {'description': 'ZZ'})[0], 200)
            self.db('UPDATE element_state SET changed_json = ? WHERE element_id = ?', ('garbage{', ELEMENTS['view']))
            item = self.detail(team['bob'], 'view')
            status, body = team['bob'].post('/api/workspace/queue/send-back', {'element': ELEMENTS['view'], 'version': item['version'], 'reason': '不对'})
            self.assertEqual(status, 200, body)


class SentBackTests(Team):
    def test_after_a_person_sent_it_back_putting_its_words_back_does_not_confirm_it(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            self.assertEqual(self.put(team['cat'], 'view', {'description': 'ZZ'})[0], 200)
            item = self.detail(team['bob'], 'view')
            status, body = team['bob'].post('/api/workspace/queue/send-back', {'element': ELEMENTS['view'], 'version': item['version'], 'reason': '说明不对'})
            self.assertEqual(status, 200, body)
            self.assertEqual(self.put(team['cat'], 'view', {'description': ''})[0], 200)
            self.assertEqual(self.state_of('view'), 'checked')


class GroupSentenceTests(Team):
    def test_confirming_a_group_says_who_holds_an_item_and_the_ways_out_in_both_languages(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(self.put(ann, 'action', {'description': 'ZZ安'})[0], 200)
            self.assertEqual(self.put(bob, 'action', {'description': 'ZZ鲍'})[0], 200)
            moved = orders_upload(lambda r, i: {**r, '金额': str(float(r['金额']) + 1)} if i == 0 else r)
            self.assertEqual(bob.post('/api/workspace/datasets/upload', {'files': [moved]})[0], 200)
            group = next(g for g in bob.get('/api/workspace/queue')[1]['groups'] if g['dataset'] == '订单')
            for lang, said in (('zh', (HELD_ZH, 'Ann', 'Bob', 'Cat', '第三位', '改回')), ('en', ('changed it since', 'Ann', 'Bob', 'Cat', 'a third person', 'Ways out', 'put back'))):
                more = {'headers': {'Accept-Language': lang}}
                shown = bob.get(f'/api/workspace/queue/group?dataset={quote(group["dataset"])}&version={group["version"]}', **more)[1]
                why = next(i for i in shown['items'] if i['element'] == ELEMENTS['action'])['why_not']
                items = [{'element': i['element'], 'version': i['version'], 'seen': i.get('seen')} for i in shown['items']]
                status, body = bob.post('/api/workspace/queue/confirm-group', {'dataset': group['dataset'], 'version': group['version'], 'items': items}, **more)
                self.assertEqual(status, 409, body)
                for word in said:
                    self.assertIn(word, why, lang)
                    self.assertIn(word, body['error'], lang)


class StandingTests(Team):
    def test_the_standing_names_no_confirmer_beside_words_nobody_confirmed(self):
        with self.service() as (base, out):
            self.out = out
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            standing = bob.get('/api/workspace/agent/standing?id=objtype%3Acustomer')[1]
            self.assertEqual((standing['confirmed'], standing['confirmed_by']), (True, 'Bob'))
            self.assertEqual(self.put(team['cat'], 'type', {'name': 'ZZ6'})[0], 200)
            standing = bob.get('/api/workspace/agent/standing?id=objtype%3Acustomer')[1]
            self.assertEqual((standing['name'], standing['confirmed'], standing['confirmed_by'], standing['confirmed_at']), ('ZZ6', False, None, None))
            listed = next(d for d in bob.get('/api/workspace/agent/standing')[1]['definitions'] if d['id'] == ELEMENTS['type'])
            self.assertIsNone(listed['confirmed_by'])
            self.assertEqual(self.put(team['cat'], 'type', {'name': '客户'})[0], 200)   # put back: Bob's confirmation stands again
            self.assertEqual(bob.get('/api/workspace/agent/standing?id=objtype%3Acustomer')[1]['confirmed_by'], 'Bob')


class NeededReviewTests(NeededCase):
    def team(self, base, valid=True):
        team = super().team(base, valid)
        from tests.test_access import Client
        from tests.test_two_person import GOOD
        self.assertEqual(team['admin'].post('/api/users', {'username': 'cat', 'display_name': 'Cat', 'role': 'builder', 'password': 'first password 1'})[0], 200)
        team['cat'] = Client(base)
        team['cat'].login('cat', 'first password 1')
        team['cat'].post('/api/auth/password', {'current': 'first password 1', 'new': GOOD})
        return team

    def change(self, client, **fields):
        found = self.item(client, Q)
        status, body = client.post(f'{NEEDED}/update', {'id': found['id'], 'version': found['version'], **fields})
        self.assertEqual(status, 200, body)
        return body

    def versions(self, out):
        conn = sqlite3.connect(out / 'workspace.sqlite')
        try:
            return conn.execute('SELECT expect_version FROM needed_question').fetchone()[0]
        finally:
            conn.close()

    def test_an_expectations_version_number_is_never_used_twice(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.write(team['ann'], Q, number(5))
            seen = [self.versions(out)]
            self.confirm(team['bob'], Q)
            seen.append(self.versions(out))
            for value in (6, 5, 7):   # changed, put back (confirmed again as it was), changed
                self.change(team['cat'], expect=number(value))
                seen.append(self.versions(out))
            self.assertEqual(self.item(team['ann'], Q)['state'], 'proposed')
            self.assertEqual(seen, sorted(set(seen)), seen)   # each one new, never one used before

    def test_a_record_that_is_not_well_formed_is_read_as_not_known(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.write(team['ann'], Q, number(5))
            self.confirm(team['bob'], Q)
            self.change(team['cat'], expect=number(6))
            for bad in BAD:
                conn = sqlite3.connect(out / 'workspace.sqlite')
                conn.execute('UPDATE needed_question SET changed_json = ?', (bad,))
                conn.commit()
                conn.close()
                self.listing(team['bob'])
                self.confirm(team['cat'], Q, status=403)   # the last to write it, and in the log
                self.change(team['cat'], expect=number(5))   # back to what Bob confirmed: with no record to trust, it does not confirm itself
                self.assertEqual(self.item(team['bob'], Q)['state'], 'proposed', bad)
                self.change(team['cat'], expect=number(6))


class EveryWayInTests(Team):
    def test_the_mcp_tools_write_no_definition_of_the_team_workspace(self):
        from ontology_poc_generator import access
        source = (Path(__file__).parent.parent / 'src' / 'ontology_poc_generator' / 'mcp_server.py').read_text(encoding='utf-8')
        paths = {p.split('?')[0] for p in re.findall(r"'(/api/workspace/[^']*)'", source)}
        self.assertTrue(paths)
        writes = {p for p in paths if access.route_role('GET', p) is None and p not in access.READ_TOKEN_POSTS}
        self.assertEqual(writes, set(), paths)   # reads, and the asks a read-only token may make: no edit, no confirmation

    def test_a_dbt_import_is_its_importers_and_whoever_changes_it_after_is_held_too(self):
        from tests.test_dbt_import import manifest, tables
        with self.service() as (base, out):
            self.out = out
            team = self.people(base, 'ann', 'bob', 'cat')
            ann, bob, cat = team['ann'], team['bob'], team['cat']
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': tables()})[0], 200)
            self.assertEqual(ann.post('/api/workspace/types/dbt-import', {'manifest': json.dumps(manifest()), 'apply': True})[0], 200)
            now = bob.get('/api/workspace/types/orders')[1]
            payload = {'id': 'orders', 'version': now['version'], 'name': now['name'], 'description': 'ZZ鲍勃的说明', 'dataset': now['dataset'], 'key': now['key'],
                       'properties': [{'column': p['column'], 'enum': p['enum']} for p in now['properties']]}
            self.assertEqual(bob.post('/api/workspace/types/update', payload)[0], 200)
            confirm = lambda client: client.post('/api/workspace/types/confirm', {'id': 'orders', 'version': client.get('/api/workspace/types/orders')[1]['version'],
                                                                                   'seen': client.get('/api/workspace/types/orders')[1]['seen']})[0]
            self.assertEqual([confirm(ann), confirm(bob), confirm(cat)], [403, 403, 200])

    def test_a_models_draft_saved_by_one_and_changed_by_another_holds_both(self):
        from tests.test_model_draft_proposer import REPLY
        from tests.test_object_types import TABLES, Suggester
        with self.service(gateway=Suggester(REPLY)) as (base, out):
            self.out = out
            team = self.people(base, 'ann', 'bob', 'cat')
            ann, bob, cat = team['ann'], team['bob'], team['cat']
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
            self.assertEqual(ann.post('/api/workspace/types/suggest', {'datasets': ['订单'], 'purpose': '订单的金额'})[0], 200)
            base_payload = {'id': 'order', 'name': '订单', 'english_name': 'order', 'dataset': '订单', 'key': ['订单号'], 'properties': [{'column': '订单号'}, {'column': '金额'}]}
            self.assertEqual(bob.post('/api/workspace/types/update', {**base_payload, 'version': bob.get('/api/workspace/types/order')[1]['version']})[0], 200)   # Bob saves the draft: his
            self.assertEqual(cat.post('/api/workspace/types/update', {**base_payload, 'description': 'ZZ卡', 'version': cat.get('/api/workspace/types/order')[1]['version']})[0], 200)
            confirm = lambda client: client.post('/api/workspace/types/confirm', {'id': 'order', 'version': client.get('/api/workspace/types/order')[1]['version'],
                                                                                  'seen': client.get('/api/workspace/types/order')[1]['seen']})[0]
            self.assertEqual([confirm(bob), confirm(cat), confirm(ann)], [403, 403, 200])   # Ann asked the model; the words now are Bob's and Cat's
