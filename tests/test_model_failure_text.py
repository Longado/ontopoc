import unittest

from ontology_poc_generator.recognition import model_failure_text


class ModelFailureTextTests(unittest.TestCase):
    def test_an_empty_account_is_not_something_to_retry_later(self):
        text = model_failure_text('model request failed: HTTP Error 402: Payment Required')
        self.assertTrue(text.startswith('模型请求失败'))   # callers tell a model outage from a bad reply by this
        self.assertIn('余额', text)
        self.assertNotIn('稍后重试', text)

    def test_anything_else_is_still_worth_trying_again(self):
        text = model_failure_text('model request failed: <urlopen error timed out>')
        self.assertIn('稍后重试', text)
        self.assertIn('timed out', text)


if __name__ == '__main__':
    unittest.main()
