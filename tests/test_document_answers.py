"""Answers from confirmed documents (ops/cards/doc-answers.md), on the seeded demo with a scripted model: a builder uploads a document, it waits for a second
person, and once confirmed a question it answers is answered with quotes code found in its passages, each with the document's name and place, under the line
"from the documents, not from the data". What waits is never used and is named only to those who may read it; a builders-only document does not exist for
anyone else; a quote that is not verbatim, or a number that is not in a quote, is refused, never mended; a data question is answered as it always was."""
import base64
import json
import re
import sqlite3
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest import mock

from ontology_poc_generator import document_answers, mcp_server
from ontology_poc_generator.recognition import ModelCompletion
from tests import test_one_number as one
from tests import test_which_ones_main as which
from tests.test_demo_mode import a_guest
from tests.test_demo_view_waits import Seeded
from tests.test_doc_answers_main import CONTRACT

RULES = '''# 质量管理制度

一、来料检验：每批来料到货后由质检部抽检，抽检不合格的整批退回。

二、罚款：检验员漏检造成损失的，按损失金额的20%罚款，单次罚款不超过五千元。

三、记录：检验记录保存三年。
'''
NO_QUERY = {'reasoning': 'test', 'query': None, 'missing': 'ontology'}


class DocModel(one.Scripted):
    """Replies with `reply_for(request)` when it is set (it reads the passages the request carries), otherwise as Scripted; keeps every system prompt too."""
    reply_for = None

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        self.systems.append(system_prompt)
        if self.reply_for is None:
            return super().complete_json(system_prompt=system_prompt, user_prompt=user_prompt, timeout_seconds=timeout_seconds)
        request = json.loads(user_prompt)
        self.requests.append(request)
        return ModelCompletion('test', 'test-model', json.dumps({'questions': [{'question': request['asked'], **self.reply_for(request)}]}, ensure_ascii=False))


def quoting(quote, said=None, prose=None):
    """A reply that answers from the passage holding `quote`, quoting `said` (by default the quote itself, exact). `prose`: a sentence of the model's own beside
    the quotes, which is never shown, returned or kept."""
    def reply(request):
        passage = next(p for p in request.get('documents') or [] if quote in p['text'])
        return {**NO_QUERY, 'document_answer': {'quotes': [{'passage': passage['id'], 'quote': quote if said is None else said}], **({'answer': prose} if prose else {})}}
    return reply


LINE_ZH = '以下是文档里的原话，由助手挑选，不是来自数据'
LINE_EN = "These are the documents' own words, chosen by the assistant; not from the data"


def upload(who, text=CONTRACT, filename='供货合同.md', builders_only=False):
    return who.call('POST', '/api/workspace/documents/upload', {'filename': filename, 'content_base64': base64.b64encode(text.encode()).decode(), 'builders_only': builders_only})


class DocumentCase(unittest.TestCase):
    def setUp(self):
        one.setUpModule()
        self.addCleanup(one.tearDownModule)
        self.demo = Seeded().__enter__()
        self.addCleanup(self.demo.__exit__, None, None, None)
        self.demo.model.__class__ = DocModel
        self.demo.model.replies, self.demo.model.systems = [NO_QUERY], []
        self.admin, self.builder, self.guest = self.demo.admin(), self.demo.builder(), a_guest(self.demo.base)

    def put(self, text=CONTRACT, filename='供货合同.md', builders_only=False, confirm=True, by=None):
        status, body = upload(by or self.admin, text, filename, builders_only)
        self.assertEqual(status, 200, body)
        if confirm:
            status, body = self.builder.call('POST', '/api/workspace/documents/confirm', {'id': body['id'], 'version': body['version']})
            self.assertEqual(status, 200, body)
        return body

    def ask(self, who, question, reply=None, reply_for=None):
        self.demo.model.reply_for = reply_for
        self.demo.model.replies = [reply or NO_QUERY]
        asked = len(self.demo.model.requests)
        status, body = who.call('POST', '/api/workspace/ask', {'question': question})
        self.assertEqual(status, 200, body)
        return body, self.demo.model.requests[asked:]


