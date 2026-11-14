"""What an outside agent can reach, tested end to end: an admin makes a token for a named person, the MCP server runs as a real subprocess against the real service with
that token, and the agent gets the confirmed meaning or a refusal, never a guess. Also the skill folder: confirmed definitions only, no row, nothing unconfirmed.
Acceptance of stage 6: "An outside agent asking through MCP gets the confirmed meaning or a refusal, not a guess." The model is a fake that writes the query it is told to."""
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.request import Request, urlopen
import zipfile

from ontology_poc_generator import mcp_server
from tests.test_explorer import CUSTOMERS, ORDERS, UseLayerCase
from tests.test_derived_properties import GROSS
from tests.test_workspace_questions import AskModel, QUESTION, cancelled

SRC = str(Path(mcp_server.__file__).resolve().parents[1])
ASKS_GROSS = '订单的含税金额合计是多少？'


class AgentCase(UseLayerCase):
    def token_for(self, admin, name, label='外部智能体', **more):
        """An admin makes a token for `name` (more: scope, days)."""
        ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
        status, made = admin.post('/api/users/tokens', {'user_id': ids[name], 'label': label, **more})
        self.assertEqual(status, 200, made)
        return made

    def mcp(self, base, token, calls, toolset='read'):
        """Starts the MCP server as the subprocess an agent would start, sends initialize and these tools/call requests, returns {id: result} (ids from 10).
        toolset None leaves ONTOPOC_TOOLSET unset and token None leaves ONTOPOC_TOKEN unset, to see the server's own defaults."""
        messages = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '0'}}},
                    {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
                    *({'jsonrpc': '2.0', 'id': 10 + i, 'method': 'tools/call', 'params': {'name': name, 'arguments': args}} for i, (name, args) in enumerate(calls))]
        env = {k: v for k, v in {**os.environ, 'PYTHONPATH': SRC, 'ONTOPOC_URL': base, 'ONTOPOC_TOKEN': token, 'ONTOPOC_TOOLSET': toolset}.items() if v is not None}
        done =subprocess.run([sys.executable, '-m', 'ontology_poc_generator.mcp_server'], input='\n'.join(json.dumps(m, ensure_ascii=False) for m in messages) + '\n',
                              capture_output=True, text=True, env=env, timeout=120, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        return {r['id']: r for r in (json.loads(line) for line in done.stdout.splitlines() if line.strip())}

    @staticmethod
    def payload(reply):
        return reply['result']['structuredContent']

    def download(self, client, path='/api/workspace/agent/skill'):
        request = Request(client.base + path, headers={'Cookie': f'{client.cookie_name}={client.cookie}'})
        with urlopen(request, timeout=30) as response:
            return response.status, response.headers, response.read()


class TokenTests(AgentCase):
    def test_an_admin_makes_a_token_that_acts_as_a_named_person_it_is_shown_once_kept_hashed_and_revocable(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            admin, bob, vera = team['admin'], team['bob'], team['vera']
            self.assertEqual(bob.post('/api/users/tokens', {'user_id': 1, 'label': 'x'})[0], 403)   # only an admin makes one
            self.assertEqual(vera.get('/api/users/tokens')[0], 403)
            self.assertEqual(admin.post('/api/users/tokens', {'user_id': 999, 'label': 'x'})[1]['error'], '没有这个在用的账号')
            made = self.token_for(admin, 'bob')
            self.assertEqual((made['username'], made['role'], made['label']), ('bob', 'builder', '外部智能体'))
            self.assertTrue(made['token'].startswith('otp_'))
            listed = admin.get('/api/users/tokens')[1]['tokens']
            self.assertEqual([(t['username'], t['label'], t['revoked']) for t in listed], [('bob', '外部智能体', False)])
            self.assertNotIn('token', listed[0])   # the token itself is never listed again
            conn = sqlite3.connect(out / 'workspace.sqlite')
            self.assertNotIn(made['token'], ' '.join(h for (h,) in conn.execute('SELECT token_hash FROM api_token')))   # only its hash is kept
            logged = conn.execute("SELECT who, element_id, after_json FROM log WHERE change = 'token_created'").fetchall()
            self.assertEqual([(w, e) for w, e, _ in logged], [('root', f'user:{made["user_id"]}')])   # the log says who made it, and for whom, with what it may do and until when
            self.assertEqual(json.loads(logged[0][2]), {'label': '外部智能体', 'for': 'bob', 'scope': 'read', 'expires_at': made['expires_at']})
            conn.close()
            # it acts as Bob: the service signs what it does with his name, and it has his role
            request = Request(base + '/api/auth/me', headers={'Authorization': f'Bearer {made["token"]}'})
            with urlopen(request, timeout=30) as response:
                self.assertEqual(json.load(response)['user']['username'], 'bob')
            # a token cannot make tokens, and a revoked one opens nothing
            self.assertEqual(admin.post('/api/users/tokens/revoke', {'id': made['id']})[0], 200)
            self.assertEqual(admin.get('/api/users/tokens')[1]['tokens'][0]['revoked'], True)
            self.assertEqual(admin.post('/api/users/tokens/revoke', {'id': made['id']})[1]['error'], '没有这个令牌')
            replies = self.mcp(base, made['token'], [('list_unconfirmed', {})])
            self.assertTrue(replies[10]['result']['isError'])
            self.assertEqual(replies[10]['result']['content'][0]['text'], '请先登录')


class McpTests(AgentCase):
    def test_an_outside_agent_gets_the_confirmed_meaning_or_a_refusal_not_a_guess(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, admin = team['ann'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)   # 含税金额 is put forward and nobody has confirmed it
            token = self.token_for(admin, 'bob')['token']
            customer = CUSTOMERS[0]
            cancelled_by_customer = sum(r['客户编号'] == customer['客户编号'] and r['状态码'] == '2' for r in ORDERS)
            replies = self.mcp(base, token, [
                ('describe_definitions', {}), ('ask', {'question': QUESTION}), ('ask', {'question': ASKS_GROSS}), ('list_unconfirmed', {}),
                ('read_derived_property', {'type': 'customer', 'name': 'cancelled_orders', 'key': {'客户编号': customer['客户编号'], '城市': customer['城市']}}),
                ('read_derived_property', {'type': 'order', 'name': 'gross'}), ('read_derived_property', {'type': 'customer', 'name': 'cancelled_orders', 'page': 1}),
                ('read_derived_property', {'type': 'customer', 'name': 'cancelled_orders', 'key': {'客户编号': 'NOPE', '城市': 'x'}})])
            self.assertEqual(replies[1]['result']['serverInfo']['name'], 'ontopoc')
            self.assertEqual(sorted(t['name'] for t in replies[2]['result']['tools']), sorted(mcp_server.READ_TOOLS))   # no uploading, no confirming, no writing
            # the confirmed meaning
            defined = self.payload(replies[10])
            order = next(t for t in defined['types'] if t['id'] == 'order')
            self.assertEqual(order['meanings']['状态码']['values'], {'0': '已交付', '1': '生产中', '2': '已取消'})
            self.assertEqual((order['meanings']['状态码']['confirmed_by'], order['meanings']['状态码']['confirmed_on']), ('Bob', '订单 v1'))
            self.assertEqual([v['line'] for v in defined['views']], ['状态码 不是 2（已取消）：算进 0 已交付、1 生产中，Bob 确认于 订单 v1'])
            self.assertEqual([d['id'] for d in defined['derived']], ['cancelled_orders'])   # not 含税金额
            self.assertNotIn('含税金额', json.dumps(defined, ensure_ascii=False))
            self.assertGreaterEqual(len(defined['rules']), 5)
            answered = self.payload(replies[11])
            self.assertEqual((answered['status'], answered['answer']['total']), ('answered', 16))
            self.assertEqual([(d['kind'], d['name'], d['confirmed_by']) for d in answered['definitions']], [('type', '订单', 'Bob'), ('meaning', '订单.状态码', 'Bob')])
            # a refusal: the question names a definition nobody confirmed; the model is not asked and no number comes back
            asked_before = len(model.requests)
            refused = self.payload(replies[12])
            self.assertEqual(refused['status'], 'refused')
            self.assertEqual(refused['refusal']['kind'], 'unsettled')
            self.assertIn('含税金额', refused['reason'])
            self.assertNotIn('answer', refused)
            self.assertEqual(asked_before, 1)   # only the answered question reached the model
            # what is not confirmed, to be told to the person
            unconfirmed = self.payload(replies[13])['unconfirmed']
            self.assertEqual([(u['kind'], u['name'], u['state']) for u in unconfirmed], [('derived', '订单.含税金额', 'checked')])
            self.assertIn('不要拿它们回答', self.payload(replies[13])['note'])
            # a confirmed derived property gives its value; one nobody confirmed gives none
            one = self.payload(replies[14])
            self.assertEqual((one['total'], one['objects'][0]['value'], one['confirmed_by']), (1, cancelled_by_customer, 'Bob'))
            page = self.payload(replies[16])
            self.assertEqual(page['total'], len(CUSTOMERS))
            self.assertEqual(sum(int(o['value']) for o in page['objects']), sum(r['状态码'] == '2' for r in ORDERS if r['客户编号'] in {c['客户编号'] for c in CUSTOMERS}))
            no_value = replies[15]['result']
            self.assertTrue(no_value['isError'])
            self.assertIn('含税金额', no_value['content'][0]['text'])
            self.assertIn('不是已确认的状态', no_value['content'][0]['text'])
            self.assertEqual(replies[17]['result']['content'][0]['text'], '没有这个对象')

    def test_the_agent_sees_what_the_token_s_person_sees_and_a_viewer_is_told_of_nothing_unconfirmed(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, admin = team['ann'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            rules = [{'column': '客户编号', 'value': 'KH026', 'user_ids': [ids['vera']]}, {'column': '', 'value': '', 'user_ids': [ids['ann'], ids['bob']]}]
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'customer', 'rules': rules})[0], 200)
            token = self.token_for(admin, 'vera')['token']
            page = self.payload(self.mcp(base, token, [('read_derived_property', {'type': 'customer', 'name': 'cancelled_orders'})])[10])
            self.assertEqual((page['total'], page['rows_limited']), (1, True))   # her rows only
            self.assertEqual(rules[0]['value'], page['objects'][0]['key']['客户编号'])
            self.assertEqual(ann.post('/api/workspace/types/privacy', {'id': 'order', 'column': '状态码', 'hide_values': True})[0], 200)   # a column whose values may not go to a model
            replies = self.mcp(base, token, [('describe_definitions', {}), ('list_unconfirmed', {}), ('read_derived_property', {'type': 'customer', 'name': 'cancelled_orders'})])
            defined = self.payload(replies[10])
            order = next(t for t in defined['types'] if t['id'] == 'order')
            self.assertEqual(order['meanings'], {})   # the meanings of a column marked "don't send values" are not given to a model
            self.assertEqual([(d['id'], d['says']) for d in defined['derived']], [('cancelled_orders', None)])   # listed, so the agent can read it; the sentence naming the kept-back meaning is not given            self.assertEqual(self.payload(replies[11])['unconfirmed'], [])
            self.assertTrue(replies[12]['result']['isError'])   # it reads the kept-back column in its condition: listed above, not read out
            self.assertIn('不对模型开放', replies[12]['result']['content'][0]['text'])

    def test_the_full_toolset_still_has_the_run_tools_and_the_read_tools_are_in_it(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            token = self.token_for(team['admin'], 'bob', scope='all')['token']
            names = {t['name'] for t in self.mcp(base, token, [], toolset='all')[2]['result']['tools']}
            self.assertTrue(set(mcp_server.READ_TOOLS) <= names)
            self.assertIn('build_ontology', names)


class SkillTests(AgentCase):
    def test_the_skill_folder_holds_confirmed_definitions_and_refusal_rules_and_nothing_else(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)
            status, headers, body = self.download(bob)
            self.assertEqual((status, headers['Content-Type']), (200, 'application/zip'))
            self.assertIn("filename*=UTF-8''ontopoc-definitions.zip", headers['Content-Disposition'])
            z = zipfile.ZipFile(io.BytesIO(body))
            files = {n: z.read(n).decode('utf-8') for n in z.namelist()}
            self.assertEqual(sorted(files), sorted(f'ontopoc-definitions/{n}' for n in (
                'SKILL.md', 'refusal-rules.md', 'definitions/definitions.json', 'definitions/relations.md', 'definitions/views.md', 'definitions/derived.md',
                *(f'definitions/{t}.md' for t in ('order', 'customer', 'product', 'stock', 'commit', 'ticket')))))
            skill = files['ontopoc-definitions/SKILL.md']
            self.assertTrue(skill.startswith('---\nname: ontopoc-definitions\ndescription: '))
            self.assertIn('[订单](definitions/order.md)', skill)
            self.assertIn('refusal-rules.md', skill)
            self.assertIn('状态码：0 = 已交付、1 = 生产中、2 = 已取消（Bob 确认于 订单 v1）', files['ontopoc-definitions/definitions/order.md'])
            self.assertIn('剔除 状态码 = 2（已取消），Bob 确认于 订单 v1', files['ontopoc-definitions/definitions/views.md'])
            self.assertIn('已取消订单数', files['ontopoc-definitions/definitions/derived.md'])
            self.assertIn('不要猜', files['ontopoc-definitions/refusal-rules.md'])
            everything = '\n'.join(files.values())
            self.assertNotIn('含税金额', everything)   # put forward, not confirmed: not in the folder
            self.assertNotIn(ORDERS[0]['订单号'], everything)   # no row of the data
            self.assertNotIn(ORDERS[0]['客户编号'] + '"', everything)
            as_json = json.loads(files['ontopoc-definitions/definitions/definitions.json'])
            self.assertEqual(sorted(as_json), ['derived', 'relations', 'types', 'views'])
            # a viewer may not download it; after a shifted upload nothing that needs a look is in it
            self.assertEqual(vera.get('/api/workspace/agent/skill')[0], 403)

    def test_what_stops_being_confirmed_leaves_the_folder_at_the_next_export(self):
        from tests.test_object_types import shifted_orders_csv
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            before = zipfile.ZipFile(io.BytesIO(self.download(bob)[2]))
            self.assertIn('ontopoc-definitions/definitions/order.md', before.namelist())
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            after = zipfile.ZipFile(io.BytesIO(self.download(bob)[2]))
            self.assertNotIn('ontopoc-definitions/definitions/order.md', after.namelist())
            text = '\n'.join(after.read(n).decode('utf-8') for n in after.namelist())
            self.assertNotIn('有效订单', text)
            self.assertNotIn('已取消', text)

    def test_the_agent_page_lists_the_tools_and_the_skill_and_is_for_builders(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            status, info = team['bob'].get('/api/workspace/agent')
            self.assertEqual(status, 200, info)
            self.assertEqual(sorted(t['name'] for t in info['tools']), sorted(mcp_server.READ_TOOLS))
            self.assertEqual(info['more_with_all'], len(mcp_server.TOOLS) - len(mcp_server.READ_TOOLS))   # what ONTOPOC_TOOLSET=all would add
            ask = next(t for t in info['tools'] if t['name'] == 'ask')
            self.assertEqual(ask['arguments'], [{'name': 'question', 'description': '要问的业务问题', 'required': True}])
            self.assertTrue(Path(info['command']['src']).joinpath('ontology_poc_generator', 'mcp_server.py').is_file())
            self.assertEqual((info['skill']['types'], info['skill']['views'], info['skill']['derived']), (6, 1, 1))
            self.assertEqual(team['vera'].get('/api/workspace/agent')[0], 403)
