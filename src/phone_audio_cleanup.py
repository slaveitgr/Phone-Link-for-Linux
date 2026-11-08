"""Restore only the exact microphone temporarily unmuted by this app."""
import json,os,stat,subprocess
from pathlib import Path
STATE=Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))/'tahoe-phone-link/call-audio.json'

def cleanup():
    try:
        info=STATE.lstat()
        if info.st_uid!=os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_mode&0o077:return
        value=json.loads(STATE.read_text())
        if value.get('restore_muted') is True:
            graph=json.loads(subprocess.run(['pw-dump'],check=True,capture_output=True,text=True,timeout=5).stdout)
            for obj in graph:
                props=obj.get('info',{}).get('props',{})
                if props.get('node.name')==value.get('name') and props.get('object.serial')==value.get('serial'):
                    subprocess.run(['wpctl','set-mute',str(obj['id']),'1'],check=True,capture_output=True,timeout=5)
                    break
        STATE.unlink(missing_ok=True)
    except (OSError,ValueError,subprocess.SubprocessError):pass

if __name__=='__main__':cleanup()
