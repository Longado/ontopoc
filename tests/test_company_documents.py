import io
import json
import unittest
from unittest.mock import patch
import zipfile

from ontology_poc_generator.company_documents import (
    DOCUMENT_PROMPT_VERSION, MAX_CHUNKS, DocumentFileError, build_document_ontology, chunk_paragraphs, document_fit,
    load_document_file,
)
from ontology_poc_generator.recognition import ModelCompletion

TEXT = '售后服务流程说明\n\n客户提交售后工单后，由售后工程师在两个工作日内联系客户。\n\n每张售后工单必须关联一张订单，订单记录了客户和产品。'


def docx(paragraphs):
    body = ''.join(f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paragraphs)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        z.writestr('word/document.xml', f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>')
    return buffer.getvalue()


class DocumentFileTests(unittest.TestCase):
    def test_markdown_text_and_word_are_read_as_paragraphs(self):
        md = load_document_file('流程.md', TEXT.encode('utf-8'))
        self.assertEqual(md['schema'], 'company_document_bundle.v1')
        self.assertEqual(md['file']['kind'], 'document')
        self.assertEqual(md['paragraphs'][0], '售后服务流程说明')
        self.assertEqual(len(md['paragraphs']), 3)
        self.assertEqual(load_document_file('流程.txt', TEXT.encode('gb18030'))['paragraphs'], md['paragraphs'])
        self.assertEqual(load_document_file('流程.docx', docx(['第一段', '第二段']))['paragraphs'], ['第一段', '第二段'])

    def test_pdf_needs_pdftotext_and_says_so(self):
        with patch('ontology_poc_generator.company_documents.shutil.which', return_value=None), \
                self.assertRaisesRegex(DocumentFileError, 'pdftotext'):
            load_document_file('a.pdf', b'%PDF-1.4')

    def test_refuses_other_and_empty_files(self):
        for name, data, message in (('a.exe', b'x', '不支持'), ('a.md', b'   \n', '没有文字'), ('a.docx', b'not zip', 'Word')):
            with self.subTest(name=name), self.assertRaisesRegex(DocumentFileError, message):
                load_document_file(name, data)

    def test_paragraphs_are_grouped_into_chunks_without_splitting_them(self):
        chunks = chunk_paragraphs(['甲' * 40, '乙' * 40, '丙' * 40], size=90)
        self.assertEqual(chunks, ['甲' * 40 + '\n' + '乙' * 40, '丙' * 40])


class Model:
    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def complete_json(self, *, system_prompt, user_prompt):
        self.prompts.append(json.loads(user_prompt))
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(self.replies.pop(0)))


REPLY = {'concepts': [
    {'key': 'ticket', 'label': '售后工单', 'definition': '客户提交的售后请求', 'evidence': '客户提交售后工单后'},
    {'key': 'engineer', 'label': '售后工程师', 'definition': '负责联系客户的人', 'evidence': '由售后工程师在两个工作日内联系客户'},
    {'key': 'order', 'label': '订单', 'definition': '记录客户和产品', 'evidence': '订单记录了客户和产品'},
    {'key': 'invoice', 'label': '发票', 'definition': '开给客户的票据', 'evidence': '每张发票都要盖章'},
], 'relations': [
    {'from': 'ticket', 'to': 'order', 'label': '关联', 'meaning': '每张工单关联一张订单', 'evidence': '每张售后工单必须关联一张订单'},
    {'from': 'engineer', 'to': 'ticket', 'label': '处理', 'meaning': '工程师处理工单', 'evidence': '工程师会关闭工单'},
    {'from': 'ticket', 'to': 'invoice', 'label': '开票', 'meaning': 'x', 'evidence': '客户提交售后工单后'},
]}


class DocumentOntologyTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load_document_file('流程.md', TEXT.encode('utf-8'))

    def test_only_items_whose_quote_is_in_the_text_are_kept(self):
        ontology = build_document_ontology(self.bundle, Model(REPLY))
        self.assertEqual(ontology['status'], 'auto_built_verified')
        self.assertEqual(ontology['prompt_version'], DOCUMENT_PROMPT_VERSION)
        self.assertEqual([t['label'] for t in ontology['object_types']], ['售后工单', '售后工程师', '订单'])
        self.assertEqual(ontology['object_types'][0]['evidence'], ['客户提交售后工单后'])
        self.assertEqual([(r['from'], r['to']) for r in ontology['relations']], [('ticket', 'order')])
        reasons = {r['item']: r['reason'] for r in ontology['rejected']}
        self.assertIn('原文里找不到', reasons['发票'])
        self.assertIn('原文里找不到', reasons['售后工程师 → 售后工单'])
        self.assertIn('发票', reasons['售后工单 → 发票'])

    def test_the_same_concept_from_two_chunks_is_merged(self):
        bundle = {**self.bundle, 'chunks': ['客户提交售后工单后', '每张售后工单必须关联一张订单']}
        first = {'concepts': [{'key': 'ticket', 'label': '售后工单', 'definition': 'a', 'evidence': '客户提交售后工单后'}], 'relations': []}
        second = {'concepts': [{'key': 'ticket', 'label': '售后工单', 'definition': 'b', 'evidence': '每张售后工单必须关联一张订单'}], 'relations': []}
        ontology = build_document_ontology(bundle, Model(first, second))
        self.assertEqual(len(ontology['object_types']), 1)
        self.assertEqual(ontology['object_types'][0]['evidence'], ['客户提交售后工单后', '每张售后工单必须关联一张订单'])

    def test_long_documents_are_cut_and_say_so(self):
        bundle = {**self.bundle, 'chunks': ['客户提交售后工单后'] * (MAX_CHUNKS + 2)}
        model = Model(*[{'concepts': [], 'relations': []}] * (MAX_CHUNKS + 2))
        ontology = build_document_ontology(bundle, model)
        self.assertEqual(len(model.prompts), MAX_CHUNKS)
        self.assertEqual((ontology['chunks_processed'], ontology['chunks_total']), (MAX_CHUNKS, MAX_CHUNKS + 2))
        self.assertEqual(ontology['status'], 'blocked')

    def test_document_checks(self):
        ontology = build_document_ontology(self.bundle, Model(REPLY))
        fit = document_fit(ontology)
        self.assertEqual((fit['proposed'], fit['kept'], fit['rejected']), (7, 4, 3))
        self.assertEqual(fit['isolated'], ['售后工程师'])
        self.assertEqual({c['key']: c['passed'] for c in fit['checks']}, {'quotes_verified': False, 'no_isolated_concepts': False})


if __name__ == '__main__':
    unittest.main()
