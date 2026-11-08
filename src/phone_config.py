"""User configuration contains no default device identifiers."""
import json,os,re
from pathlib import Path

def bluetooth_address():
    address=os.environ.get('PHONE_LINK_BLUETOOTH_ADDRESS','')
    if not address:
        try:address=json.loads((Path.home()/'.config/tahoe-phone-link/config.json').read_text()).get('bluetooth_address','')
        except (OSError,ValueError):pass
    return address.upper() if isinstance(address,str) and re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',address) else None
