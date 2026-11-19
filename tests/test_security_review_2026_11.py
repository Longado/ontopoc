"""Findings of the 2026-11-18 security review (docs/SECURITY_REVIEW_2026-11-18.md): each test failed before its fix."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ontology_poc_generator import accounts
from tests.test_accounts import AccountTestCase
from tests.test_background_language import post
from tests.test_job_persistence import UPLOAD, serving
from tests.test_ontology_jobs import wait

PATH = '/srv/ontopoc/secret-data-dir/20261118T000000Z-abcdef12.json'


class DiskFails:
    model = 'disk'

    def complete_json(self, **kwargs):
        raise OSError(28, 'No space left on device', PATH)


class SecurityReviewTests(AccountTestCase):
    def test_a_name_nobody_has_is_not_kept_in_the_log_because_it_may_be_a_password_typed_in_the_wrong_box(self):
        typed = 'Hunter2Hunter2Hunter2'   # a person pastes their password into the name field
        with self.assertRaises(accounts.AccountError):
            self.sign_in(typed, 'some other text!')
        logged = ' '.join(f'{a} {b}' for a, b in self.conn.execute("SELECT who, after_json FROM log WHERE change = 'login_failed'"))
        self.assertNotIn(typed.casefold(), logged.casefold())
        with self.assertRaises(accounts.AccountError):   # a real account's name is still kept: that is what an admin looks for
            self.sign_in('root', 'wrong password!')
        self.assertIn('"root"', self.conn.execute("SELECT after_json FROM log WHERE change = 'login_failed' ORDER BY rowid DESC").fetchone()[0])


class ErrorTextTests(unittest.TestCase):
    def test_a_failed_job_does_not_tell_the_builder_where_on_the_server_the_disk_failed(self):
        with tempfile.TemporaryDirectory() as out:
            with serving(Path(out), DiskFails()) as base:
                _, started = post(base, '/api/ontology/jobs', UPLOAD)
                job = wait(base, started['job_id'])
        self.assertEqual(job['state'], 'failed')
        self.assertNotIn('/srv/', job['error'])
        self.assertNotIn('secret-data-dir', job['error'])
