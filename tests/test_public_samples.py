import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublicSamplesTests(unittest.TestCase):
    def test_the_page_offers_the_same_sample_files_the_repo_keeps(self):
        for name in ('demo_company.xlsx', 'after_sales_process.md', 'demo_reference_ontology.json'):
            with self.subTest(name=name):
                digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
                self.assertEqual(digest(ROOT / 'landing-page/public/samples' / name), digest(ROOT / 'examples/company' / name))


if __name__ == '__main__':
    unittest.main()
