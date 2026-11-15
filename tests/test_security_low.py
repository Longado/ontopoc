"""The low findings of the pre-pilot security review: a source's host carries no port (the port has its own field, so 169.254.169.254:80 is not a
host name to look up later), and a body that is not JSON gets a 400 in words, not a dropped connection."""
import http.client
import unittest
from urllib.parse import urlsplit

from ontology_poc_generator.workspace_sources import _connection_fields
from tests.test_access import Client, GateTestCase


class HostFieldTests(unittest.TestCase):
    def test_a_host_with_a_port_is_refused_and_an_ipv6_address_is_not(self):
        for host in ('db.example.com:3306', '169.254.169.254:80', 'localhost:5432'):
            with self.subTest(host=host):
                with self.assertRaises(ValueError) as raised:
                    _connection_fields({'host': host, 'port': 3306, 'database': 'd', 'username': 'u'}, 'mysql')
                self.assertIn('端口', str(raised.exception))
        for host in ('::1', '[::1]', 'db.example.com', '10.0.0.5'):
            with self.subTest(host=host):
                self.assertEqual(_connection_fields({'host': host, 'port': 3306, 'database': 'd', 'username': 'u'}, 'mysql')['port'], 3306)


class MalformedBodyTests(GateTestCase):
    def test_a_body_that_is_not_json_or_a_length_that_is_not_a_number_is_answered_400_in_words(self):
        with self.service() as (base, _):
            admin = Client(base)
            admin.login('root')
            parts = urlsplit(base)
            for body, length in ((b'{not json', None), (b'\xff\xfe', None), (b'{}', 'abc')):
                with self.subTest(body=body, length=length):
                    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=10)
                    headers = {'Content-Type': 'application/json', 'Cookie': f'{admin.cookie_name}={admin.cookie}', 'Origin': base}
                    if length:
                        conn.putrequest('POST', '/api/workspace/ask')
                        for k, v in {**headers, 'Content-Length': length}.items():
                            conn.putheader(k, v)
                        conn.endheaders(body)
                    else:
                        conn.request('POST', '/api/workspace/ask', body=body, headers=headers)
                    reply = conn.getresponse()
                    text = reply.read().decode('utf-8', 'replace')
                    self.assertEqual(reply.status, 400, text)
                    self.assertIn('JSON', text)
                    conn.close()


if __name__ == '__main__':
    unittest.main()
