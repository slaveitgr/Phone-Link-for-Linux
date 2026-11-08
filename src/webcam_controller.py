"""Explicit-user-action Android camera to a real Linux V4L2 virtual webcam.

The installed scrcpy help corroborates --video-source=camera, --camera-facing,
--max-size and --v4l2-sink. Import/status never activates the camera or changes
kernel modules. The caller must present the start/stop controls to the user.
"""
import fcntl,os,re,shutil,signal,subprocess,threading,time,ipaddress
from pathlib import Path

VIDIOC_QUERYCAP=0x80685600


def find_scrcpy():
    system=shutil.which('scrcpy')
    if system:return Path(system)
    for root in (Path(__file__).resolve().parent/'tools',Path.home()/'.local/share/tahoe-phone-link/tools'):
        for executable in sorted(root.glob('scrcpy-linux-*/scrcpy'),reverse=True):
            if executable.is_file() and os.access(executable,os.X_OK):return executable
    return None


def loopback_devices():
    """Read driver identity with QUERYCAP; never mistake the built-in webcam."""
    devices=[]
    for node in sorted(Path('/dev').glob('video*')):
        if not re.fullmatch(r'video\d+',node.name):continue
        try:
            fd=os.open(node,os.O_RDONLY|os.O_NONBLOCK)
            try:
                cap=bytearray(104);fcntl.ioctl(fd,VIDIOC_QUERYCAP,cap,True)
            finally:os.close(fd)
            driver=bytes(cap[:16]).split(b'\0',1)[0].decode('ascii','replace')
            if driver not in ('v4l2 loopback','v4l2loopback'):continue
            devices.append({'path':str(node),'label':bytes(cap[16:48]).split(b'\0',1)[0].decode('utf-8','replace'),
                'writable':os.access(node,os.W_OK)})
        except OSError:continue
    return devices


def _selected_android():
    """Only use exactly one already-authorized ADB device; never enable debugging."""
    adb=shutil.which('adb')
    if not adb:return None,'adb_missing'
    result=subprocess.run([adb,'devices'],capture_output=True,text=True,timeout=5,check=True)
    devices=[]
    for line in result.stdout.splitlines()[1:]:
        fields=line.split()
        if len(fields)>=2 and fields[1]=='device':devices.append(fields[0])
    wireless=[d for d in devices if ':' in d or '._adb-tls-connect._tcp' in d]
    if not wireless:return None,'wifi_debugging_not_connected'
    devices=wireless
    if len(devices)!=1:return None,'select_one_wireless_android_device'
    sdk=subprocess.run([adb,'-s',devices[0],'shell','getprop','ro.build.version.sdk'],capture_output=True,text=True,timeout=5,check=True).stdout.strip()
    if not sdk.isdigit() or int(sdk)<31:return None,'android_12_required'
    return devices[0],None


class WebcamController:
    def __init__(self):
        self.process=None;self._lock=threading.RLock();self._cached=None;self._checked=0;self.device=None
    def status(self,*,fresh=False):
        with self._lock:
            running=self.process is not None and self.process.poll() is None
            if running:return {'state':'running','available':True,'device':self.device,'label':'Phone Link Android Camera','transport':'wifi_adb'}
            if self.process is not None and self.process.returncode is not None:
                return {'state':'error','available':False,'reason':'camera_stream_ended','exit_code':self.process.returncode,'transport':'wifi_adb'}
            now=time.monotonic()
            if not fresh and self._cached and now-self._checked<5:return dict(self._cached)
            binary=find_scrcpy();nodes=loopback_devices();writable=[d for d in nodes if d['writable']]
            reason=None;serial=None
            if binary is None:reason='scrcpy_missing'
            elif not writable:reason='loopback_not_writable' if nodes else 'v4l2loopback_not_loaded'
            else:
                try:serial,reason=_selected_android()
                except (OSError,subprocess.SubprocessError):reason='android_unavailable'
            result={'state':'ready' if reason is None else 'unavailable','available':reason is None,
                'reason':reason,'devices':nodes,'transport':'wifi_adb','camera_not_activated':True}
            self._cached=result;self._checked=now
            return dict(result)
    def connect_wireless(self,endpoint,*,user_initiated=False):
        """Connect a phone already enabled/paired for Wireless Debugging.

        This never enables tcpip, pairs a new key, or changes phone settings.
        The endpoint must be a private LAN IP:port entered/approved by the user.
        """
        if not user_initiated:raise PermissionError('The user must request the Wi-Fi connection')
        if not isinstance(endpoint,str) or not re.fullmatch(r'[0-9.]+:[0-9]{1,5}',endpoint):raise ValueError('Expected private IPv4:port')
        host,port=endpoint.rsplit(':',1);address=ipaddress.ip_address(host)
        if not address.is_private or address.is_loopback or address.is_unspecified or not 1<=int(port)<=65535:raise ValueError('Expected private LAN phone endpoint')
        adb=shutil.which('adb')
        if not adb:return {'state':'unavailable','available':False,'reason':'adb_missing'}
        subprocess.run([adb,'connect',endpoint],capture_output=True,text=True,timeout=10,check=True)
        self._cached=None
        return self.status(fresh=True)
    def start(self,*,user_initiated=False,facing='front',device=None):
        if not user_initiated:raise PermissionError('The user must explicitly start the camera')
        if facing not in ('front','back'):raise ValueError('Unsupported camera facing')
        with self._lock:
            if self.process is not None and self.process.poll() is None:return self.status()
            self.process=None
            info=self.status(fresh=True)
            if not info['available']:return info
            nodes={d['path']:d for d in info['devices'] if d['writable']}
            chosen=device or next(iter(nodes))
            if chosen not in nodes:raise ValueError('Not an available V4L2 loopback device')
            serial,reason=_selected_android()
            if reason:return {'state':'unavailable','available':False,'reason':reason}
            binary=find_scrcpy()
            command=[str(binary),'--serial',serial,'--video-source=camera','--camera-facing='+facing,
                '--max-size=1280','--v4l2-sink='+chosen,'--no-audio','--no-window','--no-control']
            env=dict(os.environ)
            # Official portable builds contain their matched server next to the executable.
            server=binary.parent/'scrcpy-server'
            if server.is_file():env['SCRCPY_SERVER_PATH']=str(server)
            self.process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                env=env,start_new_session=True)
            self.device=chosen
            return {'state':'starting','available':True,'device':chosen,'label':nodes[chosen]['label']}
    def stop(self):
        with self._lock:
            process=self.process;self.process=None;self.device=None;self._cached=None
            if process and process.poll() is None:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:return {'state':'stopped','available':False}
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=2)
            return {'state':'stopped','available':False}
