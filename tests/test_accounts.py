"""Accounts: passwords, sign-in limits, sessions, API tokens and the safeguards on roles. Counts and times are set by hand."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest import mock

from ontology_poc_generator import accounts
from ontology_poc_generator.accounts import AccountError, LoginLimiter
from ontology_poc_generator.workspace_store import open_workspace

GOOD = 'correct horse battery'
T0 = datetime(2026, 11, 14, 9, 0, 0, tzinfo=timezone.utc)


class Clock:
    """The limiter's clock, moved by hand."""
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class AccountTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(accounts, 'SCRYPT_N', 2 ** 10)   # cheap hashes: the cost is stored with each hash, so this only speeds the tests up
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = open_workspace(':memory:')
        self.addCleanup(self.conn.close)
        self.limiter = LoginLimiter(Clock())
        self.admin = accounts.create_user(self.conn, 'root', '管理员', 'admin', GOOD, 'host', must_change=False)

    def make(self, username, role='builder', password=GOOD, **more):
        return accounts.create_user(self.conn, username, username, role, password, 'root', **more)

    def sign_in(self, username, password=GOOD, client='10.0.0.1'):
        return accounts.authenticate(self.conn, self.limiter, username, password, client)


class PasswordTests(AccountTestCase):
    def test_a_hash_names_its_cost_and_checks_in_both_directions(self):
        stored = accounts.hash_password(GOOD)
        self.assertRegex(stored, r'^scrypt\$1024\$8\$1\$[0-9a-f]{32}\$[0-9a-f]{64}$')
        self.assertTrue(accounts.verify_password(GOOD, stored))
        self.assertFalse(accounts.verify_password(GOOD + 'x', stored))
        self.assertNotEqual(stored, accounts.hash_password(GOOD))   # a fresh salt each time
        for broken in ('', 'scrypt$x', 'bcrypt$1$1$1$00$00', 'scrypt$1024$8$1$zz$00'):
            self.assertFalse(accounts.verify_password(GOOD, broken), broken)

    def test_a_hash_made_with_other_cost_still_checks(self):
        with mock.patch.object(accounts, 'SCRYPT_N', 2 ** 11):
            stored = accounts.hash_password(GOOD)
        self.assertTrue(accounts.verify_password(GOOD, stored))

    def test_what_a_password_must_be(self):
        self.assertIsNone(accounts.password_problem(GOOD, 'x'))
        self.assertIn('至少 12', accounts.password_problem('short', 'x'))
        self.assertIn('最多 1024', accounts.password_problem('a' * 1025, 'x'))
        self.assertIn('和账号一样', accounts.password_problem('Longname12345', 'longname12345'))
        self.assertIsNotNone(accounts.password_problem(None, 'x'))
        self.assertIsNone(accounts.password_problem('密码密码密码密码密码密码', 'x'))   # characters, not bytes

    def test_a_composed_and_a_decomposed_accent_are_the_same_password(self):
        stored = accounts.hash_password('café-café-café')
        self.assertTrue(accounts.verify_password('café-café-café', stored))


class CreateTests(AccountTestCase):
    def test_a_user_is_made_with_a_hash_and_must_change_it_by_default(self):
        made = self.make('xiaowang')
        self.assertEqual((made['role'], made['must_change'], made['disabled'], made['provider']), ('builder', True, False, 'local'))
        stored = self.conn.execute("SELECT password_hash FROM user WHERE username = 'xiaowang'").fetchone()[0]
        self.assertNotIn(GOOD, stored)

    def test_what_cannot_be_made(self):
        for args, text in ((('Root', 'x', 'viewer', GOOD), '已经有叫“Root”的账号'), (('a\nb', 'x', 'viewer', GOOD), '换行'),
                           (('', 'x', 'viewer', GOOD), '要写账号'), (('ok', 'x', 'owner', GOOD), '角色'), (('ok', 'x', 'viewer', 'short'), '至少 12'),
                           (('ok', 'a\nb', 'viewer', GOOD), '显示名')):
            with self.assertRaises(AccountError) as caught:
                accounts.create_user(self.conn, *args, 'root')
            self.assertIn(text, str(caught.exception), args)
        self.assertEqual(len(accounts.list_users(self.conn)), 1)

    def test_a_company_sign_on_user_has_no_password_and_cannot_sign_in_with_one(self):
        accounts.create_user(self.conn, 'sso-user', 'x', 'viewer', None, 'root', provider='oidc')
        self.assertEqual(self.conn.execute("SELECT password_hash, provider FROM user WHERE username = 'sso-user'").fetchone(), (None, 'oidc'))
        with self.assertRaises(AccountError) as caught:
            self.sign_in('sso-user', '')
        self.assertEqual(caught.exception.status, 401)


