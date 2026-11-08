from datetime import datetime,timezone
from device_identity import DeviceIdentity
from dcg_client import DcgClient

def wake_phone(account):
    stored=account['trust']
    trust=DeviceIdentity.from_pem(stored['client_id'],stored['key'],stored['certificate'])
    data={'DCG-Environment':'Prod','IgnoreDeviceDisabledStatus':'True',
          'DCG-RequestNewSession':'True','DCG-HubRegion':account['pairing_session'].get('region','WestEurope')}
    jwt=trust.sign_scoped_data(data,source_id=account['client_id'],scope='wake',now=datetime.now(timezone.utc))
    payload={'collapseKey':'YPPWake','deviceId':account['pairing_session']['partnerDcgClientId'],
             'priority':'normal','ttl':60,'data':dict(data,**{'DCG-CryptoWakeJwt':jwt})}
    return DcgClient(account).request('POST','/Dispatcher/Wake',version='1.5.0',payload=payload,auth='device')

if __name__=='__main__':
    from account_store import load_account
    from urllib.error import HTTPError
    account,_=load_account()
    try:
        response=wake_phone(account)
        print({'wake_accepted':True,'fields':list(response) if isinstance(response,dict) else []})
    except HTTPError as error:print({'wake_accepted':False,'http_error':error.code})
