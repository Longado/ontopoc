import threading
import unittest

from ontology_poc_generator import lang


class LangTest(unittest.TestCase):
    def tearDown(self):
        lang.use('zh')

    def test_header_picks_english_only_when_english_comes_first(self):
        self.assertEqual(lang.from_header('en-US,en;q=0.9'), 'en')
        self.assertEqual(lang.from_header('zh-CN,en;q=0.5'), 'zh')
        self.assertEqual(lang.from_header(None), 'zh')

    def test_default_is_chinese_and_tr_follows_the_request(self):
        self.assertEqual(lang.tr('好', 'ok'), '好')
        lang.use('en')
        self.assertEqual(lang.tr('好', 'ok'), 'ok')
        self.assertTrue(lang.english())

    def test_each_thread_starts_in_chinese(self):
        lang.use('en')
        seen = []
        t = threading.Thread(target=lambda: seen.append(lang.tr('好', 'ok')))
        t.start(); t.join()
        self.assertEqual(seen, ['好'])