class SignInTests(AccountTestCase):
    def test_a_right_name_and_password_signs_in_whatever_the_case_of_the_name(self):
        self.assertEqual(self.sign_in('ROOT')['username'], 'root')
        self.assertIsNotNone(accounts.get_user(self.conn, self.admin['id'])['last_login_at'])

    def test_every_kind_of_wrong_answer_says_the_same_words_after_the_same_work(self):
        self.make('off', password=GOOD)
        accounts.set_disabled(self.conn, self.admin, accounts.list_users(self.conn)[1]['id'], True)
        calls = []
        real = accounts._scrypt
        with mock.patch.object(accounts, '_scrypt', side_effect=lambda *a: calls.append(1) or real(*a)):
            messages = []
            for name, password in (('nobody', GOOD), ('root', 'wrong password!'), ('off', GOOD), ('', GOOD)):
                before = len(calls)
                with self.assertRaises(AccountError) as caught:
                    self.sign_in(name, password, client=name or 'blank')
                messages.append((caught.exception.status, str(caught.exception), len(calls) - before))
        self.assertEqual(set(messages), {(401, accounts.GENERIC, 1)})   # one hash computed each, even for a name that does not exist

    def test_the_sixth_wrong_password_waits_and_a_right_one_does_not_get_past_the_wait(self):
        for _ in range(5):
            with self.assertRaises(AccountError) as caught:
                self.sign_in('root', 'wrong password!')
            self.assertEqual(caught.exception.status, 401)
        with self.assertRaises(AccountError) as caught:
            self.sign_in('root', GOOD)
        self.assertEqual((caught.exception.status, str(caught.exception)), (429, '试得太多了，请 60 秒后再试'))
        self.limiter._clock.now += 61
        self.assertEqual(self.sign_in('root')['username'], 'root')   # the wait is over and a good password clears the count

    def test_the_wait_doubles_up_to_fifteen_minutes(self):
        waits = []
        for _ in range(9):
            with self.assertRaises(AccountError):
                self.sign_in('root', 'wrong password!', client=f'c{len(waits)}')
            waits.append(self.limiter.wait('root', 'x'))
            self.limiter._clock.now += waits[-1]
        self.assertEqual(waits, [0, 0, 0, 0, 60, 120, 240, 480, 900])

    def test_an_unknown_name_is_limited_like_a_known_one(self):
        for _ in range(5):
            with self.assertRaises(AccountError):
                self.sign_in('ghost', 'wrong password!')
        with self.assertRaises(AccountError) as caught:
            self.sign_in('ghost', 'wrong password!')
        self.assertEqual(caught.exception.status, 429)

    def test_one_client_gets_twenty_wrong_passwords_in_ten_minutes_whatever_names_it_tries(self):
        for i in range(20):
            with self.assertRaises(AccountError) as caught:
                self.sign_in(f'name{i}', 'wrong password!', client='6.6.6.6')
            self.assertEqual(caught.exception.status, 401)
        with self.assertRaises(AccountError) as caught:
            self.sign_in('root', GOOD, client='6.6.6.6')
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(self.sign_in('root', GOOD, client='7.7.7.7')['username'], 'root')   # someone else is not held up
        self.limiter._clock.now += 601
        self.assertEqual(self.sign_in('root', GOOD, client='6.6.6.6')['username'], 'root')

    def test_failures_and_sign_ins_are_logged_with_the_name_kept_as_text(self):
        with self.assertRaises(AccountError):
            self.sign_in('x\nINJECT', 'wrong password!')
        self.sign_in('root')
        rows = self.conn.execute("SELECT who, change FROM log WHERE change IN ('login', 'login_failed') ORDER BY rowid").fetchall()
        self.assertEqual(rows, [('x\ninject', 'login_failed'), ('root', 'login')])

    def test_a_huge_password_is_refused_before_it_is_hashed(self):
        with mock.patch.object(accounts, '_scrypt') as work, self.assertRaises(AccountError):
            self.sign_in('root', 'a' * 5000)
        work.assert_not_called()


