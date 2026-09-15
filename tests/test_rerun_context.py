import unittest

from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_compare_server import UPLOAD
from tests.test_ontology_server import OntologyServerTests


class RerunContextTests(unittest.TestCase):
    def test_the_compared_run_says_what_it_was_built_for_and_how_big_it_was(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, first = call(base, '/api/ontology/build', {**UPLOAD, 'purpose': '哪些客户下单最多？'})
            _, second = call(base, '/api/ontology/build', {**UPLOAD, 'purpose': '订单金额怎么分布？'})
        previous = second['previous']
        self.assertEqual(previous['purpose'], '哪些客户下单最多？')
        self.assertEqual(previous['counts'], {'types': len(first['ontology']['object_types']), 'relations': len(first['ontology']['relations'])})


if __name__ == '__main__':
    unittest.main()
