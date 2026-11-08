"""Update this app's enrolled device metadata without rotating trust certificates.

Native Kiota SetDeviceInfoRequestBuilder: cdeh-setDeviceInfo-builder-evidence.json.
"""
from dcg_client import DcgClient
import base64,re
from cryptography import x509
from cryptography.hazmat.primitives import serialization


def update_metadata(account,*,client_type='PL',enabled=True,display_name='Ubuntu desktop',partner_device_key=None):
    if client_type not in ('PL','WEA'):raise ValueError('Unsupported PC client role')
    metadata={'clientType':client_type,'clientVersion':'1.26101.114.0',
        'displayName':display_name,'manufacture':'Ubuntu','modelName':'Linux desktop',
        'modelVersion':'1','osName':'Windows','osVersion':'10.0.26200',
        'consentVersion':1,'isEnabled':bool(enabled),'capabilities':[],'customData':'',
        # Linux grouping design: one app-scoped stable ID for both PC roles.
        'distinguishedDeviceId':account['logical_device_id']}
    certificate=x509.load_pem_x509_certificate(account['trust']['certificate'].encode())
    certificates={'SelfSigned':[base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode()]}
    query=None
    if partner_device_key is not None:
        if not re.fullmatch(r'PartnerDeviceKey~[a-zA-Z0-9]{64}',partner_device_key):raise ValueError('Invalid issued pairing key')
        query={'pop-device-key':partner_device_key}
    return DcgClient(account).request('POST','/DeviceAuthProxy/SetDeviceInfo',
        version='1.5.0',payload={'metadata':metadata,'certificates':certificates},auth='msa',query=query)
