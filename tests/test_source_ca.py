"""A source can carry its own CA certificate, for a company database whose certificate an internal CA signed: the connection then trusts that CA
(and only it) for this source, the host name is still checked, and the certificate text is never sent back or written to the log."""
import datetime
import ssl
import unittest
from unittest import mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from ontology_poc_generator import source_connect
from tests.test_sources import SourceCase


def ca_pem(name='Internal CA') -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def common_names(context: ssl.SSLContext) -> list[str]:
    return [dict(part[0] for part in c['subject'])['commonName'] for c in context.get_ca_certs()]


class ContextTests(unittest.TestCase):
    def test_the_sources_own_ca_is_the_one_trusted_and_the_name_is_still_checked(self):
        context = source_connect._tls_context(ca_pem('Internal CA'))
        self.assertEqual(common_names(context), ['Internal CA'])
        self.assertEqual((context.verify_mode, context.check_hostname), (ssl.CERT_REQUIRED, True))

    def test_both_drivers_are_given_the_context_with_the_ca(self):
        pem, made = ca_pem('Pinned'), []
        driver = mock.Mock(connect=lambda **kw: made.append(kw) or mock.Mock(statements=[], cursor=mock.Mock()))
        with mock.patch.object(source_connect, '_driver', return_value=driver), mock.patch.object(source_connect, '_dial', return_value=object()), \
                mock.patch.object(source_connect.Postgres, '__init__', return_value=None), mock.patch.object(source_connect.Postgres, '_query'), \
                mock.patch.object(source_connect.Postgres, '_within'), mock.patch.object(source_connect.MySql, '__init__', return_value=None), \
                mock.patch.object(source_connect.MySql, '_query', create=True), mock.patch.object(source_connect.MySql, '_within', create=True):
            for opener in (source_connect.Postgres.open, source_connect.MySql.open):
                try:
                    opener('db.internal', '10.0.0.5', 5432, 'd', 'u', 'p', 'required', ca_pem=pem)
                except Exception:
                    pass   # what happens after the driver is called is not this test's
        self.assertEqual([common_names(made[0]['ssl_context']), common_names(made[1]['ssl'])], [['Pinned'], ['Pinned']])

    def test_a_text_that_is_not_a_certificate_is_refused_in_words(self):
        for bad in ('hello', '-----BEGIN CERTIFICATE-----\nnot base64\n-----END CERTIFICATE-----', 'x' * 70000):
            with self.subTest(bad=bad[:20]), self.assertRaises(source_connect.SourceError):
                source_connect.check_ca(bad)
        source_connect.check_ca(ca_pem())


class SourceCaApiTests(SourceCase):
    FIELDS = {'kind': 'postgresql', 'host': 'db.example.com', 'database': 'd', 'username': 'u', 'password': 'p'}

    def test_an_admin_saves_a_ca_that_is_used_to_connect_shown_only_as_set_and_cleared_with_an_empty_text(self):
        pem = ca_pem('Corp Root')
        with self.service() as (base_url, out):
            admin = self.team(base_url)['admin']
            status, body = self.ask(admin, 'post', '/api/workspace/sources', {**self.FIELDS, 'name': 'bad', 'ca_pem': 'nope'})
            self.assertEqual(status, 400)
            self.assertIn('证书', body['error'])
            status, body = self.ask(admin, 'post', '/api/workspace/sources', {**self.FIELDS, 'name': 'plain', 'tls': 'none', 'ca_pem': pem})
            self.assertEqual(status, 400)   # a CA with no encryption would check nothing
            status, body = self.ask(admin, 'post', '/api/workspace/sources', {**self.FIELDS, 'name': 'corp', 'ca_pem': pem})
            self.assertEqual((status, body['custom_ca']), (200, True), body)
            self.ask(admin, 'post', '/api/workspace/sources/test', {'name': 'corp'})
            self.assertEqual(self.ca_seen, pem)
            listed = {s['name']: s for s in self.ask(admin, 'get', '/api/workspace/sources')[1]['sources']}
            self.assertTrue(listed['corp']['custom_ca'])
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/sources/update', {'name': 'corp', 'ca_pem': ''})[0], 200)
            self.assertFalse({s['name']: s for s in self.ask(admin, 'get', '/api/workspace/sources')[1]['sources']}['corp']['custom_ca'])
            self.ask(admin, 'post', '/api/workspace/sources/test', {'name': 'corp'})
            self.assertIsNone(self.ca_seen)
            self.assertFalse(any('BEGIN CERTIFICATE' in said for said in self.said))   # never sent back
            log = (out / 'workspace.sqlite').read_bytes()
            self.assertNotIn(b'"ca_pem"', log)


if __name__ == '__main__':
    unittest.main()