class UploadAndConfirm(DocumentCase):
    def test_an_upload_waits_for_a_second_person_and_a_viewer_sees_it_only_once_confirmed(self):
        status, body = upload(self.admin)
        self.assertEqual(status, 200, body)
        self.assertEqual((body['name'], body['state'], body['version']), ('供货合同.md', 'checked', 1))
        self.assertGreaterEqual(body['passages'], 3)
        self.assertEqual(upload(self.guest)[0], 403)   # a viewer uploads nothing
        self.assertEqual(self.guest.call('GET', '/api/workspace/documents')[1]['documents'], [])
        status, refused = self.admin.call('POST', '/api/workspace/documents/confirm', {'id': body['id'], 'version': body['version']})
        self.assertEqual(status, 403, refused)   # the one who put it forward does not confirm it
        status, confirmed = self.builder.call('POST', '/api/workspace/documents/confirm', {'id': body['id'], 'version': body['version']})
        self.assertEqual((status, confirmed['state'], confirmed['confirmed_by']), (200, 'confirmed', 'Demo builder'))
        [seen] = self.guest.call('GET', '/api/workspace/documents')[1]['documents']
        self.assertEqual((seen['name'], seen['state']), ('供货合同.md', 'confirmed'))
        status, opened = self.guest.call('GET', '/api/workspace/documents/' + body['id'])
        self.assertEqual(status, 200, opened)
        self.assertIn('每逾期一日，按逾期部分货款的0.5%支付违约金', ' '.join(p['text'] for p in opened['passages']))

    def test_documents_in_the_workspace_break_no_other_page(self):
        self.put()
        self.put(RULES, '质量管理制度.md', builders_only=True, confirm=False)
        self.ask(self.admin, '逾期交货怎么罚？', reply_for=quoting('每逾期一日，按逾期部分货款的0.5%支付违约金'))
        for who, paths in ((self.admin, ('/api/workspace/types', '/api/workspace/queue', '/api/workspace/receipt', '/api/workspace/graph/lineage', '/api/workspace/graph/relations',
                                         '/api/workspace/agent/standing', '/api/workspace/agent/definitions', '/api/workspace/agent/unconfirmed', '/api/workspace/ask/tally',
                                         '/api/workspace/tasks', '/api/workspace/notices', '/api/workspace/ask')),
                           (self.guest, ('/api/workspace/types', '/api/workspace/graph/lineage', '/api/workspace/agent/standing', '/api/workspace/agent/definitions', '/api/workspace/ask'))):
            for path in paths:
                status, body = who.call('GET', path)
                self.assertEqual(status, 200, (path, body))
        self.assertEqual(self.admin.call('GET', '/api/workspace/ask/tally')[1]['last_7_days']['answered'], 1)   # an answer from documents is an answer

    def test_a_new_version_sends_the_document_back_and_whoever_changed_it_does_not_confirm_it(self):
        first = self.put()
        answered, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=quoting('每逾期一日，按逾期部分货款的0.5%支付违约金'))
        self.assertEqual(answered['status'], 'from_documents', answered)
        status, again = upload(self.builder, CONTRACT.replace('0.5%', '1%'))   # Demo builder, who confirmed it, changes it
        self.assertEqual((status, again['state'], again['version']), (200, 'checked', first['version'] + 1))   # `first` is as confirmed
        body, requests = self.ask(self.admin, '逾期交货怎么罚？')
        self.assertNotIn('documents', requests[0])   # waiting again: not searched, not sent
        self.assertNotEqual(body['status'], 'from_documents')
        self.assertEqual(self.builder.call('POST', '/api/workspace/documents/confirm', {'id': again['id'], 'version': again['version']})[0], 403)
        self.assertEqual(self.guest.call('GET', '/api/workspace/documents')[1]['documents'], [])
        reopened = self.admin.call('GET', f'/api/workspace/ask/{answered["id"]}')[1]
        self.assertEqual([c['id'] for c in reopened['changed']], [again['id']])   # the answer says the document it quoted is not as it was
        status, confirmed = self.admin.call('POST', '/api/workspace/documents/confirm', {'id': again['id'], 'version': again['version']})
        self.assertEqual((status, confirmed['state']), (200, 'confirmed'), confirmed)

    def test_a_document_too_large_or_of_another_kind_is_refused_and_says_why(self):
        status, body = upload(self.admin, filename='表格.xlsx')
        self.assertEqual(status, 400)
        self.assertIn('.md', body['error'])
        with mock.patch('ontology_poc_generator.document_answers.MAX_CHARS', 100):
            status, body = upload(self.admin)
        self.assertEqual(status, 400)
        self.assertIn('100', body['error'])
        with mock.patch('ontology_poc_generator.document_answers.MAX_DOCUMENTS', 1):
            self.put(confirm=False)
            status, body = upload(self.admin, RULES, '质量管理制度.md')
        self.assertEqual(status, 400, body)
        self.assertIn('1', body['error'])

    def test_without_fts5_the_feature_says_so_and_stays_off(self):
        self.put()
        with mock.patch('ontology_poc_generator.document_answers.fts5_available', lambda: False):
            listing = self.admin.call('GET', '/api/workspace/documents')[1]
            self.assertFalse(listing['available'])
            self.assertIn('FTS5', listing['unavailable'])
            status, body = upload(self.admin, RULES, '质量管理制度.md')
            self.assertEqual(status, 503)
            self.assertIn('FTS5', body['error'])
            body, requests = self.ask(self.admin, '逾期交货怎么罚？')
            self.assertNotIn('documents', requests[0])
            self.assertNotIn('documents', body)


