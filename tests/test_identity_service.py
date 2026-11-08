from datetime import datetime, timedelta, timezone
import base64
import json
import unittest
from device_identity import DeviceIdentity
from identity_service import IdentityService
from pairing_service import AuthenticationRequired

class IdentityBootstrapTests(unittest.TestCase):
    def test_nonce_then_signed_proof(self):
        calls = []
        def transport(method, url, headers, body):
            calls.append((method,url,headers,json.loads(body)))
            if len(calls) == 1:
                return {'nonce': 'offline-server-challenge', 'epochTimeStamp': 100}
            return {'accessToken': 'offline-test-token', 'epochExpirationTime': 1900000000}
        now = datetime(2026,11,7,tzinfo=timezone.utc)
        identity = DeviceIdentity('test-device', now=now,
            certificate_validity=timedelta(days=365), clock_skew=timedelta(hours=12))
        result = IdentityService(lambda:'offline-msa', transport=transport).create_identity(identity,now=now)
        self.assertEqual(result['accessToken'],'offline-test-token')
        self.assertTrue(calls[0][1].endswith('/Auth/GenerateNonce?api-version=1.1.0'))
        self.assertEqual(calls[0][3], {'deviceId':'test-device'})
        self.assertEqual(calls[1][2]['UserIdentityToken'],'offline-msa')
        self.assertTrue(calls[1][1].endswith('/Auth/CreateIdentity?api-version=1.1.0'))
        jwt = calls[1][3]['certificateJWT']
        claims = json.loads(base64.urlsafe_b64decode(jwt.split('.')[1]+'=='))
        self.assertEqual(claims['Nonce'],'offline-server-challenge')
        self.assertEqual(claims['iss'],'test-device')

    def test_auth_missing_never_requests(self):
        def unexpected(*args):
            self.fail('No request should be made')
        with self.assertRaises(AuthenticationRequired):
            IdentityService(lambda:None,transport=unexpected).create_identity(None)

    def test_invalid_nonce_stops_bootstrap(self):
        calls=[]
        def transport(*args):
            calls.append(args)
            return {}
        class Identity:
            client_id='test-device'
        with self.assertRaises(ValueError):
            IdentityService(lambda:'offline-msa',transport=transport).create_identity(Identity())
        self.assertEqual(len(calls),1)

if __name__ == '__main__':
    unittest.main()
