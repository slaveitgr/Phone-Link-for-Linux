import unittest
from urllib.parse import quote_plus
from pairing_link import parse_pairing_link

class PairingLinkTests(unittest.TestCase):
    def test_observed_query_keys(self):
        parsed = parse_pairing_link('https://example.invalid/link?cpsi=session-123&r=eu&vm=1&ti=trace')
        self.assertEqual((parsed.session_id,parsed.region,parsed.visit_mode,parsed.trace_id),
                         ('session-123','eu','1','trace'))

    def test_full_url_decoding_precedes_query_parsing(self):
        parsed = parse_pairing_link(quote_plus('https://example.invalid/link?cpsi=session-123&r=eu'))
        self.assertEqual(parsed.session_id, 'session-123')
        self.assertEqual(parsed.region, 'eu')

    def test_missing_keys_and_first_duplicate_match_android(self):
        parsed = parse_pairing_link('https://example.invalid/?cpsi=first&cpsi=second')
        self.assertEqual(parsed.session_id, 'first')
        self.assertEqual(parsed.region, '')

    def test_invalid_escape_rejected(self):
        with self.assertRaises(ValueError):
            parse_pairing_link('https://example.invalid/?cpsi=%GG')

if __name__ == '__main__':
    unittest.main()
