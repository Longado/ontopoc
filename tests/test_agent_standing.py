"""The gate read from other tools: GET /api/workspace/agent/standing says, as the signed-in person or the token's owner, whether each definition they may see is
confirmed, by whom, when and on which data versions, and when it is not, why and who can confirm it; ?id= gives one; ?format=csv is the sheet of the confirmed
ones; the MCP tool definition_standing reads the same. A viewer or a token is told nothing about a definition they may not see: not its name, not that it exists,
not a count that includes it. The skill folder says it is a snapshot and where the live standing is."""
import csv
import io
import json
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

from ontology_poc_generator import mcp_server
from ontology_poc_generator.object_types import hidden_reason
from tests.test_access import Client
from tests.test_agent_access import AgentCase
from tests.test_derived_properties import GROSS
from tests.test_workspace_questions import AskModel, cancelled

STANDING = '/api/workspace/agent/standing'
GROSS_ID = 'derived:order:gross'


def bearer(token):
    return {'headers': {'Authorization': f'Bearer {token}'}, 'origin': None}


class StandingCase(AgentCase):
    def standing(self, client, token=None, element_id=None, expect=200):
        path = STANDING + (f'?id={quote(element_id, safe="")}' if element_id is not None else '')
        status, body = client.get(path, **bearer(token)) if token else client.get(path)
        self.assertEqual(status, expect, body)
        return body

    def sheet(self, base, token):
        """The CSV as a token's owner downloads it: (content type, rows as dicts)."""
        request = Request(base + STANDING + '?format=csv', headers={'Authorization': f'Bearer {token}'})
        with urlopen(request, timeout=30) as response:
            kind, raw = response.headers['Content-Type'], response.read()
        return kind, list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))

    @staticmethod
    def confirmed_ids(defined):
        """The element ids of what /agent/definitions lists: the confirmed definitions the person may see."""
        ids = {f'objtype:{t["id"]}' for t in defined['types']} | {f'enum:{t["id"]}:{c}' for t in defined['types'] for c in t['meanings']}
        ids |= {f'relation:{r["id"]}' for r in defined['relations']} | {f'objview:{v["id"]}' for v in defined['views']}
        return ids | {f'derived:{x["type"]}:{x["id"]}' for x in defined['derived']}


