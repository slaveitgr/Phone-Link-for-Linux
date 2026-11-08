import base64
from datetime import datetime, timedelta, timezone
import json
import unittest
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from device_identity import DeviceIdentity

def decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))

class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 7, tzinfo=timezone.utc)
        self.identity = DeviceIdentity('test-client-id', now=self.now,
            certificate_validity=timedelta(days=1), clock_skew=timedelta(minutes=1))

    def test_observed_certificate_algorithm_and_extensions(self):
        cert = self.identity.certificate
        self.assertEqual(cert.public_key().curve.name, 'secp384r1')
        self.assertEqual(cert.signature_hash_algorithm.name, 'sha384')
        self.assertFalse(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        self.assertTrue(cert.extensions.get_extension_for_class(x509.KeyUsage).value.digital_signature)
        cert.public_key().verify(cert.signature, cert.tbs_certificate_bytes, ec.ECDSA(hashes.SHA384()))

    def test_nonce_claim_and_signature_verify_with_embedded_certificate(self):
        token = self.identity.sign_server_nonce('offline-test-nonce', now=self.now,
            jwt_validity=timedelta(minutes=5), clock_skew=timedelta(minutes=1))
        header, claims, signature = token.split('.')
        self.assertEqual(json.loads(decode(header))['alg'], 'ES384')
        payload = json.loads(decode(claims))
        self.assertEqual(payload['Nonce'], 'offline-test-nonce')
        self.assertEqual(payload['iss'], 'test-client-id')
        cert = x509.load_der_x509_certificate(base64.b64decode(payload['Certificate']))
        raw = decode(signature)
        self.assertEqual(len(raw), 96)
        der = encode_dss_signature(int.from_bytes(raw[:48], 'big'), int.from_bytes(raw[48:], 'big'))
        cert.public_key().verify(der, (header+'.'+claims).encode(), ec.ECDSA(hashes.SHA384()))
        with self.assertRaises(InvalidSignature):
            cert.public_key().verify(der, (header+'.'+claims+'x').encode(), ec.ECDSA(hashes.SHA384()))

    def test_nonce_and_timezone_required(self):
        with self.assertRaises(ValueError):
            self.identity.sign_server_nonce('', now=self.now,
                jwt_validity=timedelta(minutes=5), clock_skew=timedelta(0))

if __name__ == '__main__':
    unittest.main()
