"""DCG enrollment reconstructed from Windows CIL; authenticated calls only."""
import base64
import json,re
from urllib.parse import urlencode
from datetime import datetime,timezone,timedelta
from cryptography.hazmat.primitives import serialization
from device_identity import DeviceIdentity
from pairing_service import PairingService,AuthenticationRequired,http_transport

class DeviceService:
    def __init__(self,msa_provider,device_token_provider,*,transport=http_transport,
                 base_url='https://dcg.microsoft.com'):
        self.base_url=PairingService(msa_provider,'1.5.0',base_url=base_url).base_url
        self.msa_provider=msa_provider
        self.device_token_provider=device_token_provider
        self.transport=transport

    def enroll(self,client_id,*,display_name='Ubuntu desktop',now=None,logical_device_id=None,client_type='PL',trust_identity=None,partner_device_key=None):
        if client_type not in ('PL','WEA'):raise ValueError('Unsupported PC role')
        msa=self.msa_provider();dcg=self.device_token_provider()
        for token in (msa,dcg):
            if not isinstance(token,str) or not token or '\r' in token or '\n' in token:
                raise AuthenticationRequired('Authorized MSA and DCG tokens required')
        trust=trust_identity or DeviceIdentity('trust_'+client_id,now=now or datetime.now(timezone.utc),
            certificate_validity=timedelta(days=365),clock_skew=timedelta(hours=12))
        if trust.client_id!='trust_'+client_id:raise ValueError('Trust identity mismatch')
        body={'certificates':{'SelfSigned':[base64.b64encode(trust.certificate.public_bytes(
            serialization.Encoding.DER)).decode()]},'metadata':{
            'clientType':client_type,'clientVersion':'1.26101.114.0','displayName':display_name,
            'manufacture':'Ubuntu','modelName':'Linux desktop','modelVersion':'1',
            # The phone's protocol filters PC role by this legacy wire value.
            'osName':'Windows','osVersion':'10.0.26200','consentVersion':1,
            'isEnabled':True,'capabilities':[],'customData':''}}
        headers={'Authorization':'Bearer '+msa,'Authorization-Type':'MSA',
            'Dcg-Token':dcg,'UserIdentityType':'MSA','UserIdentityToken':msa,
            'DCG-AppId':'Microsoft.YourPhone_8wekyb3d8bbwe',
            'DCG-AppVersion':'1.26101.114.0','DCG-RingName':'Public','DCG-OS':'Windows',
            'DCG-OSVersion':'10.0.26200','Content-Type':'application/json','Accept':'application/json'}
        if logical_device_id:
            if not isinstance(logical_device_id,str) or '\r' in logical_device_id or '\n' in logical_device_id:
                raise ValueError('Invalid logical device identifier')
            headers['DCG-LogicalDeviceId']=logical_device_id
            body['metadata']['distinguishedDeviceId']=logical_device_id
        query={'api-version':'1.5.0'}
        if partner_device_key is not None:
            if not re.fullmatch(r'PartnerDeviceKey~[a-zA-Z0-9]{64}',partner_device_key):raise ValueError('Invalid issued pairing key')
            query['pop-device-key']=partner_device_key
        response=self.transport('POST',self.base_url+'/DeviceAuthProxy/EnrollDevice?'+
            urlencode(query),headers,json.dumps(body).encode())
        if not isinstance(response,dict):raise ValueError('Invalid enrollment response')
        return response,trust