class Answers(DocumentCase):
    QUOTE = '每逾期一日，按逾期部分货款的0.5%支付违约金'

    def test_a_question_the_documents_answer_quotes_its_passages_with_the_documents_name_and_place(self):
        document = self.put()
        for who, line in ((self.admin, LINE_ZH), (self.guest, LINE_ZH), (self.demo.admin('en'), LINE_EN)):
            body, [request] = self.ask(who, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE, prose='违约方不需要支付违约金'))
            self.assertEqual(body['status'], 'from_documents', body)
            self.assertEqual(body['documents']['line'], line)
            self.assertEqual(set(body['documents']), {'line', 'quotes'})   # the documents' own words and where they are, nothing else
            [quote] = body['documents']['quotes']
            self.assertEqual(set(quote), {'passage', 'quote', 'document', 'document_id', 'version', 'where'})
            for kept in (json.dumps(body, ensure_ascii=False), json.dumps(which.kept(self.demo.folder, body['id']), ensure_ascii=False)):
                self.assertNotIn('违约方不需要', kept)   # the model's prose is never shown, returned or kept
            self.assertEqual((quote['quote'], quote['document'], quote['document_id'], quote['version']), (self.QUOTE, '供货合同.md', document['id'], document['version']))   # the version confirmed
            self.assertTrue(quote['where'])
            self.assertNotIn('answer', body)   # never a number from the data
            self.assertEqual((body['types'], body['datasets']), ([], {}))
            self.assertEqual([(d['id'], d['kind']) for d in body['definitions']], [(document['id'], 'document')])
            passages = request['documents']
            self.assertTrue(1 <= len(passages) <= 5)
            self.assertEqual(set(passages[0]), {'id', 'document', 'text'})
            self.assertTrue(all(re.fullmatch(r'\d+-p\d+', p['id']) for p in passages), passages)   # numbered per document, never a row id
            self.assertTrue(any(self.QUOTE in p['text'] for p in passages))
            self.assertIn('document_answer', self.demo.model.systems[-1])
            reopened = who.call('GET', f'/api/workspace/ask/{body["id"]}')[1]
            self.assertEqual((reopened['status'], reopened['documents'], reopened['changed']), ('from_documents', body['documents'], []))

    def test_rows_never_go_to_the_model_with_the_passages(self):
        self.put()
        _, [with_documents] = self.ask(self.admin, '订单的金额一共是多少？逾期交货怎么罚？', reply=one.item(one.SUM_AMOUNT))
        self.assertIn('documents', with_documents)
        with mock.patch('ontology_poc_generator.document_answers.fts5_available', lambda: False):
            _, [without] = self.ask(self.admin, '订单的金额一共是多少？逾期交货怎么罚？', reply=one.item(one.SUM_AMOUNT))
        self.assertEqual({k: v for k, v in with_documents.items() if k != 'documents'}, without)   # the catalog as it always was: names, never a row

    def test_a_two_character_chinese_term_finds_its_passage(self):
        self.put(RULES, '质量管理制度.md')
        body, [request] = self.ask(self.admin, '罚款', reply_for=quoting('按损失金额的20%罚款'))
        self.assertEqual([p['text'] for p in request['documents']][:1], ['二、罚款：检验员漏检造成损失的，按损失金额的20%罚款，单次罚款不超过五千元。'])
        self.assertEqual(body['status'], 'from_documents', body)
        _, [english] = self.ask(self.admin, 'late delivery', reply_for=lambda r: NO_QUERY)
        self.assertNotIn('documents', english)   # the contract is not confirmed in this test: only the rules are searched, and they say nothing in English

    def test_a_quote_that_is_not_verbatim_is_refused_not_mended(self):
        self.put()
        for said in (self.QUOTE.replace('，', ','), self.QUOTE.replace('0.5%', '0.5 %'), self.QUOTE + '。违约金不设上限'):
            body, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE, said=said))
            self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_check'), body)
            self.assertNotIn('documents', body)
            self.assertIn('原文', body['reason'])
            self.assertNotIn('违约金', body['reason'])   # what it quoted is not repeated, here or in what is kept

    def test_a_quote_from_a_passage_the_model_was_not_given_is_refused(self):
        self.put()
        listing = self.admin.call('GET', '/api/workspace/documents/' + self.admin.call('GET', '/api/workspace/documents')[1]['documents'][0]['id'])[1]
        given = lambda request: {p['id'] for p in request['documents']}
        def elsewhere(request):
            other = next(p for p in listing['passages'] if p['id'] not in given(request))
            return {**NO_QUERY, 'document_answer': {'quotes': [{'passage': other['id'], 'quote': other['text'][:10]}]}}
        body, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=elsewhere)
        self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_check'), body)

    def test_a_quote_of_fewer_than_four_characters_that_are_not_punctuation_or_space_is_refused(self):
        self.put()
        for said in ('0.5%', '，；：', '', ' 违约金 ', '0.5%，'):
            body, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE, said=said))
            self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_check'), (said, body))
        body, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE, said='支付违约金'))
        self.assertEqual(body['status'], 'from_documents', body)

    def test_an_answer_in_the_old_shape_with_claims_is_refused(self):
        self.put()
        def claims(request):
            passage = next(p for p in request['documents'] if self.QUOTE in p['text'])
            return {**NO_QUERY, 'document_answer': {'claims': [{'text': '违约金是百分之五', 'quotes': [{'passage': passage['id'], 'quote': self.QUOTE}]}]}}
        body, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=claims)
        self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_check'), body)
        self.assertNotIn('百分之五', json.dumps(body, ensure_ascii=False))

    def test_a_quote_checked_against_its_own_passage_not_another(self):
        self.put()
        def crossed(request):
            holding = next(p for p in request['documents'] if self.QUOTE in p['text'])
            other = next(p for p in request['documents'] if p['id'] != holding['id'])
            return {**NO_QUERY, 'document_answer': {'quotes': [{'passage': other['id'], 'quote': self.QUOTE}]}}
        body, [request] = self.ask(self.admin, '逾期交货怎么罚？订单付款', reply_for=crossed)
        self.assertGreaterEqual(len(request['documents']), 2)
        self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_check'), body)

    def test_at_most_five_passages_go_to_the_model(self):
        self.put('# 罚则\n\n' + '\n\n'.join(f'第{i}条 迟到罚款{i}0元。' for i in range(1, 9)), '罚则.md')
        _, [request] = self.ask(self.admin, '罚款')
        self.assertEqual(len(request['documents']), 5)

    def test_a_data_question_is_answered_as_without_documents_and_its_document_answer_is_ignored(self):
        reply = {**one.item(one.SUM_AMOUNT), 'document_answer': {'quotes': [{'passage': '1-p2', 'quote': self.QUOTE}]}}
        before, _ = self.ask(self.admin, '订单的金额一共是多少？', reply=reply)
        self.put()
        after, [request] = self.ask(self.admin, '订单的金额一共是多少？', reply=reply)
        self.assertIn('documents', request)   # 订单 and 金额 are in the contract: its passages were sent
        drop = lambda body: {k: v for k, v in body.items() if k not in ('id', 'asked_at')}
        self.assertEqual(drop(after), drop(before))
        self.assertEqual(after['status'], 'answered')

    def test_a_reply_with_any_query_is_never_answered_from_documents(self):
        """A query the engine cannot read (here text where a structured query goes) is still the model saying it is a data question: main's answer, the document answer ignored."""
        self.put()
        def written(request):
            return {**quoting(self.QUOTE)(request), 'query': 'SELECT count(o) FROM (o:Order)'}
        body, [request] = self.ask(self.admin, '逾期交货怎么罚？', reply_for=written)
        self.assertIn('documents', request)
        self.assertNotEqual(body['status'], 'from_documents')
        self.assertNotIn('documents', body)
        self.assertNotIn('确认过的文档', body['reason'])

    def test_nothing_found_is_said_plainly(self):
        self.put()
        body, [request] = self.ask(self.admin, '火星上的天气怎么样？')
        self.assertNotIn('documents', request)
        self.assertEqual(body['documents']['line'], '确认过的文档里没有说到这件事。')
        self.assertTrue(body['reason'].startswith('确认过的文档里没有说到这件事。\n'), body['reason'])   # the service's sentence, then on a line of its own what main says
        body, _ = self.ask(self.demo.admin('en'), 'What is the weather on Mars?')
        self.assertTrue(body['reason'].startswith('The confirmed documents say nothing about this.\n'), body['reason'])

    def test_nothing_is_said_of_documents_when_the_asker_may_read_no_confirmed_one(self):
        self.put(confirm=False)   # only a document that waits, and the question does not match it
        body, [request] = self.ask(self.builder, '火星上的天气怎么样？')
        self.assertNotIn('documents', request)
        self.assertNotIn('documents', body)
        self.assertNotIn('确认过的文档', body['reason'])

    def test_an_answer_from_the_relation_check_is_never_replaced_by_a_document_answer(self):
        docs = {'readable': True, 'waiting': [], 'passages': [{'id': '1-p2', 'element_id': 'document:x', 'document': 'x.md', 'version': 2, 'confirmed_by': 'b', 'where': 'p', 'text': self.QUOTE}]}
        item = {'query': None, 'status': 'query_limit', 'from_relation_check': True, 'document_answer': {'quotes': [{'passage': '1-p2', 'quote': self.QUOTE}]}}
        result = {'status': 'query_limit', 'reason': 'relation check'}
        self.assertIs(document_answers.settled(None, None, docs, item, result), result)


