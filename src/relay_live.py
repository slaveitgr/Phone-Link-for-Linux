"""Real DCG/SignalR relay connection. Logs event names, never payloads or tokens."""
import asyncio,json,secrets,uuid,time,sys
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from urllib.request import Request,build_opener
from websockets.asyncio.client import connect
from account_store import load_account,save_account
from dcg_client import DcgClient
from pairing_service import NoRedirects
from relay_protocol import frame,SignalRDecoder,drm_encode,drm_decode,dcg_fragment,FragmentAssembler
from phone_app import status
from wake_live import wake_phone
from runtime_cache import update_notifications,take_command,command_result,update_clipboard,snapshot
from notification_decode import notification_records
from value_set_codec import connection_configuration,clipboard_request
from remote_lock import safe_shell_available,handle_modern,handle_legacy,RESOURCE_PATH as LOCK_PATH
from pc_status import build_status_response,build_status_publication
from pc_session import is_locked
sys.path.insert(0,str(Path(__file__).resolve().parent/'generated'))
from platform_sdk.v1.device_resource_manager_pb2 import DeviceResourceManagerMessage,DeviceResourceManagerResponseMessage
from device_info.v1.status_pb2 import DeviceStatusResponseMessage,DeviceStatusRequestMessage
from phone_contacts import ContactSync
from runtime_cache import update_contacts
from phone_wallpaper import wallpaper_request,cache_home_wallpaper,cache_legacy_home_wallpaper
from value_set.valueset_pb2 import ValueSet
from platform_sdk.v1.msaep_message_pb2 import MsaepMessage
from platform_sdk.v1.platform_message_pb2 import PlatformDisconnectRequest

