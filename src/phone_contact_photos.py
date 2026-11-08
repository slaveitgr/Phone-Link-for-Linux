"""Lazy, read-only PBAP contact photos. No phone data is stored persistently.

BlueZ API was introspected on the running obexd: Search(s,s,a{sv})->a(ss)
and Pull(s,s,a{sv})->(o,a{sv}). Temporary vCards are private and unlinked.
"""
import base64,binascii,hashlib,os,re,tempfile,threading,time
from collections import OrderedDict
from pathlib import Path
from phone_config import bluetooth_address
from phone_contacts_bluetooth import Gio,GLib,SERVICE,ROOT,CLIENT,PBAP,PROPS

MAX_PHOTO_BYTES=256*1024
MAX_VCARD_BYTES=4*MAX_PHOTO_BYTES
CACHE_LIMIT=128
_lock=threading.Lock()
_cache=OrderedDict()


def parse_photo(raw):
    """Decode an embedded JPEG/PNG/WebP PHOTO, never fetch a PHOTO URI."""
    if not isinstance(raw,bytes) or len(raw)>MAX_VCARD_BYTES:raise ValueError('Contact card size exceeds limit')
    lines=[]
    for line in raw.replace(b'\r\n',b'\n').replace(b'\r',b'\n').split(b'\n'):
        if line.startswith((b' ',b'\t')) and lines:lines[-1]+=line[1:]
        else:lines.append(line)
    for index,line in enumerate(lines):
        if b':' not in line:continue
        key,value=line.split(b':',1)
        if key.split(b';',1)[0].split(b'.')[-1].upper()!=b'PHOTO':continue
        if b'VALUE=URI' in key.upper() and not value.lower().startswith(b'data:image/'):return {'status':'no_photo'}
        if value.lower().startswith(b'data:image/'):
            if b';base64,' not in value:return {'status':'no_photo'}
            value=value.split(b';base64,',1)[1]
        else:
            # vCard2.1 sometimes uses unindented continuation lines.
            for extra in lines[index+1:]:
                if b':' in extra or extra.upper().startswith(b'END:'):break
                if extra.strip():value+=extra.strip()
        try:image=base64.b64decode(re.sub(rb'\s+',b'',value),validate=True)
        except (binascii.Error,ValueError):return {'status':'invalid_photo'}
        if not image:return {'status':'no_photo'}
        if len(image)>MAX_PHOTO_BYTES:return {'status':'photo_too_large'}
        if image.startswith(b'\xff\xd8\xff'):mime='image/jpeg'
        elif image.startswith(b'\x89PNG\r\n\x1a\n'):mime='image/png'
        elif image.startswith(b'RIFF') and image[8:12]==b'WEBP':mime='image/webp'
        else:return {'status':'unsupported_photo'}
        return {'status':'ok','mime':mime,'size':len(image),
                'data_url':'data:'+mime+';base64,'+base64.b64encode(image).decode('ascii')}
    return {'status':'no_photo'}


def pull_contact_photo(number,address=None,*,timeout=20):
    """Read one selected contact photo; bounded RAM cache, no logging.

    Returns status and, only for status=ok, mime,size,data_url. The caller uses
    its own existing contact ID to match the result to the UI.
    """
    address=address or bluetooth_address()
    if not isinstance(address,str) or not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',address):return {'status':'bluetooth_unavailable'}
    if not isinstance(number,str) or len(number)>100 or not re.fullmatch(r'[0-9+*#()\s.-]{1,100}',number):return {'status':'invalid_number'}
    if not 1<=timeout<=20:raise ValueError('Invalid photo timeout')
    normalized=re.sub(r'[\s().-]','',number)
    cache_key=hashlib.sha256((address.upper()+'\0'+normalized).encode()).digest()
    requested_at=time.monotonic()
    if not _lock.acquire(timeout=timeout):return {'status':'busy'}
    try:
        cached=_cache.get(cache_key)
        if cached and time.monotonic()-cached[0]<300:
            _cache.move_to_end(cache_key);return dict(cached[1])
        from phone_calls import PhoneCalls
        if PhoneCalls(address).status().get('calls'):return {'status':'busy'}
        remaining=timeout-(time.monotonic()-requested_at)
        if remaining<1:return {'status':'timeout'}
        result=_pull_photo(normalized,address,timeout=remaining)
        if result['status'] in ('ok','no_photo','photo_too_large','unsupported_photo'):
            _cache[cache_key]=(time.monotonic(),dict(result));_cache.move_to_end(cache_key)
            while len(_cache)>CACHE_LIMIT:_cache.popitem(last=False)
        return result
    finally:_lock.release()


