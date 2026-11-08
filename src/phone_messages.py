"""Read-only SMS access over the selected phone's BlueZ OBEX MAP service.

Only explicit caller invocation reads phone data. No send, delete, read-flag
mutation, persistence or content logging. Temporary bMessages are private and
removed before returning RAM-only records.
"""
import hashlib,os,re,sys,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
sys.path.append('/usr/lib/python3/dist-packages')
from gi.repository import Gio,GLib
from phone_config import bluetooth_address

SERVICE='org.bluez.obex';ROOT='/org/bluez/obex';CLIENT='org.bluez.obex.Client1'
MAP='org.bluez.obex.MessageAccess1';MESSAGE='org.bluez.obex.Message1'
PROPS='org.freedesktop.DBus.Properties';TRANSFER='org.bluez.obex.Transfer1'
MAX_BODY_BYTES=256*1024


def parse_bmessage(raw):
    """Extract bounded UTF-8 SMS text from bMessage, excluding envelope/vCards."""
    if not isinstance(raw,bytes) or len(raw)>MAX_BODY_BYTES:raise ValueError('Invalid SMS body size')
    normalized=raw.replace(b'\r\n',b'\n').replace(b'\r',b'\n')
    marker=b'BEGIN:MSG\n'
    if marker not in normalized:return ''
    content=normalized.split(marker,1)[1]
    if b'\nEND:MSG' not in content:raise ValueError('Incomplete SMS body')
    content=content.rsplit(b'\nEND:MSG',1)[0]
    # MAP SMS transfers use UTF-8; preserve body whitespace and line breaks.
    return content.decode('utf-8','replace')[:65536]


def _timestamp(value):
    if not isinstance(value,str):return None
    try:
        stamp=datetime.strptime(value.rstrip('Z'),'%Y%m%dT%H%M%S')
        stamp=stamp.replace(tzinfo=timezone.utc) if value.endswith('Z') else stamp.astimezone()
        return stamp.isoformat()
    except ValueError:return None


def _selected_device_ready(address):
    """Read-only; never enables Bluetooth or pairs/connects another device."""
    try:
        bus=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
        objects=bus.call_sync('org.bluez','/','org.freedesktop.DBus.ObjectManager','GetManagedObjects',None,None,Gio.DBusCallFlags.NONE,5000,None).unpack()[0]
        for interfaces in objects.values():
            device=interfaces.get('org.bluez.Device1',{})
            if str(device.get('Address','')).upper()==address.upper():
                return bool(device.get('Paired') and device.get('Connected'))
    except GLib.Error:pass
    return False