class Waiting(DocumentCase):
    def test_a_document_that_waits_is_not_used_and_the_refusal_names_it_and_who_can_confirm_it(self):
        self.put(confirm=False)   # demo-admin put it forward: Demo builder can confirm it
        body, [request] = self.ask(self.builder, '逾期交货怎么罚？')
        self.assertNotIn('documents', request)
        self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_unconfirmed'), body)
        [named] = body['refusal']['documents']
        self.assertEqual((named['name'], named['who_can_confirm']), ('供货合同.md', ['Demo builder']))
        self.assertIn('供货合同.md', body['reason'])
        self.assertIn('Demo builder', body['reason'])
        guest, [request] = self.ask(self.guest, '逾期交货怎么罚？')   # a viewer may not read what waits: nothing of it is said
        self.assertNotIn('documents', request)
        self.assertNotIn('供货合同', json.dumps(guest, ensure_ascii=False))
        self.assertEqual(guest['status'], 'ontology_gap')

    def test_a_data_question_is_not_held_up_by_a_document_that_waits(self):
        self.put(confirm=False)
        body, _ = self.ask(self.builder, '订单的金额一共是多少？', reply=one.item(one.SUM_AMOUNT))
        self.assertEqual(body['status'], 'answered')
        self.assertNotIn('documents', body)


