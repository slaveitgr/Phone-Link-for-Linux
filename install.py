#!/usr/bin/env python3
"""Install a per-user client; never asks for a root password."""
from pathlib import Path
import subprocess,shutil,sys,os
root=Path(__file__).resolve().parent
app=Path.home()/'.local/share/tahoe-phone-link'
app.mkdir(parents=True,exist_ok=True)
shutil.copytree(root/'src',app,dirs_exist_ok=True)
venv=app/'.venv'
subprocess.run([sys.executable,'-m','venv','--system-site-packages',str(venv)],check=True)
python=venv/'bin/python'
subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements.txt')],check=True)
bin=Path.home()/'.local/bin';bin.mkdir(parents=True,exist_ok=True)
wrapper=bin/'tahoe-phone-link'
wrapper.write_text('''#!/bin/sh
case "${1:-open}" in
  open|login) systemctl --user start tahoe-phone-link-ui.service
    exec gdbus call --session --dest local.tahoe.PhoneLink --object-path /local/tahoe/PhoneLink --method org.freedesktop.Application.Activate '{}' ;;
  calls|clipboard|notifications|messages|photos|settings) systemctl --user start tahoe-phone-link-ui.service
    exec gdbus call --session --dest local.tahoe.PhoneLink --object-path /local/tahoe/PhoneLink --method org.gtk.Actions.Activate "$1" '[]' '{}' ;;
  *) exit 2 ;;
esac
''');wrapper.chmod(0o755)
units=Path.home()/'.config/systemd/user';units.mkdir(parents=True,exist_ok=True)
for name,module in [('tahoe-phone-link','relay_service'),('tahoe-phone-link-ui','phone_app')]:
    dbus='Type=dbus\nBusName=local.tahoe.PhoneLink\n' if module=='phone_app' else ''
    cleanup=f'ExecStopPost="{python}" "{app}/phone_audio_cleanup.py"\n' if module=='phone_app' else ''
    (units/(name+'.service')).write_text(f'[Unit]\nDescription=Phone Link for Linux\nAfter=graphical-session.target\n\n[Service]\n{dbus}ExecStart="{python}" "{app}/{module}.py"\n{cleanup}Restart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n')
apps=Path.home()/'.local/share/applications';apps.mkdir(parents=True,exist_ok=True)
(apps/'tahoe-phone-link.desktop').write_text(f'[Desktop Entry]\nType=Application\nName=Phone Link for Linux\nExec={wrapper}\nIcon=smartphone\nCategories=Network;Utility;\nStartupWMClass=local.tahoe.PhoneLink\n')
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','tahoe-phone-link.service'],check=True)
print('Installed. Launch Phone Link for Linux from Applications.')
