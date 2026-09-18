"""A client sends a new version of the file (极客夜话 39: use change as a stress test). One row more is another file by
its hash, so a person says it is the next version; the confirmation, the fixed questions and the adopted rules carry
over, and the run says which objects came and went."""
import base64
import unittest

from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import OntologyServerTests

V1 = '订单号,客户编号,金额\nO1,C1,100\nO2,C2,50\n'.encode('utf-8')
V2 = '订单号,客户编号,金额\nO1,C1,100\nO3,C3,70\nO4,C1,20\n'.encode('utf-8')


def upload(data, **extra):
    return {'filename': 'orders.csv', 'content_base64': base64.b64encode(data).decode(), **extra}


class NewVersionTests(unittest.TestCase):
    def test_a_new_version_carries_the_judgements_over_and_says_what_changed(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, first = call(base, '/api/ontology/build', upload(V1))
            decisions = {'types': {t['key']: {'verdict': 'ok'} for t in first['ontology']['object_types']}, 'relations': {}, 'added': []}
            self.assertEqual(call(base, '/api/ontology/confirm', {'saved_as': first['saved_as'], 'decisions': decisions})[0], 200)
            rule = first['evaluation']['rules']['candidates'][0]['id']
            self.assertEqual(call(base, '/api/ontology/rules', {'saved_as': first['saved_as'], 'adopted': [rule]})[0], 200)

            status, second = call(base, '/api/ontology/build', upload(V2, previous=first['saved_as']))
            self.assertEqual(status, 200, second)
            self.assertEqual(second['lineage'], first['file']['sha256'])
            self.assertTrue(second['evaluation']['reference']['confirmed'])        # compared against the confirmation at once
            self.assertTrue(second['evaluation']['reference']['suggested'])        # and it is prefilled
            self.assertEqual([r['id'] for r in second['evaluation']['rules']['adopted']], [rule])
            changes = {c['type']: c for c in second['version']['objects']}
            self.assertEqual((changes['order']['before'], changes['order']['after'], changes['order']['added'], changes['order']['removed']), (2, 3, 2, 1))
            self.assertEqual(changes['order']['removed_examples'], ['O2'])
            self.assertEqual(second['version']['previous'], first['saved_as'])

            _, third = call(base, '/api/ontology/build', upload(V2.replace(b'O4,C1,20', b'O5,C2,5'), previous=second['saved_as']))
            self.assertEqual(third['lineage'], first['file']['sha256'])            # the line runs back to the first version

    def test_a_changed_file_that_is_not_called_a_new_version_starts_fresh(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, first = call(base, '/api/ontology/build', upload(V1))
            decisions = {'types': {t['key']: {'verdict': 'ok'} for t in first['ontology']['object_types']}, 'relations': {}, 'added': []}
            call(base, '/api/ontology/confirm', {'saved_as': first['saved_as'], 'decisions': decisions})
            _, other = call(base, '/api/ontology/build', upload(V2))
            self.assertNotIn('lineage', other)
            self.assertNotIn('version', other)
            self.assertIsNone(other['evaluation'].get('reference'))

    def test_previous_must_be_a_kept_run(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            status, body = call(base, '/api/ontology/build', upload(V2, previous='nope.json'))
            self.assertEqual(status, 400, body)


if __name__ == '__main__':
    unittest.main()
