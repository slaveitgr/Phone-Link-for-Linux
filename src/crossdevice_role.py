"""Additional WEA identity for PC controls; preserves the existing PL identity.

All keys stay in this application's OS keyring item. No credentials are logged.
"""
import uuid
from datetime import datetime,timezone,timedelta
from account_store import serialize_identity,save_account
from device_identity import DeviceIdentity
from identity_service import IdentityService
from device_service import DeviceService


def ensure_role(account):
    role=account.get('wea')
    if role is None:
        identity=DeviceIdentity(str(uuid.uuid4()),now=datetime.now(timezone.utc),
            certificate_validity=timedelta(days=365),clock_skew=timedelta(hours=12))
        role=serialize_identity(identity)
        account['wea']=role
        if not save_account(account):raise RuntimeError('Could not preserve role identity')
    else:identity=DeviceIdentity.from_pem(role['client_id'],role['key'],role['certificate'])
    if 'device_auth' not in role:
        role['device_auth']=IdentityService(lambda:account['msa']['access_token']).create_identity(identity)
        if not save_account(account):raise RuntimeError('Could not preserve role authentication')
    if 'trust' not in role:
        trust=DeviceIdentity('trust_'+role['client_id'],now=datetime.now(timezone.utc),
            certificate_validity=timedelta(days=365),clock_skew=timedelta(hours=12))
        role['trust']=serialize_identity(trust)
        if not save_account(account):raise RuntimeError('Could not preserve role trust')
    else:trust=DeviceIdentity.from_pem(role['trust']['client_id'],role['trust']['key'],role['trust']['certificate'])
    if 'enrollment' not in role:
        response,_=DeviceService(lambda:account.get('msa_sapi',account['msa'])['access_token'],lambda:role['device_auth']['accessToken']).enroll(
            role['client_id'],logical_device_id=account['logical_device_id'],client_type='WEA',trust_identity=trust)
        records=response.get('devices',[])
        own=next((x for x in records if x.get('id')==role['client_id']),None)
        if not own or own.get('clientType')!='WEA':raise RuntimeError('Role enrollment was not confirmed')
        role['enrollment']=response
        if not save_account(account):raise RuntimeError('Could not preserve enrollment')
    return role


def connection_account(account):
    role=dict(account['wea'])
    role.update(msa=account['msa'],logical_device_id=account['logical_device_id'],pairing_session=dict(account['pairing_session']))
    return role