def _pull_photo(number,address,*,timeout):
    started=time.monotonic()
    context=GLib.MainContext.new();context.push_thread_default()
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    states={};session=None;target=None;directory=None
    def changed(connection,sender,path,interface,signal,parameters):
        iface,values,_=parameters.unpack()
        if iface=='org.bluez.obex.Transfer1' and 'Status' in values:states[path]=values['Status']
    subscription=bus.signal_subscribe(SERVICE,PROPS,'PropertiesChanged',None,'org.bluez.obex.Transfer1',Gio.DBusSignalFlags.NONE,changed)
    def call(path,interface,method,args=None):
        remaining=max(1,timeout-(time.monotonic()-started))
        return bus.call_sync(SERVICE,path,interface,method,args,None,Gio.DBusCallFlags.NONE,int(remaining*1000),None).unpack()
    try:
        session=call(ROOT,CLIENT,'CreateSession',GLib.Variant('(sa{sv})',(address.upper(),{'Target':GLib.Variant('s','pbap')})))[0]
        call(session,PBAP,'Select',GLib.Variant('(ss)',('int','pb')))
        matches=call(session,PBAP,'Search',GLib.Variant('(ssa{sv})',('number',number,{'MaxCount':GLib.Variant('q',3)})))[0]
        if not matches:return {'status':'no_photo'}
        handle=matches[0][0]
        if not isinstance(handle,str) or len(handle)>200 or '/' in handle or '..' in handle:return {'status':'invalid_card'}
        runtime=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))/'tahoe-phone-link'
        if runtime.is_symlink():raise ValueError('Unexpected photo runtime directory')
        runtime.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(runtime,0o700)
        directory=Path(tempfile.mkdtemp(prefix='contact-photo-',dir=runtime));os.chmod(directory,0o700)
        fd,name=tempfile.mkstemp(prefix='photo-',suffix='.vcf',dir=directory);os.close(fd);target=Path(name)
        filters={'Format':GLib.Variant('s','vcard30'),'Fields':GLib.Variant('as',['VERSION','PHOTO'])}
        transfer,_=call(session,PBAP,'Pull',GLib.Variant('(ssa{sv})',(handle,str(target),filters)))
        while time.monotonic()-started<timeout:
            while context.pending():context.iteration(False)
            if target.exists() and target.stat().st_size>MAX_VCARD_BYTES:return {'status':'photo_too_large'}
            if states.get(transfer)=='complete':
                target.chmod(0o600);return parse_photo(target.read_bytes())
            if states.get(transfer)=='error':return {'status':'transfer_failed'}
            time.sleep(.025)
        return {'status':'timeout'}
    except GLib.Error as error:
        code=Gio.DBusError.get_remote_error(error) or ''
        return {'status':'need_permissions' if any(x in code for x in ('NotAuthorized','Forbidden','NotPermitted')) else 'bluetooth_unavailable'}
    finally:
        if session:
            try:call(ROOT,CLIENT,'RemoveSession',GLib.Variant('(o)',(session,)))
            except GLib.Error:pass
        bus.signal_unsubscribe(subscription);context.pop_thread_default()
        if target:target.unlink(missing_ok=True)
        if directory:
            try:directory.rmdir()
            except OSError:pass
