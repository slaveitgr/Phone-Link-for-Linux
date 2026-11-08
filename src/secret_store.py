"""This app's Secret Service item, using the standard local-bus plain session.

Only transfer on the user's session bus is plain. The login collection remains
password protected and encrypted by the OS. This avoids the observed GNOME
Keyring crash in encrypted-session negotiation; no global settings are changed.
Protocol: https://specifications.freedesktop.org/secret-service/latest-single/
"""
import sys,time
sys.path.append('/usr/lib/python3/dist-packages')
from gi.repository import Gio,GLib
SERVICE='org.freedesktop.secrets'
ROOT='/org/freedesktop/secrets'
IFACE='org.freedesktop.Secret.'
ATTRIBUTES={'xdg:schema':'local.tahoe.PhoneLink','account':'primary'}

class KeyringLocked(RuntimeError):pass

class SecretStore:
    def __init__(self):
        self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        self.session=None

    def call(self,path,interface,method,signature,args,result):
        return self.bus.call_sync(SERVICE,path,interface,method,
            GLib.Variant(signature,args),GLib.VariantType.new(result),
            Gio.DBusCallFlags.NONE,20000,None).unpack()

    def prompt(self,path):
        if path=='/':return
        context=GLib.MainContext.new()
        context.push_thread_default()
        done=[]
        def complete(connection,sender,path,interface,signal,parameters,user_data):
            done.append(parameters.unpack())
        subscription=self.bus.signal_subscribe(SERVICE,IFACE+'Prompt','Completed',path,
                          None,Gio.DBusSignalFlags.NONE,complete,None)
        try:
            self.call(path,IFACE+'Prompt','Prompt','(s)',('',),'()')
            until=time.monotonic()+120
            while not done and time.monotonic()<until:
                while context.pending():context.iteration(False)
                time.sleep(.05)
            if not done or done[0][0]:raise KeyringLocked('Login keyring was not unlocked')
        finally:
            self.bus.signal_unsubscribe(subscription)
            context.pop_thread_default()

    def unlock(self,paths):
        if not paths:return
        _,prompt=self.call(ROOT,IFACE+'Service','Unlock','(ao)',(paths,),'(aoo)')
        self.prompt(prompt)

    def collection(self):
        (path,)=self.call(ROOT,IFACE+'Service','ReadAlias','(s)',('default',),'(o)')
        if path=='/':raise KeyringLocked('No default login keyring exists')
        (locked,)=self.call(path,'org.freedesktop.DBus.Properties','Get',
                      '(ss)',(IFACE+'Collection','Locked'),'(v)')
        if locked:self.unlock([path])
        return path

    def open_session(self):
        if self.session is None:
            _,self.session=self.call(ROOT,IFACE+'Service','OpenSession','(sv)',
                         ('plain',GLib.Variant('s','')),'(vo)')
        return self.session

    def load(self):
        # A locked keyring is not equivalent to a missing account.
        self.collection()
        unlocked,locked=self.call(ROOT,IFACE+'Service','SearchItems','(a{ss})',
                               (ATTRIBUTES,),'(aoao)')
        if locked:
            self.unlock(locked)
            unlocked+=locked
        if not unlocked:return None
        (secret,)=self.call(unlocked[0],IFACE+'Item','GetSecret','(o)',
                            (self.open_session(),),'((oayays))')
        return bytes(secret[2]).decode('utf-8')

    def save(self,value):
        collection=self.collection()
        properties={IFACE+'Item.Label':GLib.Variant('s','Ubuntu Phone Link connection'),
                    IFACE+'Item.Attributes':GLib.Variant('a{ss}',ATTRIBUTES)}
        secret=(self.open_session(),b'',value.encode('utf-8'),'application/json; charset=utf-8')
        _,prompt=self.call(collection,IFACE+'Collection','CreateItem',
            '(a{sv}(oayays)b)',(properties,secret,True),'(oo)')
        self.prompt(prompt)
        if self.load()!=value:raise RuntimeError('Secure keyring write/read verification failed')
        return True

    def close(self):
        if self.session:
            try:self.call(self.session,IFACE+'Session','Close','()',(),'()')
            except GLib.Error:pass
            self.session=None

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
