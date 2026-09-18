import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from ontology_poc_generator import ontology_server


def health(base):
    with urlopen(base + '/api/ontology/health', timeout=10) as response:
        return json.load(response)


class StaleServiceTests(unittest.TestCase):
    def test_the_service_says_when_the_code_on_disk_changed_after_it_started(self):
        with tempfile.TemporaryDirectory() as code, tempfile.TemporaryDirectory() as out:
            code_dir = Path(code)
            shutil.copy(Path(ontology_server.__file__), code_dir / 'ontology_server.py')
            server = ontology_server.make_server(port=0, gateway=None, output_dir=Path(out), code_dir=code_dir)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                first = health(base)
                self.assertFalse(first['stale'])
                self.assertEqual(first['running'], first['on_disk'])
                (code_dir / 'ontology_server.py').write_text('# changed after start\n', encoding='utf-8')
                second = health(base)
                self.assertTrue(second['stale'])
                self.assertEqual(second['running'], first['running'])   # what it runs has not changed; the disk has
                self.assertNotEqual(second['on_disk'], first['on_disk'])
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