class BuildersOnly(DocumentCase):
    def test_a_builders_only_document_does_not_exist_for_a_viewer(self):
        document = self.put(builders_only=True)
        self.put(RULES, '质量管理制度.md')   # one the guest may read, so they too are told "the confirmed documents say nothing" when nothing matches
        self.assertEqual([d['name'] for d in self.guest.call('GET', '/api/workspace/documents')[1]['documents']], ['质量管理制度.md'])
        self.assertEqual(self.guest.call('GET', '/api/workspace/documents/' + document['id'])[0], 404)
        drop = lambda body: {k: v for k, v in body.items() if k not in ('id', 'asked_at', 'question')}
        its_words, [request] = self.ask(self.guest, '逾期交货怎么罚？', reply_for=lambda r: NO_QUERY)
        self.assertNotIn('documents', request)
        no_words, _ = self.ask(self.guest, '火星上的天气怎么样？', reply_for=lambda r: NO_QUERY)
        self.assertEqual(drop(its_words), drop(no_words))
        body, [request] = self.ask(self.builder, '逾期交货怎么罚？', reply_for=quoting(Answers.QUOTE))
        self.assertEqual(body['status'], 'from_documents', body)

    def test_a_builders_only_document_that_waits_is_not_named_to_a_viewer(self):
        self.put(builders_only=True, confirm=False)
        guest, _ = self.ask(self.guest, '逾期交货怎么罚？')
        self.assertNotIn('供货合同', json.dumps(guest, ensure_ascii=False))
        builder, _ = self.ask(self.builder, '逾期交货怎么罚？')
        self.assertEqual(builder['refusal']['kind'], 'document_unconfirmed')


class Agent(DocumentCase):
    def test_the_mcp_ask_tool_carries_a_document_answer_in_the_same_structure(self):
        self.put()
        body, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=quoting(Answers.QUOTE))

        class Session:
            def request(self, path, payload=None):
                return body
        got = mcp_server.ask(Session(), {'question': '逾期交货怎么罚？'})
        self.assertEqual((got['status'], got['documents']), ('from_documents', body['documents']))