class SessionTests(AccountTestCase):
    def test_only_the_hash_of_a_token_is_stored(self):
        token = accounts.start_session(self.conn, self.admin['id'], T0)
        self.assertGreaterEqual(len(token), 43)   # 256 bits
        stored = self.conn.execute('SELECT token_hash FROM session').fetchone()[0]
        self.assertNotIn(token, stored)
        self.assertEqual(accounts.session_user(self.conn, token, T0)['username'], 'root')
        self.assertNotEqual(token, accounts.start_session(self.conn, self.admin['id'], T0))

    def test_idle_for_eight_hours_ends_it_and_use_keeps_it_going(self):
        token = accounts.start_session(self.conn, self.admin['id'], T0)
        for hours in (7, 14, 21):   # each visit is within 8 hours of the last
            self.assertIsNotNone(accounts.session_user(self.conn, token, T0 + timedelta(hours=hours)))
        self.assertIsNone(accounts.session_user(self.conn, token, T0 + timedelta(hours=30)))
        self.assertIsNone(accounts.session_user(self.conn, token, T0 + timedelta(hours=30)))   # and it is gone, not just late

    def test_fourteen_days_ends_it_however_busy(self):
        token = accounts.start_session(self.conn, self.admin['id'], T0)
        for visit in range(1, 56):   # every 6 hours for 13 days and 18 hours
            self.assertIsNotNone(accounts.session_user(self.conn, token, T0 + timedelta(hours=6 * visit)), visit)
        self.assertIsNone(accounts.session_user(self.conn, token, T0 + timedelta(days=14, minutes=1)))   # busy until a minute ago, and still over

    def test_disabling_a_person_ends_their_sessions_and_tokens_at_once(self):
        other = self.make('xiaoli')
        session = accounts.start_session(self.conn, other['id'], T0)
        _, token = accounts.create_token(self.conn, other, 'script', T0)
        accounts.set_disabled(self.conn, self.admin, other['id'], True)
        self.assertIsNone(accounts.session_user(self.conn, session, T0))
        self.assertIsNone(accounts.token_user(self.conn, token, T0))
        accounts.set_disabled(self.conn, self.admin, other['id'], False)
        self.assertIsNone(accounts.token_user(self.conn, token, T0))   # a revoked token stays revoked
        self.assertIsNone(accounts.session_user(self.conn, session, T0))

    def test_a_password_change_signs_the_other_sessions_out_but_not_this_one(self):
        mine, other = (accounts.start_session(self.conn, self.admin['id'], T0) for _ in range(2))
        accounts.change_password(self.conn, self.admin, GOOD, 'another long password', keep_token=mine)
        self.assertIsNotNone(accounts.session_user(self.conn, mine, T0))
        self.assertIsNone(accounts.session_user(self.conn, other, T0))
        self.assertEqual(self.sign_in('root', 'another long password')['username'], 'root')

    def test_a_wrong_current_password_changes_nothing(self):
        with self.assertRaises(AccountError) as caught:
            accounts.change_password(self.conn, self.admin, 'not it at all!', 'another long password')
        self.assertEqual(caught.exception.status, 403)
        with self.assertRaises(AccountError):
            accounts.change_password(self.conn, self.admin, GOOD, 'short')
        self.assertEqual(self.sign_in('root')['username'], 'root')

    def test_an_admin_reset_signs_the_person_out_and_asks_for_a_new_password(self):
        other = self.make('xiaoli', must_change=False)
        session = accounts.start_session(self.conn, other['id'], T0)
        reset = accounts.reset_password(self.conn, 'root', other['id'], 'a temporary password')
        self.assertTrue(reset['must_change'])
        self.assertIsNone(accounts.session_user(self.conn, session, T0))
        self.assertEqual(self.sign_in('xiaoli', 'a temporary password')['username'], 'xiaoli')
        with self.assertRaises(AccountError):
            self.sign_in('xiaoli', GOOD)


class TokenTests(AccountTestCase):
    def test_a_token_is_shown_once_and_has_its_owners_role_as_it_is_now(self):
        other = self.make('xiaoli')
        record, token = accounts.create_token(self.conn, other, '脚本', T0)
        self.assertTrue(token.startswith('otp_'))
        self.assertNotIn(token, str(self.conn.execute('SELECT * FROM api_token').fetchall()))
        self.assertEqual(accounts.token_user(self.conn, token, T0)['role'], 'builder')
        accounts.set_role(self.conn, self.admin, other['id'], 'viewer')
        self.assertEqual(accounts.token_user(self.conn, token, T0)['role'], 'viewer')   # never more than its owner
        self.assertEqual([(t['label'], t['revoked']) for t in accounts.list_tokens(self.conn, other['id'])], [('脚本', False)])
        accounts.revoke_token(self.conn, other, record['id'])
        self.assertIsNone(accounts.token_user(self.conn, token, T0))

    def test_a_token_is_not_a_session_and_a_session_is_not_a_token(self):
        session = accounts.start_session(self.conn, self.admin['id'], T0)
        _, token = accounts.create_token(self.conn, self.admin, 'x', T0)
        self.assertIsNone(accounts.token_user(self.conn, session, T0))
        self.assertIsNone(accounts.session_user(self.conn, token, T0))
        self.assertIsNone(accounts.token_user(self.conn, 'otp_' + 'x' * 43, T0))

    def test_nobody_revokes_someone_elses_token(self):
        other = self.make('xiaoli')
        record, _ = accounts.create_token(self.conn, other, 'x', T0)
        with self.assertRaises(AccountError):
            accounts.revoke_token(self.conn, self.admin, record['id'])


