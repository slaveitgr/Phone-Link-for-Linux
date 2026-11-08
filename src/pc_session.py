"""Observe actual GNOME lock state; never unlock or change the desktop session."""
import sys
sys.path.append('/usr/lib/python3/dist-packages')
from gi.repository import Gio,GLib

def is_locked():
    """None on unavailable session bus, not an invented unlocked status."""
    try:
        bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        result=bus.call_sync('org.gnome.ScreenSaver','/org/gnome/ScreenSaver',
            'org.gnome.ScreenSaver','GetActive',None,GLib.VariantType.new('(b)'),
            Gio.DBusCallFlags.NONE,2000,None)
        return bool(result.unpack()[0])
    except GLib.Error:return None
