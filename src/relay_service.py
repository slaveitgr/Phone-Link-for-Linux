"""Persistent user service: keeps the phone connection independent of its window."""
import asyncio,time,json,threading
from account_store import load_account,save_account
from secret_store import KeyringLocked
from phone_app import status
from relay_live import run
from msa_oauth import refresh_tokens
from identity_service import IdentityService
from runtime_cache import start_bridge,update_contacts,update_call_history,update_phone_favorites
from tray_icon import start_tray
from crossdevice_role import connection_account
from device_identity import DeviceIdentity
from pc_session import is_locked

async def connection_cycle(account,duration):
    async def serve(value,profile):
        deadline=time.monotonic()+duration
        backoff=5
        was_locked=False
        while time.monotonic()<deadline:
            if profile=='WEA':
                locked=await asyncio.to_thread(is_locked)
                if locked is True:
                    if not was_locked:print(json.dumps({'event':'pc_session_locked_channel_paused'}),flush=True)
                    was_locked=True
                    await asyncio.sleep(2)
                    continue
                if locked is None:
                    await asyncio.sleep(2)
                    continue
                if was_locked:
                    print(json.dumps({'event':'pc_session_unlocked_channel_reconnecting'}),flush=True)
                    was_locked=False
                    backoff=2
            try:
                await run(value,duration=max(1,deadline-time.monotonic()),profile=profile)
                backoff=5
            except Exception as error:
                print(json.dumps({'event':'connection_retry','profile':profile,'type':type(error).__name__}),flush=True)
            remaining=deadline-time.monotonic()
            if remaining>0:await asyncio.sleep(min(backoff,remaining))
            backoff=min(backoff*2,60)
    tasks=[serve(account,'PL')]
    if account.get('wea_enabled') is True and account.get('wea',{}).get('enrollment'):tasks.append(serve(connection_account(account),'WEA'))
    await asyncio.gather(*tasks)

def sync_phone_contacts():
    try:
        from phone_contacts_bluetooth import pull_contacts
        update_contacts([],status='syncing')
        result=pull_contacts()
        if result['status']=='ok':
            update_contacts(result['contacts'],status='ok',full=True)
        else:update_contacts([],status=result['status'])
        print(json.dumps({'event':'bluetooth_contacts_sync','status':result['status'],'count':result['count']}),flush=True)
    except Exception as error:
        update_contacts([],status='bluetooth_unavailable')
        print(json.dumps({'event':'bluetooth_contacts_sync_error','type':type(error).__name__}),flush=True)

    from phone_call_history import pull_call_history,pull_favorites
    from phone_calls import PhoneCalls
    from phone_config import bluetooth_address
    while True:
        try:
            address=bluetooth_address()
            active=bool(address and PhoneCalls(address).status().get('calls'))
            if not active:
                history=pull_call_history()
                update_call_history(history['calls'],history['status'])
                favorites=pull_favorites()
                update_phone_favorites(favorites['favorites'],favorites['status'])
                print(json.dumps({'event':'bluetooth_call_data_sync','history_status':history['status'],'history_count':history['count'],'favorites_status':favorites['status'],'favorites_count':favorites['count']}),flush=True)
        except Exception as error:
            print(json.dumps({'event':'bluetooth_call_data_error','type':type(error).__name__}),flush=True)
        time.sleep(60)

bridge=start_bridge()
threading.Thread(target=sync_phone_contacts,daemon=True).start()
tray=start_tray()
account=None
retry=5
while True:
    try:
        if account is None:
            saved=load_account()
            if saved is None:
                status('signed_out','Δεν υπάρχει αποθηκευμένος λογαριασμός Microsoft.',actions=['login','open'])
                time.sleep(30)
                continue
            account,identity=saved
        if account.get('pairing_session',{}).get('state')!='DEVICE_PAIRED':
            status('pairing','Άνοιξε το Phone Link για να ολοκληρώσεις τη σύζευξη.',authenticated=True,actions=['open'])
            account=None;time.sleep(15);continue
        expires=account['msa'].get('obtained_at',0)+float(account['msa'].get('expires_in',0))
        if expires<time.time()+300:
            account['msa']=refresh_tokens(account['msa'])
            save_account(account)
            print(json.dumps({'event':'microsoft_authorization_refreshed'}),flush=True)
        if account['device_auth']['epochExpirationTime']<time.time()+300:
            account['device_auth']=IdentityService(lambda:account['msa']['access_token']).sign_in(identity)
            save_account(account)
        role=account.get('wea',{})
        if role.get('enrollment') and role['device_auth']['epochExpirationTime']<time.time()+300:
            role_identity=DeviceIdentity.from_pem(role['client_id'],role['key'],role['certificate'])
            role['device_auth']=IdentityService(lambda:account['msa']['access_token']).sign_in(role_identity)
            save_account(account)
        expires=account['msa'].get('obtained_at',0)+float(account['msa'].get('expires_in',0))
        asyncio.run(connection_cycle(account,min(1800,max(60,expires-time.time()-300))))
        retry=5
    except KeyringLocked:
        status('disconnected','Η σύζευξη είναι αποθηκευμένη. Ξεκλείδωσε το Login keyring.',actions=['open'])
    except Exception as error:
        print(json.dumps({'event':'relay_reconnect','type':type(error).__name__}),flush=True)
        status('disconnected','Η σύζευξη παραμένει αποθηκευμένη. Γίνεται επανασύνδεση.',authenticated=True,actions=['open'])
    time.sleep(retry)
    retry=min(retry*2,60)
