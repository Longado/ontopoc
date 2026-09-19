"""The service can be pointed at another data directory, so a trial run (a demo, a screenshot script) never writes
into the runs a person keeps. Without the option it keeps using the repository's output/ontology-runs."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ontology_poc_generator import ontology_server


def started_with(argv):
    fake = mock.MagicMock(server_port=0)
    with mock.patch.object(ontology_server, 'make_server', return_value=fake) as made, mock.patch.object(ontology_server, 'gateway_from_env', return_value=None):
        ontology_server.main(argv)
    return made.call_args


class DataDirTests(unittest.TestCase):
    def test_a_trial_can_keep_its_runs_elsewhere(self):
        with tempfile.TemporaryDirectory() as d:
            call = started_with(['--port', '0', '--data-dir', d])
        self.assertEqual(call.kwargs['output_dir'], Path(d))

    def test_by_default_runs_stay_where_they_always were(self):
        self.assertEqual(started_with([]).kwargs['output_dir'], ontology_server.ROOT / 'output/ontology-runs')


if __name__ == '__main__':
    unittest.main()
