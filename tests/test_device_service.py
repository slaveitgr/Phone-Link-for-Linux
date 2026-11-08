import base64,json,unittest
from datetime import datetime,timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from device_service import DeviceService
class EnrollmentTests(unittest.TestCase):
    def test_distinct_msa_and_device_credentials_and_trust_certificate(self):
        calls=[]
        def send(*args):calls.append(args);return {'deviceId':'fixture'}
        response,trust=DeviceService(lambda:'offline-msa',lambda:'offline-dcg',transport=send).enroll(
            'fixture',now=datetime(2026,11,7,tzinfo=timezone.utc))
        method,url,headers,body=calls[0]
        self.assertEqual(headers['Authorization'],'Bearer offline-msa')
        self.assertEqual(headers['Dcg-Token'],'offline-dcg')
        self.assertTrue(url.endswith('EnrollDevice?api-version=1.5.0'))
        body=json.loads(body)
        certificate=x509.load_der_x509_certificate(base64.b64decode(body['certificates']['SelfSigned'][0]))
        self.assertEqual(certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value,'trust_fixture')
        self.assertEqual(body['metadata']['displayName'],'Ubuntu desktop')
if __name__=='__main__':unittest.main()
