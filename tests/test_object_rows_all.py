import unittest

from ontology_poc_generator.object_rows import object_rows
from tests.test_object_rows import BUNDLE, ONTOLOGY


class AllRowsTests(unittest.TestCase):
    def test_a_download_can_ask_for_every_row_at_once(self):
        page = object_rows(ONTOLOGY, BUNDLE, 'customer', page=1, size=None)
        self.assertEqual((page['total'], len(page['rows']), page['size']), (3, 3, 3))


if __name__ == '__main__':
    unittest.main()
