import json
import unittest
from pairing_service import PairingService, AuthenticationRequired

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        def transport(*args):
            self.requests.append(args)
            return {'pairingSessionId': 'test-session'}
        self.client = PairingService(lambda: 'test-token', '3.0.0', transport=transport)

    def test_observed_routes_and_methods(self):
        self.client.create_session({'flow': 'test-fixture-only'})
        self.client.get_session('test-session')
        self.client.refresh_challenge_pin('test-session')
        self.client.complete_session('test-session')
        self.assertEqual([r[0] for r in self.requests], ['POST','GET','POST','POST'])
        paths = [r[1].split('.com')[1] for r in self.requests]
        self.assertEqual(paths, [
            '/DevicePairingProxy/PairingSessions?Api-Version=3.0.0',
            '/DevicePairingProxy/PairingSessions/test-session?Api-Version=3.0.0',
            '/DevicePairingProxy/PairingSessions/test-session/RefreshChallengePIN?Api-Version=3.0.0',
            '/DevicePairingProxy/PairingSessions/test-session/Complete?Api-Version=3.0.0'])
        self.assertEqual(json.loads(self.requests[0][3]), {'flow':'test-fixture-only'})

    def test_missing_auth_prevents_request(self):
        self.client.authorization_provider = lambda: None
        with self.assertRaises(AuthenticationRequired):
            self.client.get_session('test-session')
        self.assertEqual(self.requests, [])

    def test_path_injection_rejected_before_auth(self):
        with self.assertRaises(ValueError):
            self.client.get_session('../other')
        self.assertEqual(self.requests, [])

    def test_untrusted_origin_rejected(self):
        for origin in ['http://dcg.microsoft.com','https://example.com','https://dcg.microsoft.com@evil.invalid']:
            with self.assertRaises(ValueError):
                PairingService(lambda: 'test-token', '3.0.0', base_url=origin)

if __name__ == '__main__':
    unittest.main()