class SendBackAndRemove(DocumentCase):
    """Round 2: a confirmed document that turns out wrong stops answering, sent back to waiting or removed."""
    QUOTE = Answers.QUOTE

    def send_back(self, who, document, reason='第五条的比例写错了'):
        return who.call('POST', '/api/workspace/documents/send-back', {'id': document['id'], 'version': document['version'], 'reason': reason})

    def remove(self, who, document, reason='合同已作废'):
        return who.call('POST', '/api/workspace/documents/remove', {'id': document['id'], 'version': document['version'], 'reason': reason})

    def test_a_document_sent_back_leaves_search_at_once_and_waits_for_a_second_confirmation(self):
        document = self.put()   # demo-admin put it forward, Demo builder confirmed it
        self.assertEqual(self.send_back(self.builder, document, reason='')[0], 400)   # a reason is needed
        status, back = self.send_back(self.builder, document)
        self.assertEqual((status, back['state'], back['reason']), (200, 'needs_look', '第五条的比例写错了'), back)
        self.assertEqual(self.send_back(self.builder, back)[0], 409)   # only a confirmed document is sent back
        body, [request] = self.ask(self.builder, '逾期交货怎么罚？')
        self.assertNotIn('documents', request)   # out of search at once
        self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_unconfirmed'), body)
        self.assertEqual(body['refusal']['documents'][0]['name'], '供货合同.md')
        guest, [request] = self.ask(self.guest, '逾期交货怎么罚？')   # a viewer never sees its name
        self.assertNotIn('documents', request)
        self.assertNotIn('供货合同', json.dumps(guest, ensure_ascii=False))
        self.assertEqual(self.guest.call('GET', '/api/workspace/documents')[1]['documents'], [])
        self.assertEqual(self.guest.call('GET', '/api/workspace/documents/' + document['id'])[0], 404)
        [listed] = self.admin.call('GET', '/api/workspace/documents')[1]['documents']
        self.assertEqual((listed['state'], listed['reason']), ('needs_look', '第五条的比例写错了'))
        status, refused = self.admin.call('POST', '/api/workspace/documents/confirm', {'id': back['id'], 'version': back['version']})
        self.assertEqual(status, 403, refused)   # who put it forward still does not confirm it
        status, again = self.builder.call('POST', '/api/workspace/documents/confirm', {'id': back['id'], 'version': back['version']})
        self.assertEqual((status, again['state']), (200, 'confirmed'), again)
        body, _ = self.ask(self.guest, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE))
        self.assertEqual(body['status'], 'from_documents', body)
        log = sqlite3.connect(self.demo.folder / 'workspace.sqlite').execute("SELECT who, change, after_json FROM log WHERE element_id = ? AND change = 'sent_back'", (document['id'],)).fetchall()
        self.assertEqual([(who, change) for who, change, _ in log], [('Demo builder', 'sent_back')])
        self.assertIn('第五条的比例写错了', log[0][2])

    def test_a_sent_back_document_changed_since_is_not_confirmed_by_whoever_changed_it(self):
        document = self.put()
        status, back = self.send_back(self.builder, document)
        self.assertEqual(status, 200, back)
        status, changed = upload(self.builder, CONTRACT.replace('0.5%', '1%'))   # Demo builder corrects it
        self.assertEqual((status, changed['state']), (200, 'checked'), changed)
        self.assertEqual(self.builder.call('POST', '/api/workspace/documents/confirm', {'id': changed['id'], 'version': changed['version']})[0], 403)
        self.assertEqual(self.admin.call('POST', '/api/workspace/documents/confirm', {'id': changed['id'], 'version': changed['version']})[0], 200)

    def test_a_removed_document_leaves_search_and_the_index_its_answers_reopen_refused_and_its_name_may_come_again(self):
        document = self.put()
        admin_answer, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE))
        guest_answer, _ = self.ask(self.guest, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE))
        self.assertEqual((admin_answer['status'], guest_answer['status']), ('from_documents', 'from_documents'))
        self.assertEqual(self.remove(self.builder, document, reason='')[0], 400)
        status, removed = self.remove(self.builder, document)
        self.assertEqual(status, 200, removed)
        conn = sqlite3.connect(self.demo.folder / 'workspace.sqlite')
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM doc_passage').fetchone()[0], 0)
        for index in ('doc_terms_all', 'doc_terms_builders', 'doc_terms_waiting'):   # one index per level of visibility
            self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {index} WHERE {index} MATCH '\"逾期\"'").fetchone()[0], 0, index)
        self.assertEqual(conn.execute("SELECT who, change FROM log WHERE element_id = ? AND change = 'removed'", (document['id'],)).fetchall(), [('Demo builder', 'removed')])
        body, [request] = self.ask(self.builder, '逾期交货怎么罚？')
        self.assertNotIn('documents', request)
        self.assertNotIn('documents', body)   # it is not there: no refusal names it, no "documents say nothing" (none is left)
        listing = self.admin.call('GET', '/api/workspace/documents')[1]
        self.assertEqual(listing['documents'], [])
        [gone] = listing['removed']
        self.assertEqual((gone['name'], gone['removed_by'], gone['reason']), ('供货合同.md', 'Demo builder', '合同已作废'))
        self.assertNotIn('供货合同', json.dumps(self.guest.call('GET', '/api/workspace/documents')[1], ensure_ascii=False))
        self.assertEqual(self.admin.call('GET', '/api/workspace/documents/' + document['id'])[0], 404)
        reopened = self.admin.call('GET', f'/api/workspace/ask/{admin_answer["id"]}')[1]
        self.assertEqual(reopened['withheld']['documents'], ['供货合同.md'])
        self.assertIn('已移除', reopened['reason'])
        self.assertNotIn(self.QUOTE, json.dumps(reopened, ensure_ascii=False))
        self.assertNotIn('documents', reopened)
        reopened = self.guest.call('GET', f'/api/workspace/ask/{guest_answer["id"]}')[1]
        self.assertEqual(reopened['withheld']['documents'], [])
        self.assertIn('已移除', reopened['reason'])
        self.assertNotIn('供货合同', json.dumps(reopened, ensure_ascii=False))
        english = self.demo.admin('en').call('GET', f'/api/workspace/ask/{admin_answer["id"]}')[1]
        self.assertIn('removed', english['reason'])
        status, fresh = upload(self.admin)
        self.assertEqual((status, fresh['state'], fresh['version']), (200, 'checked', 1), fresh)
        self.assertNotEqual(fresh['id'], document['id'])   # a new document: the old one's answers stay refused
        self.assertIn('已移除', self.admin.call('GET', f'/api/workspace/ask/{admin_answer["id"]}')[1]['reason'])

    def test_only_builders_send_back_or_remove(self):
        document = self.put()
        self.assertEqual(self.send_back(self.guest, document)[0], 403)
        self.assertEqual(self.remove(self.guest, document)[0], 403)
        self.assertEqual(self.remove(self.builder, {**document, 'version': document['version'] - 1})[0], 409)