class StandingTests(StandingCase):
    def test_a_token_reads_the_standing_of_every_definition_its_person_may_see_and_of_one_by_id(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)   # 含税金额 is put forward by Ann and nobody has confirmed it
            token = self.token_for(admin, 'bob')['token']
            script = Client(base)
            body = self.standing(script, token)
            entries = {e['id']: e for e in body['definitions']}
            confirmed = {i for i, e in entries.items() if e['state'] == 'confirmed'}
            self.assertEqual(confirmed, self.confirmed_ids(bob.get('/api/workspace/agent/definitions')[1]))   # the same confirmed set the agent is given
            order = entries['objtype:order']
            self.assertEqual((order['kind'], order['name'], order['confirmed'], order['confirmed_by'], order['data_versions']), ('type', '订单', True, 'Bob', {'订单': 1}))
            self.assertTrue(order['confirmed_at'])
            self.assertEqual((entries['enum:order:状态码']['kind'], entries['enum:order:状态码']['name'], entries['enum:order:状态码']['confirmed_by']), ('meaning', '订单.状态码', 'Bob'))
            self.assertEqual(entries['objview:有效订单']['kind'], 'view')
            gross = entries[GROSS_ID]
            self.assertEqual((gross['kind'], gross['name'], gross['state'], gross['confirmed'], gross['confirmed_by'], gross['data_versions']), ('derived', '订单.含税金额', 'checked', False, None, None))
            self.assertIn('Bob', gross['who_can_confirm'])
            self.assertNotIn('Ann', gross['who_can_confirm'])   # she put it forward: two-person confirmation
            self.assertEqual(gross['proposed_by'], 'Ann')
            self.assertEqual(gross['reason'], '已经提出，还没有另一位确认')   # the cause of one that only waits is its state, in words
            self.assertEqual([e['id'] for e in body['definitions'] if not e['confirmed']], [GROSS_ID])
            for e in body['definitions']:
                self.assertFalse({'rows', 'rows_stored', 'total', 'count'} & set(e), e['id'])   # no count of the data
            # one by id: the same entry; one that does not exist is not found
            self.assertEqual(self.standing(script, token, 'objtype:order'), order)
            self.assertEqual(self.standing(script, token, GROSS_ID), gross)
            missing = self.standing(script, token, 'objtype:nothing', expect=404)
            self.assertTrue(missing['error'])
            # the signed-in page reads the same
            self.assertEqual(self.standing(bob)['definitions'], body['definitions'])

    def test_a_viewer_reads_only_confirmed_ones_and_is_not_told_that_an_unconfirmed_one_exists(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, vera, admin = team['ann'], team['vera'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)
            for read in (lambda **k: self.standing(vera, **k), lambda **k: self.standing(Client(base), self.token_for(admin, 'vera', label='看板')['token'], **k)):
                body = read()
                self.assertTrue(body['definitions'])
                self.assertTrue(all(e['state'] == 'confirmed' and e['confirmed'] for e in body['definitions']))
                said = json.dumps(body, ensure_ascii=False)
                for word in ('含税金额', 'gross', 'who_can_confirm', 'Ann'):   # not its name, not who could confirm it (a viewer is not told names), not who put it forward
                    self.assertNotIn(word, said)
                hidden = read(element_id=GROSS_ID, expect=404)
                self.assertEqual(hidden, read(element_id='derived:order:nothing', expect=404))   # the same answer as for one that does not exist

    def test_a_type_kept_to_named_people_is_left_out_with_everything_on_it_and_by_id_is_not_found(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            before = {e['id'] for e in self.standing(bob)['definitions']}
            self.assertIn('objtype:ticket', before)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'ticket', 'visible_to': [ids['ann']]})[0], 200)
            token = self.token_for(admin, 'bob')['token']
            body = self.standing(Client(base), token)
            said = json.dumps(body, ensure_ascii=False)
            self.assertNotIn('ticket', said)
            self.assertNotIn('售后工单', said)
            kept = {e['id'] for e in self.standing(ann)['definitions']}
            self.assertEqual(kept, before)   # Ann still reads all of it
            self.assertEqual({e['id'] for e in body['definitions']}, {i for i in before if 'ticket' not in i})   # the list Bob reads has nothing about it, so no count includes it
            self.assertEqual(self.standing(Client(base), token, 'objtype:ticket', expect=404), self.standing(Client(base), token, 'objtype:nothing', expect=404))
            _, rows = self.sheet(base, token)
            self.assertNotIn('售后工单', json.dumps(rows, ensure_ascii=False))

    def test_a_row_limited_builder_reads_the_cause_without_the_counts_of_the_whole_data(self):
        from tests.test_object_types import shifted_orders_csv
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            rules = [{'column': '客户编号', 'value': 'KH026', 'user_ids': [ids['bob']]}, {'column': '', 'value': '', 'user_ids': [ids['ann']]}]
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': rules})[0], 200)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)   # the codes move: 订单 needs another look
            whole = {e['id']: e for e in self.standing(ann)['definitions']}['enum:order:状态码']
            self.assertEqual(whole['state'], 'needs_look')
            self.assertTrue(whole['reason'])
            self.assertEqual(whole['cause_word'], '数据变了')
            self.assertEqual((whole['confirmed_by'], whole['data_versions']), ('Bob', {'订单': 1}))   # the confirmation it had, on the data before
            limited = {e['id']: e for e in self.standing(Client(base), self.token_for(admin, 'bob')['token'])['definitions']}['enum:order:状态码']
            self.assertEqual((limited['state'], limited['reason'], limited['reason_hidden'], limited['cause_word']), ('needs_look', None, hidden_reason(), '数据变了'))

    def test_the_sheet_holds_the_confirmed_definitions_the_person_may_see_and_what_each_says(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, admin = team['ann'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)
            token = self.token_for(admin, 'bob')['token']
            kind, rows = self.sheet(base, token)
            self.assertTrue(kind.startswith('text/csv'))
            self.assertEqual(list(rows[0]), ['id', 'kind', 'name', 'definition', 'confirmed_by', 'confirmed_at', 'data_versions', 'other_names'])
            listed = [e for e in self.standing(Client(base), token)['definitions'] if e['confirmed']]
            self.assertEqual([r['id'] for r in rows], [e['id'] for e in listed])   # the same list, the confirmed ones only
            self.assertNotIn('含税金额', json.dumps(rows, ensure_ascii=False))
            by_id = {r['id']: r for r in rows}
            self.assertEqual(by_id['enum:order:状态码']['definition'], '0 = 已交付、1 = 生产中、2 = 已取消')
            self.assertEqual((by_id['objtype:order']['confirmed_by'], by_id['objtype:order']['data_versions']), ('Bob', '订单 v1'))
            self.assertIn('已取消', by_id['derived:customer:cancelled_orders']['definition'])
            # a column whose values may not go to a model: its meanings and the sentence that spells them out are left blank, the standing stays
            self.assertEqual(ann.post('/api/workspace/types/privacy', {'id': 'order', 'column': '状态码', 'hide_values': True})[0], 200)
            by_id = {r['id']: r for r in self.sheet(base, token)[1]}
            self.assertEqual((by_id['enum:order:状态码']['definition'], by_id['enum:order:状态码']['confirmed_by']), ('', 'Bob'))
            self.assertEqual(by_id['derived:customer:cancelled_orders']['definition'], '')
            self.assertNotIn('已取消', ' '.join(r['definition'] for r in by_id.values()))   # in no sentence (a name such as 客户.已取消订单数 is listed, as describe_definitions lists it)
            self.assertNotIn('objview:有效订单', by_id)   # a view on that column is out of the scope, as in describe_definitions


class StandingToolTests(StandingCase):
    def test_the_mcp_tool_reads_the_same_standing_and_is_a_read_tool(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, admin = team['ann'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)
            token = self.token_for(admin, 'bob')['token']
            self.assertIn('definition_standing', mcp_server.READ_TOOLS)
            replies = self.mcp(base, token, [('definition_standing', {}), ('definition_standing', {'id': GROSS_ID}), ('definition_standing', {'id': 'objtype:nothing'})])
            tool = next(t for t in replies[2]['result']['tools'] if t['name'] == 'definition_standing')
            self.assertTrue(tool['description'].startswith(mcp_server.SCOPE_TEAM))
            self.assertIn('可以重试', tool['description'])
            self.assertIn('describe_definitions', tool['description'])   # names the look-alike tools
            self.assertIn('list_unconfirmed', tool['description'])
            self.assertEqual(self.payload(replies[10])['definitions'], self.standing(Client(base), token)['definitions'])
            self.assertEqual(self.payload(replies[11]), self.standing(Client(base), token, GROSS_ID))
            self.assertTrue(replies[12]['result']['isError'])

    def test_the_skill_folder_says_it_is_a_snapshot_and_names_the_live_standing(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            skill = zipfile.ZipFile(io.BytesIO(self.download(team['bob'])[2])).read('ontopoc-definitions/SKILL.md').decode('utf-8')
            self.assertIn('快照', skill)
            self.assertIn(STANDING, skill)
            self.assertIn('definition_standing', skill)
