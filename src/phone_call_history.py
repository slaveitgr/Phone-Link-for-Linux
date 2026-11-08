"""Real POCO call history and favorites over BlueZ PBAP; RAM-only results.

BlueZ PhonebookAccess1 docs define int/cch and int/fav. This module never
mutates the phone, dials, logs personal values, or accesses it on import.
"""
import hashlib,os,re,sys,tempfile,time
from pathlib import Path
from datetime import datetime
sys.path.append('/usr/lib/python3/dist-packages')
from gi.repository import Gio,GLib
from phone_config import bluetooth_address
from phone_contacts_bluetooth import parse_vcards,MAX_BYTES,SERVICE,ROOT,CLIENT,PBAP,PROPS


def parse_call_history(raw):
    if not isinstance(raw,bytes) or len(raw)>MAX_BYTES:raise ValueError('Invalid call history size')
    records=[]
    for card in re.findall(rb'BEGIN:VCARD.*?END:VCARD',raw,re.S|re.I):
        people=parse_vcards(card)
        if not people:continue
        person=people[0]
        match=re.search(rb'(?im)^X-IRMC-CALL-DATETIME(?:;([^:\r\n]*))?:(.*?)\r?$',card)
        timestamp=None;kind='unknown'
        if match:
            params=(match.group(1) or b'').decode('ascii','ignore').upper()
            for token,label in [('MISSED','missed'),('RECEIVED','incoming'),('DIALED','outgoing')]:
                if token in params:kind=label;break
            value=match.group(2).decode('ascii','ignore').strip()
            try:
                parsed=datetime.strptime(value,'%Y%m%dT%H%M%S'+('Z' if value.endswith('Z') else ''))
                if value.endswith('Z'):
                    from datetime import timezone
                    parsed=parsed.replace(tzinfo=timezone.utc)
                else:parsed=parsed.astimezone()
                timestamp=parsed.isoformat()
            except ValueError:pass
        records.append({'id':'pbap-call:'+hashlib.sha256(card).hexdigest(),
            'name':person['name'],'number':person['numbers'][0]['number'],
            'type':kind,'timestamp':timestamp,'duration':None})
    return sorted(records,key=lambda c:c['timestamp'] or '',reverse=True)


def _pull_book(folder,address=None,*,timeout=60,max_count=500):
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
        call(session,PBAP,'Select',GLib.Variant('(ss)',('int',folder)))
        runtime=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))/'tahoe-phone-link'
        if runtime.is_symlink():raise ValueError('Unexpected runtime directory')
        runtime.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(runtime,0o700)
        directory=Path(tempfile.mkdtemp(prefix='call-book-',dir=runtime));os.chmod(directory,0o700)
        descriptor,filename=tempfile.mkstemp(prefix='phonebook-',suffix='.vcf',dir=directory)
        os.close(descriptor);target=Path(filename)
        filters={'Format':GLib.Variant('s','vcard30'),'Fields':GLib.Variant('as',['VERSION','FN','N','TEL','UID','X-IRMC-CALL-DATETIME'])}
        if folder=='cch':filters['MaxCount']=GLib.Variant('q',max_count)
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
                raw=target.read_bytes()
                records=parse_call_history(raw) if folder=='cch' else parse_vcards(raw)
                return {'status':'ok','source':'bluetooth_pbap','records':records,'count':len(records)}
            if state=='error':return {'status':'transfer_failed','records':[],'count':0}
            time.sleep(.05)
        raise TimeoutError('Phonebook transfer timed out')
    except GLib.Error as error:
        name=Gio.DBusError.get_remote_error(error) or ''
        return {'status':'need_permissions' if any(x in name for x in ('NotAuthorized','Forbidden','NotPermitted')) else 'bluetooth_unavailable','records':[],'count':0,'error_code':name}
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


def pull_call_history(address=None,*,timeout=60,max_count=500):
    """Read up to newest500 (PBAP phone order) actual entries, no duration invented."""
    if type(max_count) is not int or not 1<=max_count<=2000:raise ValueError('Invalid history limit')
    result=_pull_book('cch',address,timeout=timeout,max_count=max_count)
    return {**result,'calls':result['records']}


def pull_favorites(address=None,*,timeout=60):
    """Read actual phone favorites; IDs/numbers can be matched to full contacts."""
    result=_pull_book('fav',address,timeout=timeout)
    return {**result,'favorites':result['records']}