class TokenActs(DocumentCase):
    """The Leader's ruling: sending back takes trust away and is open to a builder's token, logged with the token; removing deletes passages for good and is a
    person's act, refused to a token with its own sentence."""

    def token_call(self, token, path, body, lang='zh-CN'):
        request = Request(self.demo.base + path, method='POST', data=json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}', 'Accept-Language': lang})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def test_a_builders_token_sends_a_document_back_and_the_log_names_the_token(self):
        document = self.put()
        status, made = self.builder.call('POST', '/api/auth/tokens', {'label': '文档代理'})
        self.assertEqual(status, 200, made)
        status, back = self.token_call(made['token'], '/api/workspace/documents/send-back', {'id': document['id'], 'version': document['version'], 'reason': '比例写错了'})
        self.assertEqual((status, back['state']), (200, 'needs_look'), back)
        [(who, via)] = sqlite3.connect(self.demo.folder / 'workspace.sqlite').execute("SELECT who, via_token FROM log WHERE element_id = ? AND change = 'sent_back'", (document['id'],)).fetchall()
        self.assertEqual((who, via), ('Demo builder', '文档代理'))

    def test_removing_a_document_is_refused_to_a_token_with_its_own_sentence(self):
        document = self.put()
        status, made = self.builder.call('POST', '/api/auth/tokens', {'label': '文档代理'})
        self.assertEqual(status, 200, made)
        for lang, words in (('zh-CN', '移除文档要由本人登录页面来做'), ('en', 'Removing a document is done by a person signed in to the page')):
            status, body = self.token_call(made['token'], '/api/workspace/documents/remove', {'id': document['id'], 'version': document['version'], 'reason': '作废'}, lang)
            self.assertEqual((status, body.get('needs_person')), (403, True), body)
            self.assertIn(words, body['error'])
        self.assertEqual(len(self.admin.call('GET', '/api/workspace/documents')[1]['documents']), 1)   # still there


VISIBLE = '# 规定\n\n甲、罚款五千元。\n\n乙、检验按批次进行，每一批来料都要抽样，抽样不合格的整批退回给供应商处理。\n'
HIDDEN = '# 内部\n\n' + '\n\n'.join(f'第{i}项 罚款事项{i}' for i in range(1, 21)) + '\n'


