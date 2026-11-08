"""Wi-Fi screen/app streaming using an explicitly authorized Android connection.

This is a Linux scrcpy receiver, not Microsoft's proprietary video transport.
No stream is started on import or status inspection. Phone screen stays on.
"""
import os,re,subprocess,threading,signal
from webcam_controller import find_scrcpy,_selected_android

class PhoneStreaming:
    def __init__(self):self.processes={};self.lock=threading.RLock()
    def status(self):
        try:serial,reason=_selected_android()
        except (OSError,subprocess.SubprocessError):serial=None;reason='wifi_phone_unavailable'
        with self.lock:
            active=[key for key,p in self.processes.items() if p.poll() is None]
        return {'available':bool(serial and find_scrcpy()),'reason':reason,'transport':'wifi','running':len(active),'active':active}
    def start(self,*,package=None,user_initiated=False):
        if not user_initiated:raise PermissionError('Explicit screen/app streaming request required')
        if package is not None and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+',package):raise ValueError('Invalid Android app package')
        with self.lock:
            key=package or 'screen'
            existing=self.processes.get(key)
            if existing and existing.poll() is None:return {'status':'running'}
            serial,reason=_selected_android();binary=find_scrcpy()
            if reason or not binary:return {'status':reason or 'scrcpy_missing'}
            command=[str(binary),'--serial',serial,'--no-audio','--max-size=1600','--max-fps=30','--window-title=Phone Link — '+(package or 'Phone screen')]
            if package:command+=['--new-display=1080x1920/420','--start-app='+package]
            env=dict(os.environ)
            server=binary.parent/'scrcpy-server'
            if server.is_file():env['SCRCPY_SERVER_PATH']=str(server)
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env,start_new_session=True)
            self.processes[key]=process
            try:code=process.wait(timeout=.8)
            except subprocess.TimeoutExpired:return {'status':'running','transport':'wifi'}
            return {'status':'stream_ended' if code==0 else 'stream_start_failed','exit_code':code,'transport':'wifi'}
    def stop(self,package=None):
        with self.lock:
            key=package or 'screen';process=self.processes.pop(key,None)
            if process and process.poll() is None:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:return {'status':'stopped'}
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait(timeout=3)
            return {'status':'stopped'}
    def stop_all(self):
        with self.lock:
            for key in list(self.processes):self.stop(None if key=='screen' else key)

    def list_apps(self):
        serial,reason=_selected_android();binary=find_scrcpy()
        if reason or not binary:return {'status':reason or 'scrcpy_missing','apps':[]}
        env=dict(os.environ);server=binary.parent/'scrcpy-server'
        if server.is_file():env['SCRCPY_SERVER_PATH']=str(server)
        result=subprocess.run([str(binary),'--serial',serial,'--list-apps'],capture_output=True,text=True,timeout=30,env=env,check=True)
        apps=[]
        for line in result.stdout.splitlines():
            match=re.match(r'\s*[-*]\s+(.+?)\s+([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)\s*$',line)
            if match:apps.append({'name':match[1].strip(),'package':match[2]})
        return {'status':'ok','apps':apps}
