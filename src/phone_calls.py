"""Bluetooth HFP telephony through PipeWire's native session D-Bus API.

No discovery, pairing, call, microphone or audio mutation happens on import.
The UI must bind a user-confirmed Bluetooth address before enabling actions.
Reference: PipeWire spa/plugins/bluez5/README-Telephony.md and telephony.c.
"""
import re
import sys
sys.path.append('/usr/lib/python3/dist-packages')
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

SERVICE='org.pipewire.Telephony'
ROOT='/org/pipewire/Telephony'
AG='org.pipewire.Telephony.AudioGateway1'
CALL='org.pipewire.Telephony.Call1'
TRANSPORT='org.pipewire.Telephony.AudioGatewayTransport1'
OBJECTS='org.freedesktop.DBus.ObjectManager'
PROPERTIES='org.freedesktop.DBus.Properties'

class PhoneUnavailable(RuntimeError):
    pass

def _unpack(value):
    if isinstance(value, GLib.Variant):
        return _unpack(value.unpack())
    if isinstance(value, dict):
        return {k:_unpack(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):
        return [_unpack(v) for v in value]
    return value

class PhoneCalls:
    def __init__(self, address):
        if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',address):
            raise ValueError('A confirmed Bluetooth address is required')
        self.address=address.upper()
        self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)

    def _call(self,path,interface,method,args=None):
        result=self.bus.call_sync(SERVICE,path,interface,method,args,None,
            Gio.DBusCallFlags.NONE,5000,None)
        return _unpack(result)[0] if result.n_children() else None

    def _gateway(self):
        objects=self._call(ROOT,OBJECTS,'GetManagedObjects')
        for path,interfaces in objects.items():
            if AG not in interfaces:continue
            props=interfaces[AG]
            address=props.get('Address')
            if address is None:
                address=self._call(path,PROPERTIES,'Get',GLib.Variant('(ss)',(AG,'Address')))
            if str(address).upper()==self.address:return path
        raise PhoneUnavailable('The selected phone has no connected HFP audio gateway')

    def get_calls(self):
        gateway=self._gateway()
        records=self._call(gateway,'org.ofono.VoiceCallManager','GetCalls')
        return [{'path':path,**props} for path,props in (records.items() if isinstance(records,dict) else records)]

    def status(self):
        try:
            gateway=self._gateway()
            calls=self.get_calls()
            return {'available':True,'gateway':gateway,'calls':calls}
        except PhoneUnavailable:
            return {'available':False,'reason':'phone_not_connected','calls':[]}
        except GLib.Error:
            return {'available':False,'reason':'telephony_unavailable','calls':[]}

    def dial(self,number):
        # The caller must invoke this only after the user presses Call.
        if not isinstance(number,str) or not re.fullmatch(r'[0-9+*#,ABCD]{1,80}',number):
            raise ValueError('Invalid telephone number')
        self._call(self._gateway(),AG,'Dial',GLib.Variant('(s)',(number,)))

    def _owned_call(self,path):
        gateway=self._gateway()
        if not path.startswith(gateway+'/') or path not in {c['path'] for c in self.get_calls()}:
            raise PhoneUnavailable('Call is not owned by the selected phone')
        return path

    def answer(self,path):
        self._call(self._owned_call(path),CALL,'Answer')

    def hangup(self,path):
        self._call(self._owned_call(path),CALL,'Hangup')

    def activate_audio(self):
        """Request SCO only for a live call. This does not route/unmute the mic."""
        gateway=self._gateway()
        if not any(c.get('State') in ('active','dialing','alerting') for c in self.get_calls()):
            raise PhoneUnavailable('No call requires audio')
        self._call(gateway,TRANSPORT,'Activate')