def pull_messages(address=None,*,max_messages=50,timeout=60,include_bodies=True):
    """Read recent inbox/sent SMS messages; return status + RAM-only records.

    Android message-sharing prompts are left to the phone user. `Get` retrieves
    content without setting Message1.Read, and no mutating MAP method is called.
    BlueZ public APIs: org.bluez.obex.MessageAccess1 and Message1.
    """
    address=address or bluetooth_address()
    if not isinstance(address,str) or not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',address):return {'status':'bluetooth_unavailable','messages':[],'count':0}
    if type(max_messages) is not int or not 1<=max_messages<=50:raise ValueError('Invalid SMS count limit')
    if not 1<=timeout<=120:raise ValueError('Invalid SMS timeout')
    if not _selected_device_ready(address):return {'status':'bluetooth_unavailable','messages':[],'count':0}
    context=GLib.MainContext.new();context.push_thread_default()
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None);states={}
    def changed(connection,sender,path,interface,signal,parameters):
        iface,values,_=parameters.unpack()
        if iface==TRANSFER and 'Status' in values:states[path]=values['Status']
    subscription=bus.signal_subscribe(SERVICE,PROPS,'PropertiesChanged',None,TRANSFER,Gio.DBusSignalFlags.NONE,changed)
    deadline=time.monotonic()+timeout
    def call(path,interface,method,args=None):
        remaining=max(1,min(20000,int((deadline-time.monotonic())*1000)))
        return bus.call_sync(SERVICE,path,interface,method,args,None,Gio.DBusCallFlags.NONE,remaining,None).unpack()
    session=None;directory=None;target=None
    try:
        session=call(ROOT,CLIENT,'CreateSession',GLib.Variant('(sa{sv})',(address.upper(),{'Target':GLib.Variant('s','map')})))[0]
        xml=call(session,'org.freedesktop.DBus.Introspectable','Introspect')[0]
        if MAP not in xml:return {'status':'unsupported','messages':[],'count':0}
        def folders():
            return call(session,MAP,'ListFolders',GLib.Variant('(a{sv})',({'MaxCount':GLib.Variant('q',100)},)))[0]
        names={f.get('Name') for f in folders()}
        if 'telecom' in names:
            call(session,MAP,'SetFolder',GLib.Variant('(s)',('telecom',)));names={f.get('Name') for f in folders()}
        if 'msg' in names:
            call(session,MAP,'SetFolder',GLib.Variant('(s)',('msg',)));names={f.get('Name') for f in folders()}
        if not names.intersection({'inbox','sent'}):return {'status':'unsupported','messages':[],'count':0}
        records=[]
        filters={'MaxCount':GLib.Variant('q',max_messages),'Fields':GLib.Variant('as',['subject','timestamp','sender','sender-address','recipient','recipient-address','type','read','sent'])}
        for folder in ('inbox','sent'):
            if folder not in names:continue
            listing=call(session,MAP,'ListMessages',GLib.Variant('(sa{sv})',(folder,filters)))[0]
            for path,props in (listing.items() if isinstance(listing,dict) else listing):
                if props.get('Type') not in ('sms-gsm','sms-cdma'):continue
                outgoing=bool(props.get('Sent')) or folder=='sent'
                records.append({'id':'map:'+hashlib.sha256(path.rsplit('/',1)[-1].encode()).hexdigest(),
                    'sender':str(props.get('Recipient' if outgoing else 'Sender',''))[:500],
                    'number':str(props.get('RecipientAddress' if outgoing else 'SenderAddress',''))[:200],
                    'body':str(props.get('Subject',''))[:65536],
                    'timestamp':_timestamp(props.get('Timestamp')),
                    'type':'outgoing' if outgoing else 'incoming','unread':not bool(props.get('Read',True)),
                    'body_complete':False,'_path':path})
        records.sort(key=lambda r:r['timestamp'] or '',reverse=True);records=records[:max_messages]
        if include_bodies and records:
            runtime=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))/'tahoe-phone-link'
            if runtime.is_symlink():raise ValueError('Unexpected runtime path')
            runtime.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(runtime,0o700)
            directory=Path(tempfile.mkdtemp(prefix='sms-',dir=runtime));os.chmod(directory,0o700)
            for record in records:
                if time.monotonic()>=deadline:break
                fd,name=tempfile.mkstemp(prefix='message-',suffix='.bmsg',dir=directory);os.close(fd);target=Path(name)
                transfer,_=call(record['_path'],MESSAGE,'Get',GLib.Variant('(sb)',(str(target),False)))
                while time.monotonic()<deadline:
                    while context.pending():context.iteration(False)
                    if target.exists() and target.stat().st_size>MAX_BODY_BYTES:raise ValueError('SMS body size limit exceeded')
                    state=states.get(transfer)
                    if state=='complete':
                        os.chmod(target,0o600);record['body']=parse_bmessage(target.read_bytes());record['body_complete']=True;break
                    if state=='error':break
                    time.sleep(.03)
                target.unlink(missing_ok=True);target=None
        for record in records:record.pop('_path',None)
        return {'status':'ok','source':'bluetooth_map','messages':records,'count':len(records)}
    except GLib.Error as error:
        code=Gio.DBusError.get_remote_error(error) or ''
        status='need_permissions' if any(x in code for x in ('NotAuthorized','Forbidden','NotPermitted')) else 'bluetooth_unavailable'
        return {'status':status,'messages':[],'count':0,'error_code':code}
    finally:
        bus.signal_unsubscribe(subscription)
        context.pop_thread_default()
        if session:
            try:bus.call_sync(SERVICE,ROOT,CLIENT,'RemoveSession',GLib.Variant('(o)',(session,)),None,Gio.DBusCallFlags.NONE,5000,None)
            except GLib.Error:pass
        if target:target.unlink(missing_ok=True)
        if directory:
            try:directory.rmdir()
            except OSError:pass
