"""Read the selected paired phone's PBAP address book into RAM only.

Actual BlueZ OBEX API introspected on this machine. No phone access on import.
Only names and telephone numbers are requested; temporary vCard is unlinked.
"""
import hashlib,os,quopri,re,sys,tempfile,time
from pathlib import Path
sys.path.append('/usr/lib/python3/dist-packages')
from gi.repository import Gio,GLib

from phone_config import bluetooth_address
SERVICE='org.bluez.obex'
ROOT='/org/bluez/obex'
CLIENT='org.bluez.obex.Client1'
PBAP='org.bluez.obex.PhonebookAccess1'
PROPS='org.freedesktop.DBus.Properties'
MAX_BYTES=32*1024*1024
MAX_CONTACTS=20000


def _unescape(value):
    return re.sub(r'\\([nN,;\\])',lambda m:'\n' if m[1] in ('n','N') else m[1],value)


def parse_vcards(raw):
    """Parse requested vCard3 fields only. Does not persist or log records."""
    if not isinstance(raw,bytes) or len(raw)>MAX_BYTES:raise ValueError('Invalid phonebook size')
    lines=[]
    for line in raw.replace(b'\r\n',b'\n').replace(b'\r',b'\n').split(b'\n'):
        if line.startswith((b' ',b'\t')) and lines:lines[-1]+=line[1:]
        elif lines and lines[-1].endswith(b'=') and b'ENCODING=QUOTED-PRINTABLE' in lines[-1].upper():lines[-1]=lines[-1][:-1]+line
        else:lines.append(line)
    records=[];current=None
    for line in lines:
        if line.upper()==b'BEGIN:VCARD':current={'numbers':[]};continue
        if line.upper()==b'END:VCARD':
            if current and current['numbers']:
                name=current.get('name') or current.get('structured_name') or current['numbers'][0]['number']
                identity=current.get('uid') or hashlib.sha256((name+'\0'+'\0'.join(n['number'] for n in current['numbers'])).encode()).hexdigest()
                records.append({'id':'pbap:'+identity[:300],'name':name[:500],'numbers':current['numbers'][:100]})
                if len(records)>MAX_CONTACTS:raise ValueError('Phonebook record limit exceeded')
            current=None;continue
        if current is None or b':' not in line:continue
        key,value=line.split(b':',1);params=key.decode('ascii','ignore').split(';');field=params[0].split('.')[-1].upper()
        if field not in ('FN','N','TEL','UID'):continue
        charset='utf-8'
        for param in params[1:]:
            if param.upper().startswith('CHARSET='):charset=param.split('=',1)[1].strip('"')
        if any(p.upper()=='ENCODING=QUOTED-PRINTABLE' for p in params[1:]):value=quopri.decodestring(value)
        try:text=_unescape(value.decode(charset,'replace'))
        except LookupError:text=_unescape(value.decode('utf-8','replace'))
        if field=='FN':current['name']=text.strip()
        elif field=='UID':current['uid']=text.strip()
        elif field=='N':
            parts=text.split(';');current['structured_name']=' '.join(x for x in (parts[1:2]+parts[0:1]) if x).strip()
        elif field=='TEL':
            number=text.removeprefix('tel:').strip()[:100]
            label=next((p.split('=',1)[1] for p in params[1:] if p.upper().startswith('TYPE=')),'Phone')[:100]
            if number and number not in {n['number'] for n in current['numbers']}:current['numbers'].append({'number':number,'label':label})
    # UID-less duplicate cards can appear in Android's combined address book.
    return list({r['id']:r for r in records}.values())


def pull_contacts(address=None,*,timeout=60):
    """Caller-authorized PBAP PullAll. Returns actual contacts in RAM.

    Temporary file and session are removed on success, failure and timeout.
    Permission prompts, if required by Android, are left to the phone user.
    """
    address=address or bluetooth_address()
    if not isinstance(address,str) or not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',address):raise ValueError('Invalid paired phone address')
    if not 1<=timeout<=120:raise ValueError('Invalid transfer timeout')
    context=GLib.MainContext.new();context.push_thread_default()
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    states={}
    def changed(connection,sender,path,interface,signal,parameters):
        iface,values,_=parameters.unpack()
        if iface=='org.bluez.obex.Transfer1' and 'Status' in values:states[path]=values['Status']
    subscription=bus.signal_subscribe(SERVICE,PROPS,'PropertiesChanged',None,
        'org.bluez.obex.Transfer1',Gio.DBusSignalFlags.NONE,changed)
    def call(path,interface,method,args=None,limit=10000):
        return bus.call_sync(SERVICE,path,interface,method,args,None,Gio.DBusCallFlags.NONE,limit,None).unpack()
    session=None;transfer=None;directory=None;target=None
    try:
        session=call(ROOT,CLIENT,'CreateSession',GLib.Variant('(sa{sv})',(address.upper(),{'Target':GLib.Variant('s','pbap')})),limit=min(25000,int(timeout*1000)))[0]
        call(session,PBAP,'Select',GLib.Variant('(ss)',('int','pb')))
        runtime=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))/'tahoe-phone-link'
        if runtime.is_symlink():raise ValueError('Unexpected runtime directory')
        runtime.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(runtime,0o700)
        directory=Path(tempfile.mkdtemp(prefix='contacts-',dir=runtime));os.chmod(directory,0o700)
        descriptor,filename=tempfile.mkstemp(prefix='phonebook-',suffix='.vcf',dir=directory)
        os.close(descriptor);target=Path(filename)
        filters={'Format':GLib.Variant('s','vcard30'),'Fields':GLib.Variant('as',['VERSION','FN','N','TEL','UID'])}
        transfer,_=call(session,PBAP,'PullAll',GLib.Variant('(sa{sv})',(str(target),filters)),limit=25000)
        deadline=time.monotonic()+timeout
        # obexd removes completed transfer objects immediately. Observe the
        # completion signal, rather than racing GetAll on a vanished object.
        while time.monotonic()<deadline:
            while context.pending():context.iteration(False)
            state=states.get(transfer)
            if target.exists() and target.stat().st_size>MAX_BYTES:raise ValueError('Phonebook size limit exceeded')
            if state=='complete':
                os.chmod(target,0o600)
                contacts=parse_vcards(target.read_bytes())
                return {'status':'ok','source':'bluetooth_pbap','contacts':contacts,'count':len(contacts)}
            if state=='error':return {'status':'transfer_failed','contacts':[],'count':0}
            time.sleep(.05)
        raise TimeoutError('Phonebook transfer timed out')
    except GLib.Error as error:
        name=Gio.DBusError.get_remote_error(error) or ''
        return {'status':'need_permissions' if any(x in name for x in ('NotAuthorized','Forbidden','NotPermitted')) else 'bluetooth_unavailable','contacts':[],'count':0,'error_code':name}
    finally:
        bus.signal_unsubscribe(subscription)
        context.pop_thread_default()
        if session:
            try:call(ROOT,CLIENT,'RemoveSession',GLib.Variant('(o)',(session,)))
            except GLib.Error:pass
        if target:target.unlink(missing_ok=True)
        if directory:
            try:directory.rmdir()
            except OSError:pass