class Round3(DocumentCase):
    QUOTE = Answers.QUOTE

    def test_what_a_viewers_model_is_offered_does_not_depend_on_documents_they_may_not_read(self):
        self.put(VISIBLE, '规定.md')
        _, [before] = self.ask(self.guest, '罚款和检验')
        self.put(HIDDEN, '内部.md', builders_only=True)
        self.put(HIDDEN.replace('内部', '草稿'), '草稿.md', confirm=False)
        _, [after] = self.ask(self.guest, '罚款和检验')
        self.assertEqual(json.dumps(after['documents'], ensure_ascii=False), json.dumps(before['documents'], ensure_ascii=False))   # the same passages, order and ids
        _, [builder] = self.ask(self.builder, '罚款和检验')
        self.assertIn('内部.md', {p['document'] for p in builder['documents']})
        listed = {d['name']: d['id'] for d in self.admin.call('GET', '/api/workspace/documents')[1]['documents']}
        for name in ('规定.md', '内部.md'):
            passages = self.admin.call('GET', '/api/workspace/documents/' + listed[name])[1]['passages']
            self.assertEqual([p['id'] for p in passages], [f'p{i}' for i in range(1, len(passages) + 1)])   # numbered per document

    def test_a_document_removed_while_a_question_is_answered_is_refused_as_removed(self):
        document = self.put()
        def removed_meanwhile(request):
            reply = quoting(self.QUOTE)(request)
            assert self.builder.call('POST', '/api/workspace/documents/remove', {'id': document['id'], 'version': document['version'], 'reason': '作废'})[0] == 200
            return reply
        body, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=removed_meanwhile)
        self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_removed'), body)
        self.assertNotIn(self.QUOTE, json.dumps(body, ensure_ascii=False))

    def test_a_document_sent_back_while_a_question_is_answered_is_refused_as_waiting_and_never_shown_as_confirmed(self):
        for who, named in ((self.admin, True), (self.guest, False)):
            document = self.put(filename=f'供货合同{int(named)}.md')
            def sent_back_meanwhile(request, document=document):
                reply = quoting(self.QUOTE)(request)
                assert self.builder.call('POST', '/api/workspace/documents/send-back', {'id': document['id'], 'version': document['version'], 'reason': '有误'})[0] == 200
                return reply
            body, _ = self.ask(who, '逾期交货怎么罚？', reply_for=sent_back_meanwhile)
            self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_unconfirmed'), body)
            self.assertNotIn(self.QUOTE, json.dumps(body, ensure_ascii=False))
            self.assertEqual('供货合同' in json.dumps(body, ensure_ascii=False), named)   # a viewer is never told its name

    def test_a_kept_refusal_of_a_document_answer_keeps_no_quoted_text_and_reopens_withheld_when_the_document_is_out_of_reach(self):
        document = self.put()
        body, _ = self.ask(self.guest, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE, said=self.QUOTE + '，违约金不设上限'))
        self.assertEqual(body['refusal']['kind'], 'document_check')
        self.assertEqual(body['refusal']['documents'], [document['id']])   # the documents it read
        kept = json.dumps(which.kept(self.demo.folder, body['id']), ensure_ascii=False)
        self.assertNotIn('违约金', kept)
        self.assertEqual(upload(self.admin, builders_only=True)[0], 200)   # now for builders only, and waiting
        reopened = self.guest.call('GET', f'/api/workspace/ask/{body["id"]}')[1]
        self.assertIn('withheld', reopened)
        self.assertNotIn('refusal', reopened)

    def test_a_kept_answer_reopens_withheld_for_a_viewer_who_may_no_longer_read_its_document(self):
        self.put()
        body, _ = self.ask(self.guest, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE))
        self.assertEqual(body['status'], 'from_documents')
        self.assertEqual(upload(self.admin, builders_only=True)[0], 200)
        reopened = self.guest.call('GET', f'/api/workspace/ask/{body["id"]}')[1]
        self.assertIn('withheld', reopened)
        self.assertNotIn(self.QUOTE, json.dumps(reopened, ensure_ascii=False))

    def test_confirming_with_a_version_that_moved_is_refused(self):
        status, body = upload(self.admin)
        self.assertEqual(upload(self.admin, CONTRACT.replace('0.5%', '1%'))[0], 200)
        self.assertEqual(self.builder.call('POST', '/api/workspace/documents/confirm', {'id': body['id'], 'version': body['version']})[0], 409)

    def test_without_fts5_remove_and_send_back_answer_503(self):
        document = self.put()
        with mock.patch('ontology_poc_generator.document_answers.fts5_available', lambda: False):
            for path in ('/api/workspace/documents/remove', '/api/workspace/documents/send-back'):
                status, body = self.builder.call('POST', path, {'id': document['id'], 'version': document['version'], 'reason': '作废'})
                self.assertEqual(status, 503, (path, body))
                self.assertIn('FTS5', body['error'])

    def test_a_docx_that_unpacks_too_large_is_refused_before_it_is_read(self):
        import io, zipfile
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + '<w:p><w:r><w:t>罚款</w:t></w:r></w:p>' * 2000 + '</w:body></w:document>')
        with mock.patch('ontology_poc_generator.company_documents.MAX_DOCX_XML', 10_000):
            status, body = self.admin.call('POST', '/api/workspace/documents/upload', {'filename': '大.docx', 'content_base64': base64.b64encode(buffer.getvalue()).decode()})
        self.assertEqual(status, 400, body)
        self.assertIn('10,000', body['error'])

    def test_a_pdf_reader_that_runs_out_of_time_is_a_plain_refusal(self):
        import subprocess
        def too_slow(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], 60)
        with mock.patch('ontology_poc_generator.company_documents.shutil.which', lambda name: '/usr/bin/pdftotext'), \
                mock.patch('ontology_poc_generator.company_documents.subprocess.run', too_slow):
            status, body = self.admin.call('POST', '/api/workspace/documents/upload', {'filename': '慢.pdf', 'content_base64': base64.b64encode(b'%PDF-1.4').decode()})
        self.assertEqual(status, 400, body)
        self.assertIn('60', body['error'])


if __name__ == '__main__':
    unittest.main()
