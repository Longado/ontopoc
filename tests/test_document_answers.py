"""Answers from confirmed documents (ops/cards/doc-answers.md), on the seeded demo with a scripted model: a builder uploads a document, it waits for a second
person, and once confirmed a question it answers is answered with quotes code found in its passages, each with the document's name and place, under the line
"from the documents, not from the data". What waits is never used and is named only to those who may read it; a builders-only document does not exist for
anyone else; a quote that is not verbatim, or a number that is not in a quote, is refused, never mended; a data question is answered as it always was."""
import base64
import json
import unittest
from unittest import mock

from ontology_poc_generator import mcp_server
from ontology_poc_generator.recognition import ModelCompletion
from tests import test_one_number as one
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


def quoting(quote, claim=None, said=None):
    """A reply that answers from the passage holding `quote`: one claim (`claim`, or the quote itself) resting on `said` (the quote as written, by default exact)."""
    def reply(request):
        passage = next(p for p in request.get('documents') or [] if quote in p['text'])
        return {**NO_QUERY, 'document_answer': {'claims': [{'text': claim or quote, 'quotes': [{'passage': passage['id'], 'quote': said or quote}]}]}}
    return reply


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
        for who, line in ((self.admin, '来自文档，不是来自数据'), (self.guest, '来自文档，不是来自数据'), (self.demo.admin('en'), 'From the documents, not from the data')):
            body, [request] = self.ask(who, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE, '逾期交货每逾期一日按逾期部分货款的0.5%支付违约金'))
            self.assertEqual(body['status'], 'from_documents', body)
            self.assertEqual(body['documents']['line'], line)
            [claim] = body['documents']['claims']
            self.assertEqual(claim['text'], '逾期交货每逾期一日按逾期部分货款的0.5%支付违约金')
            [quote] = claim['quotes']
            self.assertEqual((quote['quote'], quote['document'], quote['document_id'], quote['version']), (self.QUOTE, '供货合同.md', document['id'], document['version']))   # the version confirmed
            self.assertTrue(quote['where'])
            self.assertNotIn('answer', body)   # never a number from the data
            self.assertEqual((body['types'], body['datasets']), ([], {}))
            self.assertEqual([(d['id'], d['kind']) for d in body['definitions']], [(document['id'], 'document')])
            passages = request['documents']
            self.assertTrue(1 <= len(passages) <= 5)
            self.assertEqual(set(passages[0]), {'id', 'document', 'text'})
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
            body, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE, '逾期一日按0.5%支付违约金', said=said))
            self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_check'), body)
            self.assertNotIn('claims', json.dumps(body.get('documents') or {}))
            self.assertIn('原文', body['reason'])

    def test_a_quote_from_a_passage_the_model_was_not_given_is_refused(self):
        self.put()
        listing = self.admin.call('GET', '/api/workspace/documents/' + self.admin.call('GET', '/api/workspace/documents')[1]['documents'][0]['id'])[1]
        given = lambda request: {p['id'] for p in request['documents']}
        def elsewhere(request):
            other = next(p for p in listing['passages'] if p['id'] not in given(request))
            return {**NO_QUERY, 'document_answer': {'claims': [{'text': other['text'][:10], 'quotes': [{'passage': other['id'], 'quote': other['text'][:10]}]}]}}
        body, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=elsewhere)
        self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_check'), body)

    def test_a_number_that_is_not_in_a_quote_is_refused(self):
        self.put()
        for claim in ('逾期一日按货款的5%支付违约金', '逾期一日按0.5%支付违约金，上限为合同总价的10%', '逾期五日以上按0.5%支付违约金', '逾期一日按0.50%支付违约金'):
            body, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE, claim))
            self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'document_check'), (claim, body))
            self.assertIn('数字', body['reason'])
        body, _ = self.ask(self.admin, '逾期交货怎么罚？', reply_for=quoting(self.QUOTE, '每逾期一日按逾期部分货款的0.5%支付违约金'))
        self.assertEqual(body['status'], 'from_documents', body)

    def test_a_data_question_is_answered_as_without_documents_and_its_document_answer_is_ignored(self):
        reply = {**one.item(one.SUM_AMOUNT), 'document_answer': {'claims': [{'text': self.QUOTE, 'quotes': [{'passage': 'p1', 'quote': self.QUOTE}]}]}}
        before, _ = self.ask(self.admin, '订单的金额一共是多少？', reply=reply)
        self.put()
        after, [request] = self.ask(self.admin, '订单的金额一共是多少？', reply=reply)
        self.assertIn('documents', request)   # 订单 and 金额 are in the contract: its passages were sent
        drop = lambda body: {k: v for k, v in body.items() if k not in ('id', 'asked_at')}
        self.assertEqual(drop(after), drop(before))
        self.assertEqual(after['status'], 'answered')

    def test_nothing_found_is_said_plainly(self):
        self.put()
        body, [request] = self.ask(self.admin, '火星上的天气怎么样？')
        self.assertNotIn('documents', request)
        self.assertEqual(body['documents']['line'], '确认过的文档里没有说到这件事。')
        self.assertTrue(body['reason'].startswith('确认过的文档里没有说到这件事。'), body['reason'])
        body, _ = self.ask(self.demo.admin('en'), 'What is the weather on Mars?')
        self.assertTrue(body['reason'].startswith('The confirmed documents say nothing about this.'), body['reason'])


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


if __name__ == '__main__':
    unittest.main()
