"""Linux replacement for observed Phone Link certificate/signing primitives.

P-384, SHA-384, non-CA/digital-signature certificate extensions and the exact
Nonce/Certificate claims were observed in the shipped CIL. Service acceptance
is not established by these local cryptographic tests. No keys are persisted.
"""
import base64
from datetime import timedelta
import json
import re
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.x509.oid import NameOID

def base64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=')

class DeviceIdentity:
    @classmethod
    def from_pem(cls, client_id, key_pem, certificate_pem):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', client_id):
            raise ValueError('Invalid stored device identity')
        key = serialization.load_pem_private_key(key_pem.encode(), password=None)
        cert = x509.load_pem_x509_certificate(certificate_pem.encode())
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP384R1):
            raise ValueError('Stored key must use P-384')
        if key.public_key().public_numbers() != cert.public_key().public_numbers():
            raise ValueError('Stored certificate and key do not match')
        names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if len(names) != 1 or names[0].value != client_id:
            raise ValueError('Stored certificate identity does not match')
        result = cls.__new__(cls)
        result.client_id, result._key, result.certificate = client_id, key, cert
        return result

    def __init__(self, client_id, *, now, certificate_validity, clock_skew):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', client_id):
            raise ValueError('A valid client identity is required')
        if now.tzinfo is None or certificate_validity <= timedelta(0) or clock_skew < timedelta(0):
            raise ValueError('Explicit timezone-aware validity parameters required')
        self.client_id = client_id
        self._key = ec.generate_private_key(ec.SECP384R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, client_id)])
        self.certificate = (
            x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(self._key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - clock_skew).not_valid_after(now + certificate_validity)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False, key_agreement=False,
                key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=False)
            .sign(self._key, hashes.SHA384()))

    def sign_server_nonce(self, nonce, *, now, jwt_validity, clock_skew):
        if not isinstance(nonce, str) or not nonce:
            raise ValueError('The actual server nonce is required')
        if now.tzinfo is None or jwt_validity <= timedelta(0) or clock_skew < timedelta(0):
            raise ValueError('Explicit timezone-aware JWT validity parameters required')
        claims = {
            'iss': self.client_id,
            'nbf': int((now-clock_skew).timestamp()),
            'exp': int((now+jwt_validity).timestamp()),
            'iat': int(now.timestamp()),
            'Nonce': nonce,
            'Certificate': base64.b64encode(
                self.certificate.public_bytes(serialization.Encoding.DER)).decode('ascii'),
        }
        header = {'alg': 'ES384', 'typ': 'JWT'}
        parts = [base64url(json.dumps(value, separators=(',', ':')).encode('utf-8'))
                 for value in (header, claims)]
        signing_input = b'.'.join(parts)
        der = self._key.sign(signing_input, ec.ECDSA(hashes.SHA384()))
        r, s = decode_dss_signature(der)
        signature = r.to_bytes(48, 'big') + s.to_bytes(48, 'big')
        return (signing_input + b'.' + base64url(signature)).decode('ascii')

    def sign_scoped_data(self, data, *, source_id, scope, now):
        """Observed CryptoManager ConvertToClaims: Data, SourceId, Scope."""
        if now.tzinfo is None or not scope or not source_id:
            raise ValueError('Explicit time, source and scope required')
        claims = {'iss':self.client_id, 'iat':int(now.timestamp()),
            'nbf':int((now-timedelta(hours=12)).timestamp()),
            'exp':int((now+timedelta(hours=12)).timestamp()),
            'Data':json.dumps(data,separators=(',',':')), 'SourceId':source_id,'Scope':scope}
        parts=[base64url(json.dumps(v,separators=(',',':')).encode())
               for v in ({'alg':'ES384','typ':'JWT'},claims)]
        signing_input=b'.'.join(parts)
        signature=self._key.sign(signing_input,ec.ECDSA(hashes.SHA384()))
        r,s=decode_dss_signature(signature)
        return (signing_input+b'.'+base64url(r.to_bytes(48,'big')+s.to_bytes(48,'big'))).decode()