class CallAudio:
    """Two scoped PipeWire loopbacks, owned only for the selected phone call.

    Call start(user_initiated=True) from a worker after a Call/Answer/audio click.
    The monitor tears down both loopbacks and restores an originally muted mic
    when the call disappears. It never changes the system default devices.
    """
    def __init__(self, calls):
        import threading
        self.calls=calls
        self.processes=[]
        self.mic=None
        self.original_mute=None
        self._stop=threading.Event()
        self._lock=threading.RLock()
        self.state='idle'

    @staticmethod
    def _run(args):
        import subprocess
        return subprocess.run(args,check=True,capture_output=True,text=True,timeout=5).stdout

    @classmethod
    def _graph(cls):
        import json
        return json.loads(cls._run(['pw-dump']))

    def _nodes(self, graph):
        devices={o['id'] for o in graph if o.get('type')=='PipeWire:Interface:Device'
            and o.get('info',{}).get('props',{}).get('api.bluez5.address','').upper()==self.calls.address}
        phone={}
        local={}
        for obj in graph:
            if obj.get('type')!='PipeWire:Interface:Node':continue
            p=obj.get('info',{}).get('props',{})
            media=p.get('media.class')
            if media not in ('Audio/Source','Audio/Sink'):continue
            if p.get('device.id') in devices or p.get('api.bluez5.address','').upper()==self.calls.address:
                phone[media]=p
            # Prefer actual built-in analog devices; never route into a monitor,
            # HDMI output, camera microphone, or unrelated Bluetooth device.
            elif p.get('node.name','').startswith('alsa_') and '.analog-' in p.get('node.name',''):
                local[media]=p
        if set(phone)!={'Audio/Source','Audio/Sink'}:
            raise PhoneUnavailable('Phone SCO audio nodes are not available yet')
        if set(local)!={'Audio/Source','Audio/Sink'}:
            raise PhoneUnavailable('Built-in laptop microphone/speakers are unavailable')
        return phone,local

    def inspect(self):
        """Read-only readiness; false is normal before a call opens SCO."""
        try:
            phone,local=self._nodes(self._graph())
            return {'ready':True,'state':self.state,
                'phone_source':phone['Audio/Source']['node.name'],
                'phone_sink':phone['Audio/Sink']['node.name'],
                'laptop_source':local['Audio/Source']['node.name'],
                'laptop_sink':local['Audio/Sink']['node.name']}
        except PhoneUnavailable:
            return {'ready':False,'state':self.state,'reason':'waiting_for_call_audio'}

    def start(self, *, user_initiated=False):
        import subprocess,time,threading
        if not user_initiated:
            raise PermissionError('Call audio requires a user action')
        with self._lock:
            if self.processes:return
            if not any(c.get('State') in ('active','dialing','alerting') for c in self.calls.get_calls()):
                raise PhoneUnavailable('No active or outgoing call')
            self.calls.activate_audio()
            self.state='connecting'
            deadline=time.monotonic()+8
            while True:
                try:
                    phone,local=self._nodes(self._graph());break
                except PhoneUnavailable:
                    if time.monotonic()>=deadline:
                        self.state='unavailable';raise
                    time.sleep(.25)
            mic=local['Audio/Source']
            self.mic={'name':mic['node.name'],'serial':mic['object.serial']}
            volume=self._run(['wpctl','get-volume',str(mic['object.id'])])
            self.original_mute='[MUTED]' in volume
            self._stop=threading.Event()
            try:
                paths=[(phone['Audio/Source']['node.name'],local['Audio/Sink']['node.name'],'receive'),
                       (local['Audio/Source']['node.name'],phone['Audio/Sink']['node.name'],'microphone')]
                for source,sink,role in paths:
                    proc=subprocess.Popen(['pw-loopback','--name','tahoe-phone-call-'+role,
                        '--channels','1','--channel-map','[ MONO ]','--capture',source,'--playback',sink,
                        '--capture-props','media.role=Communication node.dont-reconnect=true',
                        '--playback-props','media.role=Communication node.dont-reconnect=true'],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    self.processes.append(proc)
                time.sleep(.2)
                if any(p.poll() is not None for p in self.processes):
                    raise PhoneUnavailable('Call audio bridge could not start')
                # Only unmute this exact built-in microphone, retaining volume.
                if self.original_mute:
                    import json,os
                    from phone_audio_cleanup import STATE
                    STATE.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                    fd=os.open(STATE,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'w') as stream:json.dump({'name':self.mic['name'],'serial':self.mic['serial'],'restore_muted':True},stream)
                    self._run(['wpctl','set-mute',str(mic['object.id']),'0'])
                self.state='active'
                threading.Thread(target=self._monitor,args=(self._stop,),daemon=True).start()
            except Exception:
                self.stop();raise

    def _monitor(self, stop_event):
        while not stop_event.wait(.5):
            try:
                calls=self.calls.get_calls()
                alive=any(c.get('State') in ('active','dialing','alerting','held','waiting') for c in calls)
                if not alive or any(p.poll() is not None for p in self.processes):break
            except Exception:break
        with self._lock:
            if self._stop is stop_event:self.stop()

    def stop(self):
        with self._lock:
            self._stop.set()
            for process in self.processes:
                if process.poll() is None:process.terminate()
            for process in self.processes:
                try:process.wait(timeout=2)
                except Exception:process.kill()
            self.processes=[]
            if self.original_mute and self.mic:
                try:
                    for obj in self._graph():
                        p=obj.get('info',{}).get('props',{})
                        if p.get('node.name')==self.mic['name'] and p.get('object.serial')==self.mic['serial']:
                            self._run(['wpctl','set-mute',str(obj['id']),'1']);break
                except Exception:pass
            from phone_audio_cleanup import cleanup
            cleanup()
            self.mic=None
            self.original_mute=None
            self.state='idle'
