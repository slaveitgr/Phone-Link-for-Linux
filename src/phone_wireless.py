"""Explicit setup of authenticated Android Wi-Fi debugging for Linux services."""
import ipaddress,json,re,shutil,subprocess,time
from pathlib import Path

def configure_wifi(*,user_initiated=False):
    if not user_initiated:raise PermissionError('Explicit Wi-Fi setup is required')
    adb=shutil.which('adb')
    if not adb:return {'status':'adb_missing'}
    def run(args,timeout=10):
        return subprocess.run([adb,*args],capture_output=True,text=True,timeout=timeout,check=True).stdout
    devices=[line.split()[0] for line in run(['devices']).splitlines()[1:] if len(line.split())>1 and line.split()[1]=='device']
    wireless=[s for s in devices if ':' in s]
    if len(wireless)==1:return {'status':'connected','endpoint':wireless[0]}
    usb=[s for s in devices if ':' not in s]
    if len(usb)!=1:return {'status':'connect_one_authorized_phone_for_setup'}
    serial=usb[0]
    addresses=run(['-s',serial,'shell','ip','-4','-o','addr','show','wlan0'])
    match=re.search(r'\binet\s+(\d+\.\d+\.\d+\.\d+)/',addresses)
    if not match:return {'status':'phone_wifi_not_connected'}
    address=ipaddress.ip_address(match[1])
    if not address.is_private or address.is_loopback:return {'status':'private_wifi_required'}
    endpoint=str(address)+':5555'
    run(['-s',serial,'tcpip','5555'])
    for _ in range(8):
        try:
            run(['connect',endpoint],timeout=5)
            if run(['-s',endpoint,'get-state']).strip()=='device':
                path=Path.home()/'.config/tahoe-phone-link/config.json'
                path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                try:config=json.loads(path.read_text())
                except (OSError,ValueError):config={}
                config['wireless_adb_endpoint']=endpoint
                path.write_text(json.dumps(config));path.chmod(0o600)
                return {'status':'connected','endpoint':endpoint}
        except subprocess.SubprocessError:pass
        time.sleep(.5)
    return {'status':'wifi_connection_failed'}