class RoleSafeguardTests(AccountTestCase):
    def test_nobody_changes_their_own_role_or_disables_themselves(self):
        for call in (lambda: accounts.set_role(self.conn, self.admin, self.admin['id'], 'viewer'), lambda: accounts.set_disabled(self.conn, self.admin, self.admin['id'], True)):
            with self.assertRaises(AccountError):
                call()
        self.assertEqual(accounts.get_user(self.conn, self.admin['id'])['role'], 'admin')

    def test_the_last_active_admin_stays(self):
        stranger = {'id': 999, 'username': 'x'}   # whoever acts, the one enabled admin cannot be removed
        for call in (lambda: accounts.set_role(self.conn, stranger, self.admin['id'], 'builder'), lambda: accounts.set_disabled(self.conn, stranger, self.admin['id'], True)):
            with self.assertRaises(AccountError) as caught:
                call()
            self.assertIn('至少要留一位', str(caught.exception))
        second = self.make('second', 'admin')
        self.assertEqual(accounts.set_role(self.conn, self.admin, second['id'], 'builder')['role'], 'builder')   # fine while another admin stays

    def test_a_bad_id_or_role_is_refused_in_words(self):
        for bad in (None, 'x', 99, True, [1]):
            with self.assertRaises(AccountError):
                accounts.set_role(self.conn, self.admin, bad, 'viewer')
        other = self.make('xiaoli')
        for bad in ('owner', None, 5):
            with self.assertRaises(AccountError):
                accounts.set_role(self.conn, self.admin, other['id'], bad)
        with self.assertRaises(AccountError):
            accounts.set_disabled(self.conn, self.admin, other['id'], 'yes')

    def test_each_change_is_logged_by_whom(self):
        other = self.make('xiaoli')
        accounts.set_role(self.conn, self.admin, other['id'], 'viewer')
        accounts.set_disabled(self.conn, self.admin, other['id'], True)
        self.assertEqual(self.conn.execute("SELECT who, change FROM log WHERE element_id = ? ORDER BY rowid", (f'user:{other["id"]}',)).fetchall(),
                         [('root', 'user_created'), ('root', 'role_changed'), ('root', 'user_disabled')])


class HostToolTests(unittest.TestCase):
    """create-admin and reset-password, the only way the first account comes to exist."""

    def run_tool(self, folder, *argv, passwords=(GOOD, GOOD)):
        with mock.patch.object(accounts, 'SCRYPT_N', 2 ** 10), mock.patch('getpass.getpass', side_effect=list(passwords)):
            return accounts.main([*argv, '--data-dir', folder])

    def test_the_first_admin_is_made_on_the_host_with_a_typed_password_and_can_sign_in(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self.run_tool(folder, 'create-admin', 'alice'), 0)
            conn = open_workspace(f'{folder}/workspace.sqlite')
            [alice] = accounts.list_users(conn)
            self.assertEqual((alice['username'], alice['role'], alice['must_change']), ('alice', 'admin', False))
            with mock.patch.object(accounts, 'SCRYPT_N', 2 ** 10):
                self.assertEqual(accounts.authenticate(conn, LoginLimiter(), 'alice', GOOD, 'host')['id'], alice['id'])
            token = accounts.start_session(conn, alice['id'])
            self.assertEqual(self.run_tool(folder, 'reset-password', 'alice', passwords=('a brand new password', 'a brand new password')), 0)
            self.assertIsNone(accounts.session_user(conn, token))   # a reset signs everyone out
            self.assertEqual(self.run_tool(folder, 'reset-password', 'nobody'), 1)
            self.assertEqual(self.run_tool(folder, 'create-admin', 'alice'), 1)   # taken
            conn.close()


if __name__ == '__main__':
    unittest.main()
