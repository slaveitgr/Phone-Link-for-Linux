"""RAM-only phone notifications exposed through an owner-only local socket.

No Microsoft tokens, private keys or account data are exposed by this bridge.
"""
import json,os,socket,socketserver,stat,struct,threading,queue,uuid
from pathlib import Path
from datetime import datetime,timezone

RUNTIME=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))/'tahoe-phone-link'
SOCKET=RUNTIME/'view.sock'
_lock=threading.RLock()
_notifications={}
_sync=False
_commands=queue.Queue(maxsize=20)
_results={}
_clipboard=None
_contacts=[]
_contacts_status="search_required"

def update_notifications(records,*,replace=False,removed=()):
    global _sync
    with _lock:
        if replace:_notifications.clear()
        for identifier in removed:_notifications.pop(str(identifier),None)
        for record in records:
            identifier=record.get('id')
            if not identifier:continue
            _notifications[str(identifier)[:300]]={
                'id':str(identifier)[:300], 'app':str(record.get('app',''))[:200],
                'title':str(record.get('title',''))[:500],
                'body':str(record.get('body',''))[:4000]}
        while len(_notifications)>100:_notifications.pop(next(iter(_notifications)))
        _sync=True

def snapshot():
    with _lock:
        return {'schema_version':1,'notifications_synced':_sync,
            'notifications':list(_notifications.values()),'contacts':list(_contacts),'contacts_status':_contacts_status,'clipboard':_clipboard,'command_results':dict(_results),
            'updated_at':datetime.now(timezone.utc).isoformat()}

class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        _,uid,_=struct.unpack('3i',self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if uid!=os.getuid():return
        self.request.settimeout(2)
        command=self.rfile.readline(512*1024)
        if command==b'view\n':
            reply=snapshot()
        else:
            try:request=json.loads(command)
            except ValueError:return
            action=request.get('action')
            if action=='copy_text':
                if not isinstance(request.get('text'),str) or len(request['text'].encode())>65536:return
                payload={'text':request['text']}
            elif action=='search_contacts':
                query=request.get('query')
                if not isinstance(query,str) or not query.strip() or len(query)>500:return
                payload={'kind':'search_contacts','query':query.strip()}
            else:return
            identifier=str(uuid.uuid4())
            try:_commands.put_nowait({'id':identifier,**payload})
            except queue.Full:return
            reply={'queued':True,'id':identifier}
        try:self.wfile.write(json.dumps(reply,ensure_ascii=False).encode()+b'\n')
        except (BrokenPipeError,ConnectionResetError):pass

class _Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads=True

def start_bridge():
    RUNTIME.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(RUNTIME,0o700)
    if SOCKET.exists():
        info=SOCKET.lstat()
        if info.st_uid!=os.getuid() or not stat.S_ISSOCK(info.st_mode):raise RuntimeError('Unexpected bridge file')
        SOCKET.unlink()
    server=_Server(str(SOCKET),_Handler)
    os.chmod(SOCKET,0o600)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server

def read_snapshot():
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(1)
        client.connect(str(SOCKET));client.sendall(b'view\n')
        with client.makefile('rb') as stream:
            raw=stream.readline(512*1024)
    return json.loads(raw)


def take_command():
    try:return _commands.get_nowait()
    except queue.Empty:return None

def command_result(identifier,result):
    with _lock:
        _results[identifier]=result
        while len(_results)>20:_results.pop(next(iter(_results)))

def update_clipboard(text):
    global _clipboard
    if not isinstance(text,str) or len(text.encode())>65536:return
    with _lock:_clipboard=text

def send_clipboard(text):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(2);client.connect(str(SOCKET))
        client.sendall(json.dumps({'action':'copy_text','text':text},ensure_ascii=False).encode()+b'\n')
        with client.makefile('rb') as stream:raw=stream.readline(4096)
    return json.loads(raw)


def update_contacts(records,status='ok'):
    global _contacts,_contacts_status
    with _lock:
        _contacts=list(records[:1000]);_contacts_status=status

def search_contacts(query):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(2);client.connect(str(SOCKET))
        client.sendall(json.dumps({'action':'search_contacts','query':query}).encode()+b'\n')
        with client.makefile('rb') as stream:return json.loads(stream.readline(4096))