def azure_request(url,token):
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname.endswith('.service.signalr.net') or p.username or p.password:
        raise ValueError('Unexpected Azure relay origin')
    r=Request(url,data=b'',method='POST',headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
    with build_opener(NoRedirects()).open(r,timeout=20) as response:
        raw=response.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError('Relay negotiation exceeds limit')
        return json.loads(raw)

def trace():
    return {'TraceId':secrets.token_hex(16),'ParentId':secrets.token_hex(8),'TraceFlags':0,
       'TraceState':{'ypScenarioId':'SendConnectedMessage','ypTriggerId':'ConnectingWithPartner'}}

async def run(account,*,duration=None,profile="PL"):
    def connection_status(state,message,**kwargs):
        if profile=="PL":status(state,message,**kwargs)
        else:print(json.dumps({"event":"crossdevice_connection_state","state":state}),flush=True)
    client=DcgClient(account)
    response=await asyncio.to_thread(client.request,'POST','/relayhub/negotiate',auth='device',
                  partner=True,query={'negotiateVersion':'1'})
    service_url=response['url'];token=response['accessToken'];p=urlsplit(service_url)
    query=dict(parse_qsl(p.query));query['negotiateVersion']='1'
    negotiate=urlunsplit((p.scheme,p.netloc,p.path.rstrip('/')+'/negotiate',urlencode(query),''))
    second=await asyncio.to_thread(azure_request,negotiate,token)
    query.pop('negotiateVersion',None)
    query['id']=second.get('connectionToken') or second['connectionId']
    wsurl=urlunsplit(('wss',p.netloc,p.path,urlencode(query),''))
    headers={k:v for k,v in client.headers(partner=True).items() if k.startswith('DCG-')}
    headers['Authorization']='Bearer '+token
    headers['DCG-HubRegion']=account['pairing_session'].get('region','WestEurope')
    headers['DCG-HeartBeatFrequency']='15'
    connection_status('connecting','Η σύζευξη είναι αποθηκευμένη. Συνδέεται στο ζωντανό κανάλι του POCO.',authenticated=True,actions=['open'])
    async with connect(wsurl,additional_headers=headers,max_size=16*1024*1024,
                       ping_interval=15,ping_timeout=30,open_timeout=20) as websocket:
        await websocket.send('{"protocol":"messagepack","version":1}\x1e')
        handshake=await asyncio.wait_for(websocket.recv(),20)
        if isinstance(handshake,bytes):handshake=handshake.decode()
        first,_,rest=handshake.partition('\x1e')
        result=json.loads(first)
        if result.get('error'):raise RuntimeError('SignalR handshake rejected')
        print(json.dumps({'event':'relay_handshake_accepted'}),flush=True)
        partner=account['pairing_session']['partnerDcgClientId']
        await websocket.send(frame([1,{},'1','SendConnectedAsync',[trace(),partner,{}],[]]))
        decoder=SignalRDecoder()
        assembler=FragmentAssembler()
        deadline=time.monotonic()+duration if duration else float('inf')
        last_status=0;partner_connected=False
        device={'name':'POCO F8 Ultra'}
        request_ids=set()
        pending_resources={}
        pending_contacts={}
        latest_contact_query=None
        last_phone_refresh=0
        sequence=1
        shape_logged=False
        last_peer=time.monotonic()
        envelope_types=set()
        configured=False
        pending_copies={}
        pending_status_publications=set()
        last_ping=time.monotonic()
        def publish():
            connection_status('connected','Το POCO είναι συνδεδεμένο στο ζωντανό κανάλι.',authenticated=True,
                   actions=['open'],device=device.copy(),summary={'notification_count':len(snapshot()['notifications'])},capabilities=(['battery'] if 'battery_percent' in device else [])+(['clipboard'] if configured else []))
        async def send_payload(route,body,*,plane=0,headers=None):
            nonlocal sequence
            identifier=str(uuid.uuid4());request_ids.add(identifier)
            metadata={'_route':route,'_requestId':identifier,'_rejectionVersion':'1',
                      'ms-content-type':'application/x-binary'}
            metadata.update(headers or {})
            envelope=dcg_fragment(drm_encode(metadata,body),client.session_id,sequence,plane=plane)
            sent_sequence=sequence;sequence+=1
            context=trace()
            if route=='/connect/v1':context['TraceState'].update(ypScenarioId='EstablishSyncSession',ypTriggerId='ConnectingWithPartner')
            if route=='/clipboard':context['TraceState'].update(ypScenarioId='PCPhoneCopy',ypTriggerId='PCPhoneMessageReceived',isuserinitiated='True')
            await websocket.send(frame([1,{},str(sequence+1),'SendMessageAsync',[context,partner,envelope],[]]))
            return identifier,sent_sequence
        async def send_response(identifier,payload,*,plane=1):
            nonlocal sequence
            metadata={'_route':'/internal/response','_originalRequestId':identifier,
                      'ms-content-type':'application/x-binary'}
            envelope=dcg_fragment(drm_encode(metadata,payload),client.session_id,sequence,plane=plane)
            sequence+=1
            await websocket.send(frame([1,{},None,'SendMessageAsync',[trace(),partner,envelope],[]]))

        async def configure():
            correlation=str(uuid.uuid4())
            payload=connection_configuration(correlation,account['client_id'],remote_lock=safe_shell_available() and account.get('crossdevice_controls_ready',False))
            payload.entries['IsSampled'].value_type=11
            payload.entries['IsSampled'].bool_value=False
            await send_payload('/connect/v1',payload.SerializeToString())
            print(json.dumps({'event':'phone_configuration_sent'}),flush=True)
        async def request_status():
            body=DeviceResourceManagerMessage(request_type=1,resource_path='/devicestatus',payload=DeviceStatusRequestMessage(request_type=1).SerializeToString()).SerializeToString()
            identifier,_=await send_payload('/DeviceResourceManager',body,plane=1)
            pending_resources[identifier]='status'
            identifier,_=await send_payload('/DeviceResourceManager',wallpaper_request(),plane=1)
            pending_resources[identifier]='wallpaper'
            print(json.dumps({'event':'phone_preview_resources_requested'}),flush=True)
        def envelopes(value,depth=0):
            if depth>6:return
            if isinstance(value,dict):
                if value.get('Type')=='ms-dcg':yield value
                else:
                    for child in list(value.values())[:100]:yield from envelopes(child,depth+1)
            elif isinstance(value,list):
                for child in value[:100]:yield from envelopes(child,depth+1)
        def shape(value,depth=0):
            if depth>3:return type(value).__name__
            if isinstance(value,dict):return {str(k):shape(v,depth+1) for k,v in list(value.items())[:20]}
            if isinstance(value,list):return [shape(v,depth+1) for v in value[:10]]
            return type(value).__name__
        last_lock_check=0
        while time.monotonic()<deadline:
            if profile=='WEA' and time.monotonic()-last_lock_check>=2:
                last_lock_check=time.monotonic()
                if await asyncio.to_thread(is_locked) is True:
                    await send_payload('/PlatformDisconnectRequest',PlatformDisconnectRequest(reason=7).SerializeToString(),plane=1)
                    print(json.dumps({'event':'pc_lock_channel_disconnect'}),flush=True)
                    return
            if not partner_connected and time.monotonic()-last_peer>90:
                raise TimeoutError('Paired phone did not join relay')
            if time.monotonic()-last_ping>=15:
                await websocket.send(frame([6]));last_ping=time.monotonic()
            if partner_connected and profile=="PL":
                if configured and time.monotonic()-last_phone_refresh>60:
                    await request_status()
                    last_phone_refresh=time.monotonic()
                command=take_command()
                if command:
                    if command.get('kind')=='search_contacts':
                        latest_contact_query=command['query']
                        sync=ContactSync(latest_contact_query)
                        identifier,_=await send_payload('/DeviceResourceManager',sync.request(),plane=1)
                        pending_resources[identifier]='contacts';pending_contacts[identifier]=sync
                        update_contacts([],status='syncing')
                    else:
                        _,number=await send_payload('/clipboard',clipboard_request(command['text'],str(uuid.uuid4()),account['client_id']).SerializeToString())
                        pending_copies[number]=command['id']
            if partner_connected and time.monotonic()-last_status>15:
                if time.monotonic()-last_peer<75:publish()
                else:connection_status('connecting','Η σύζευξη είναι αποθηκευμένη. Αναμένεται απόκριση του POCO.',authenticated=True,actions=['open'])
                last_status=time.monotonic()
            try:raw=await asyncio.wait_for(websocket.recv(),1)
            except asyncio.TimeoutError:
                continue
            if isinstance(raw,str):
                print(json.dumps({'event':'unexpected_text_frame'}),flush=True);continue
            for message in decoder.feed(raw):
                kind=message[0]
                if kind==1:
                    target=message[3];args=message[4]
                    print(json.dumps({'event':'hub_invocation','target':target,'argument_count':len(args)}),flush=True)
                    if target=='OnConnected':
                        for arg in args:
                            if isinstance(arg,dict) and isinstance(arg.get('RegionName'),str):
                                account['pairing_session']['region']=arg['RegionName']
                        try:
                            await asyncio.to_thread(wake_phone,account)
                            print(json.dumps({'event':'phone_wake_accepted'}),flush=True)
                        except Exception as error:
                            print(json.dumps({'event':'phone_wake_error','type':type(error).__name__}),flush=True)
                    elif target=='OnPartnerConnected':
                        if args and isinstance(args[0],str) and args[0]!=partner:continue
                        last_peer=time.monotonic()
                        first_connection=not partner_connected
                        partner_connected=True
                        publish()
                        if first_connection:
                            if profile=='PL':await configure()
                            else:
                                refresh=Path.home()/'.local/state/tahoe-phone-link/refresh-pc-session'
                                if refresh.exists() and await asyncio.to_thread(is_locked) is False:
                                    await send_payload('/PlatformDisconnectRequest',PlatformDisconnectRequest(reason=1).SerializeToString(),plane=1)
                                    refresh.unlink(missing_ok=True)
                                    print(json.dumps({'event':'pc_session_requested_refresh_sent'}),flush=True)
                                    await asyncio.sleep(1)
                                    return
                                print(json.dumps({'event':'wea_peer_connected'}),flush=True)
                    elif target=='OnPartnerHeartBeat' and partner_connected:
                        last_peer=time.monotonic()
                        publish()
                    elif target=='OnPartnerDisconnected':
                        partner_connected=False
                        connection_status('disconnected','Η σύζευξη παραμένει αποθηκευμένη. Το POCO δεν είναι τώρα διαθέσιμο.',authenticated=True,actions=['open'])
                    elif target=='OnReceiveMessage':
                        if args and isinstance(args[0],str) and args[0]!=partner:continue
                        last_peer=time.monotonic()
                        if not shape_logged:
                            print(json.dumps({'event':'incoming_structure','shape':shape(args)}),flush=True)
                            shape_logged=True
                        for envelope in envelopes(args):
                            props=envelope.get('Properties',{})
                            raw_body=envelope.get('Raw')
                            if props.get('Type')==1 and props.get('SequenceNumber') in pending_status_publications:
                                pending_status_publications.discard(props['SequenceNumber'])
                                print(json.dumps({'event':'pc_status_transport_ack','success':props.get('Success') is True}),flush=True)
                            if props.get('Type')==1 and props.get('SequenceNumber') in pending_copies:
                                identifier=pending_copies.pop(props['SequenceNumber'])
                                command_result(identifier,'sent' if props.get('Success') is True else 'failed')
                            if props.get('Type')==2:
                                acknowledgement={'Type':'ms-dcg','Properties':{
                                    'Type':1,'Version':1.0,'SequenceNumber':props.get('SequenceNumber',0),
                                    'ErrorNo':0.0,'SessionId':props.get('SessionId',client.session_id),
                                    'Success':True},'Raw':None}
                                await websocket.send(frame([1,{},None,'SendMessageAsync',
                                    [trace(),partner,acknowledgement],[]]))
                            shape_key=(props.get('Type'),type(raw_body).__name__)
                            if shape_key not in envelope_types:
                                envelope_types.add(shape_key)
                                print(json.dumps({'event':'incoming_envelope','message_type':props.get('Type'),
                                    'transport_plane':props.get('MessageType'),'success':props.get('Success'),
                                    'error_number':props.get('ErrorNo'),'raw_type':type(raw_body).__name__,
                                    'raw_size':len(raw_body) if isinstance(raw_body,(bytes,str,list)) else 0}),flush=True)
                            if props.get('Type')==4:
                                reply={'Type':'ms-dcg','Properties':{'Version':1.0,'Type':5,
                                   'SessionId':client.session_id,'RequestId':props.get('RequestId',0.0),
                                   'MessageType':'PRESENCERESPONSE'},'Raw':None}
                                await websocket.send(frame([1,{},None,'SendMessageAsync',[trace(),partner,reply],[]]))
                            if not isinstance(raw_body,bytes):continue
                            try:raw_body=assembler.add(props,raw_body)
                            except (ValueError,TypeError,OverflowError):continue
                            if raw_body is None:continue
                            try:headers,payload=drm_decode(raw_body)
                            except ValueError as error:
                                failure_key=('drm',str(error),props.get('MessageType'))
                                if failure_key not in envelope_types:
                                    envelope_types.add(failure_key)
                                    print(json.dumps({'event':'resource_framing_mismatch','reason':str(error),
                                       'version_byte':raw_body[0] if raw_body else None,
                                       'size':len(raw_body),'fragments':props.get('FragmentCount'),
                                       'declared_header_size':int.from_bytes(raw_body[1:5],'little'),
                                       'declared_pair_count':int.from_bytes(raw_body[5:9],'little')}),flush=True)
                                    if raw_body and raw_body[0]==1:
                                        print(json.dumps({'event':'first_header_lengths',
                                            'first_length':int.from_bytes(raw_body[9:13],'little'),
                                            'second_length':int.from_bytes(raw_body[13:17],'little'),
                                            'first_value_length':int.from_bytes(raw_body[13+int.from_bytes(raw_body[9:13],'little'):17+int.from_bytes(raw_body[9:13],'little')],'little')}),flush=True)
                                continue
                            print(json.dumps({'event':'phone_resource_message','route':headers.get('_route'),'transport_plane':props.get('MessageType'),
                                  'header_names':list(headers),'payload_size':len(payload)}),flush=True)
                            if headers.get('_route')=='/Context/Publish':
                                try:
                                    context_message=MsaepMessage.FromString(payload)
                                    print(json.dumps({'event':'context_msaep_structure','tag':context_message.message_tag,'payload_size':len(context_message.payload),'major':context_message.platform_major_version,'minor':context_message.platform_minor_version}),flush=True)
                                except Exception:pass
                                try:
                                    context_values=ValueSet.FromString(payload)
                                    print(json.dumps({'event':'context_payload_structure','keys':list(context_values.entries),'plane':props.get('MessageType')}),flush=True)
                                except Exception:
                                    print(json.dumps({'event':'context_payload_structure','valueset':False,'plane':props.get('MessageType')}),flush=True)
                            if headers.get('_route')=='/DeviceResourceManager' and props.get('MessageType')==1:
                                sender=args[0] if args and isinstance(args[0],str) else None
                                identifier=headers.get('_requestId')
                                if sender==partner and isinstance(identifier,str) and len(identifier)<200:
                                    try:
                                        request=DeviceResourceManagerMessage.FromString(payload)
                                        response_payload=None
                                        if request.resource_path=='/remotedevicestatus' and request.request_type==1:
                                            response_payload=await asyncio.to_thread(build_status_response)
                                        elif request.resource_path==LOCK_PATH and request.request_type==1:
                                            response_payload=await asyncio.to_thread(handle_modern,request.payload,sender=sender,paired_partner=partner)
                                        if response_payload is not None:
                                            wrapper=DeviceResourceManagerResponseMessage(payload=response_payload,response_type=1)
                                            await send_response(identifier,wrapper.SerializeToString())
                                            print(json.dumps({'event':'pc_resource_response_sent','resource':request.resource_path}),flush=True)
                                    except (ValueError,TypeError):pass
                                continue
                            if headers.get('_route') in ('/legacy/phonecontent','/internal/response'):
                                try:
                                    values=ValueSet.FromString(payload)
                                    related=headers.get('_requestId') or headers.get('_responseId') or headers.get('_originalRequestId')
                                    if related in request_ids and ('capabilities' in values.entries or 'deviceConfiguration' in values.entries):
                                        configured=True
                                        publish()
                                        print(json.dumps({'event':'phone_configuration_acknowledged'}),flush=True)
                                    if 'mimetypes' in values.entries and 'data' in values.entries:
                                        mime=values.entries['mimetypes'];data=values.entries['data']
                                        if mime.value_type==29 and data.value_type==29:
                                            for content_type,text in zip(mime.string_array,data.string_array):
                                                if content_type=='text/plain':update_clipboard(text)
                                    notifications=notification_records(values)
                                    if notifications is not None:
                                        update_notifications(notifications)
                                        print(json.dumps({'event':'notification_update','record_count':len(notifications)}),flush=True)
                                    if 'batteryPercent' in values.entries:
                                        variant=values.entries['batteryPercent']
                                        numeric={4:'int32_value',5:'uint32_value',6:'int64_value',
                                            7:'uint64_value',8:'single_value',9:'double_value'}
                                        field=numeric.get(variant.value_type)
                                        battery=getattr(variant,field,None) if field else None
                                        if type(battery) in (int,float) and 0<=battery<=100:
                                            device['battery_percent']=round(battery)
                                            charging=values.entries.get('batteryCharging')
                                            if charging is not None and charging.value_type==11:
                                                device['charging']=charging.bool_value
                                            publish()
                                            print(json.dumps({'event':'real_battery_received','battery_percent':round(battery)}),flush=True)
                                except Exception:pass
                            related=headers.get('_originalRequestId') or headers.get('_responseId') or headers.get('_requestId')
                            if not args or args[0]!=partner:continue
                            resource=pending_resources.pop(related,None)
                            if resource is None:continue
                            try:
                                wrapper=DeviceResourceManagerResponseMessage.FromString(payload)
                                if resource=='contacts':
                                    sync=pending_contacts.pop(related,None)
                                    if sync is None or sync.query!=latest_contact_query:continue
                                    result=sync.consume(wrapper.payload)
                                    update_contacts(sync.records(),status=result['status'])
                                    if not sync.complete:
                                        identifier,_=await send_payload('/DeviceResourceManager',sync.request(),plane=1)
                                        pending_resources[identifier]='contacts';pending_contacts[identifier]=sync
                                    print(json.dumps({'event':'phone_contacts_page_received','status':result['status'],'count':len(sync.records())}),flush=True)
                                elif resource=='wallpaper':
                                    result=cache_home_wallpaper(wrapper.payload)
                                    device['wallpaper_status']=result['status']
                                    if result.get('path'):device['wallpaper_path']=result['path']
                                    publish()
                                    print(json.dumps({'event':'phone_wallpaper_response','status':result['status']}),flush=True)
                                else:
                                    response=DeviceStatusResponseMessage.FromString(wrapper.payload)
                                    if response.status==1 and response.HasField('info'):
                                        info=response.info
                                        if 0<=info.battery_percent<=100:
                                            device['battery_percent']=info.battery_percent
                                        for field,key in [('battery_charging','charging'),('wifi_state','wifi_enabled')]:
                                            device[key]=getattr(info,field)
                                        if info.bluetooth_state in (10,12):device['bluetooth_enabled']=info.bluetooth_state==12
                                        publish()
                                        print(json.dumps({'event':'phone_device_status_received'}),flush=True)
                            except Exception as error:
                                print(json.dumps({'event':'phone_preview_response_error','type':type(error).__name__}),flush=True)
                elif kind==3:
                    print(json.dumps({'event':'hub_completion','invocation':message[2],
                         'result_kind':message[3]}),flush=True)
                elif kind==7:raise RuntimeError('SignalR relay closed')

if __name__=='__main__':
    try:
        account,_=load_account()
        asyncio.run(run(account,duration=90))
    except Exception as error:
        print(json.dumps({'event':'relay_error','type':type(error).__name__}),flush=True)
