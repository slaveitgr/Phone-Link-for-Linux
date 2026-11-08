"""Paired-peer PC locking; no power/session changes on import.

APK getResourcePath: /remotecontrol (ev_fc7670d906b6451f1f922ab03ed008c3b0d6eeb7afbfb96aa6d2182d1188a971).
Modern enum LOCK=1; Windows legacy remoteControlType LockScreen=0.
Caller must reply using its existing correlated DRM response mechanism.
"""
import sys
from pathlib import Path
sys.path.append('/usr/lib/python3/dist-packages')
sys.path.insert(0,str(Path(__file__).resolve().parent/'generated'))
from gi.repository import Gio,GLib
from remote_control.v1.control_message_pb2 import RemoteControlRequestMessage,RemoteControlResponseMessage
from google.protobuf.message import DecodeError
from value_set_codec import value_set

EVIDENCE_IDS={
    'modern_route':'ev_fc7670d906b6451f1f922ab03ed008c3b0d6eeb7afbfb96aa6d2182d1188a971',
    'modern_lock':'ev_9b51fb2f06656a53868a20eb2a55dbbd2000f4b6d6c59b148f293e58734f1ca7',
    'legacy_handler':'ev_e9ea201e56744e0feb183da6419db162c7bb5915e55ba6f1e7850367c97ed790',
}
RESOURCE_PATH='/remotecontrol'
SUCCESS,FAILED,DISABLED=1,2,3

def safe_shell_available():
    """Never lock the loaded pre-fix Shell extension with disposed actor bugs."""
    try:
        bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        result=bus.call_sync('org.gnome.Shell','/org/gnome/Shell/Extensions/TahoeApplications',
            'org.gnome.Shell.Extensions.TahoeApplications','GetVersion',None,
            GLib.VariantType.new('(s)'),Gio.DBusCallFlags.NONE,2000,None)
        return result.unpack()[0]=='2-phone-link'
    except GLib.Error:return False

def _lock():
    bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    bus.call_sync('org.gnome.ScreenSaver','/org/gnome/ScreenSaver',
        'org.gnome.ScreenSaver','Lock',None,None,Gio.DBusCallFlags.NONE,5000,None)

def handle_control(control_type,*,sender,paired_partner,legacy=False,
                   safety_check=safe_shell_available,lock_action=_lock):
    """Return protocol result. Only paired sender + explicit lock can mutate."""
    if not paired_partner or not isinstance(sender,str) or sender!=paired_partner:
        return DISABLED
    expected=0 if legacy else 1
    if type(control_type) is not int or control_type!=expected:return DISABLED
    if not safety_check():return DISABLED
    try:lock_action()
    except (GLib.Error,OSError):return FAILED
    return SUCCESS

def handle_modern(payload,*,sender,paired_partner,**kwargs):
    if not isinstance(payload,bytes) or len(payload)>4096:
        return RemoteControlResponseMessage(control_result=FAILED).SerializeToString()
    request=RemoteControlRequestMessage()
    try:request.ParseFromString(payload)
    except DecodeError:return RemoteControlResponseMessage(control_result=FAILED).SerializeToString()
    result=handle_control(request.control_type,sender=sender,paired_partner=paired_partner,**kwargs)
    return RemoteControlResponseMessage(control_result=result).SerializeToString()

def handle_legacy(values,*,sender,paired_partner,**kwargs):
    """Legacy result field is boolean error: Windows emits !success."""
    entry=values.entries.get('remoteControlType')
    control=entry.int32_value if entry is not None and entry.value_type==4 else None
    result=handle_control(control,sender=sender,paired_partner=paired_partner,legacy=True,**kwargs)
    return value_set({'result':result!=SUCCESS})
