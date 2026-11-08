"""Authenticated DCG calls for this user's consented Phone Link connection."""
import base64,hashlib,json,secrets,uuid
from urllib.parse import urlencode,urlsplit
from pairing_service import http_transport

class DcgClient:
    def __init__(self,account,*,transport=http_transport):
        self.account=account
        self.transport=transport
        # App-scoped opaque identity is a Linux design choice; no hardware ID is read.
        if 'logical_device_id' not in account:
            account['logical_device_id']=base64.b64encode(hashlib.sha256(secrets.token_bytes(32)).digest()).decode()
        self.session_id=str(uuid.uuid4())

    def headers(self,*,auth='msa',partner=False):
        a=self.account
        token=a['msa']['access_token'] if auth=='msa' else a['device_auth']['accessToken']
        h={'Authorization':'Bearer '+token,'Authorization-Type':'MSA',
           'Dcg-Token':a['device_auth']['accessToken'],
           'DCG-AppId':'Microsoft.YourPhone_8wekyb3d8bbwe','DCG-AppVersion':'1.26101.114.0',
           'DCG-LogicalDeviceId':a['logical_device_id'],'DCG-SessionId':self.session_id,
           'DCG-RingName':'Public','DCG-OS':'Windows','DCG-OSVersion':'10.0.26200',
           'Accept':'application/json'}
        if auth=='msa':
            h.update({'UserIdentityType':'MSA','UserIdentityToken':token})
        if partner:h['DCG-PartnerId']=a['pairing_session']['partnerDcgClientId']
        return h

    def request(self,method,route,*,version=None,payload=None,auth='msa',origin='https://dcg.microsoft.com',partner=False,query=None):
        p=urlsplit(origin)
        if p.scheme!='https' or not (p.hostname=='dcg.microsoft.com' or p.hostname.endswith('.dcg.microsoft.com')) or p.username or p.password or p.port not in (None,443):
            raise ValueError('Untrusted DCG origin')
        if not route.startswith('/') or '?' in route or '#' in route:raise ValueError('Invalid DCG route')
        params=dict(query or {})
        if version:params['api-version']=version
        url=origin.rstrip('/')+route+('?' + urlencode(params) if params else '')
        headers=self.headers(auth=auth,partner=partner)
        body=None
        if payload is not None:
            body=json.dumps(payload).encode();headers['Content-Type']='application/json'
        return self.transport(method,url,headers,body)
