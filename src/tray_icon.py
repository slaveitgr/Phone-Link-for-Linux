"""StatusNotifierItem for the persistent Phone Link service (no GTK window needed)."""
import json, os, subprocess, threading, sys
sys.path.append('/usr/lib/python3/dist-packages')
from pathlib import Path
from datetime import datetime, timezone
from gi.repository import Gio, GLib

SNI='org.kde.StatusNotifierItem'
MENU='com.canonical.dbusmenu'
PATH='/StatusNotifierItem'
MENU_PATH='/MenuBar'
XML='''<node><interface name="org.kde.StatusNotifierItem">
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="WindowId" type="u" access="read"/><property name="IconName" type="s" access="read"/>
<property name="IconPixmap" type="a(iiay)" access="read"/><property name="OverlayIconName" type="s" access="read"/>
<property name="AttentionIconName" type="s" access="read"/><property name="AttentionMovieName" type="s" access="read"/>
<property name="ToolTip" type="(sa(iiay)ss)" access="read"/><property name="ItemIsMenu" type="b" access="read"/>
<property name="Menu" type="o" access="read"/>
<signal name="NewIcon"/><signal name="NewToolTip"/><signal name="NewTitle"/>
<signal name="NewStatus"><arg type="s"/></signal></interface>
<interface name="com.canonical.dbusmenu">
<property name="Version" type="u" access="read"/><property name="TextDirection" type="s" access="read"/>
<property name="Status" type="s" access="read"/><property name="IconThemePath" type="as" access="read"/>
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/><arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
<method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
<method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/></method>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
<signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
</interface></node>'''

class TrayIcon:
    def __init__(self):
        self.state='disconnected'; self.description='Phone Link'; self.revision=1
        self.ready=threading.Event(); self.error=None
        self.thread=threading.Thread(target=self._run,name='phone-link-tray',daemon=True)
        self.thread.start()

    def _run(self):
        try:
            context=GLib.MainContext.new(); context.push_thread_default()
            self.loop=GLib.MainLoop.new(context,False)
            self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            node=Gio.DBusNodeInfo.new_for_xml(XML)
            self.registrations=[self.bus.register_object(PATH,node.interfaces[0],self._method,self._property,None),
                self.bus.register_object(MENU_PATH,node.interfaces[1],self._method,self._property,None)]
            self.name='org.kde.StatusNotifierItem.PhoneLink'+str(os.getpid())
            self.owner=Gio.bus_own_name_on_connection(self.bus,self.name,Gio.BusNameOwnerFlags.NONE,
                lambda *_:self._register(),None)
            self.watch=Gio.bus_watch_name_on_connection(self.bus,'org.kde.StatusNotifierWatcher',
                Gio.BusNameWatcherFlags.NONE,lambda *_:self._register(),None)
            source=GLib.timeout_source_new_seconds(3); source.set_callback(self._refresh); source.attach(context)
            self._refresh(); self.ready.set(); self.loop.run()
        except Exception as error:
            self.error=type(error).__name__; self.ready.set()

    def _register(self):
        self.bus.call('org.kde.StatusNotifierWatcher','/StatusNotifierWatcher',
            'org.kde.StatusNotifierWatcher','RegisterStatusNotifierItem',GLib.Variant('(s)',(self.name,)),
            None,Gio.DBusCallFlags.NONE,3000,None,None,None)

    def _refresh(self,*_):
        try:
            path=Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'tahoe-phone-link/status.json'
            data=json.loads(path.read_text()); state=data.get('state','disconnected')
            if state=='connected' and (datetime.now(timezone.utc)-datetime.fromisoformat(data['updated_at'])).total_seconds()>90:
                state='disconnected'
            device=data.get('device',{}); battery=device.get('battery_percent')
            label={'connected':'Συνδεδεμένο','connecting':'Σύνδεση…','paired':'Συζευγμένο',
                'disconnected':'Εκτός σύνδεσης','signed_out':'Χρειάζεται σύνδεση','error':'Χρειάζεται έλεγχος'}.get(state,state)
            description=device.get('name','POCO F8 Ultra')+' · '+label
            if state=='connected' and isinstance(battery,int):description+=' · '+str(battery)+'%'
        except (OSError,ValueError,TypeError,KeyError):state='disconnected';description='Phone Link · Εκτός σύνδεσης'
        if (state,description)!=(self.state,self.description):
            self.state,self.description=state,description;self.revision+=1
            for signal in ('NewIcon','NewToolTip','NewTitle'):self.bus.emit_signal(None,PATH,SNI,signal,None)
            self.bus.emit_signal(None,MENU_PATH,MENU,'LayoutUpdated',GLib.Variant('(ui)',(self.revision,0)))
        return GLib.SOURCE_CONTINUE

    @property
    def icon(self):return 'phone-symbolic' if self.state=='connected' else 'phone-missed-call-symbolic'

    def _property(self,connection,sender,path,interface,name):
        if interface==SNI:
            values={'Category':('s','Communications'),'Id':('s','tahoe-phone-link'),'Title':('s',self.description),
                'Status':('s','Active'),'WindowId':('u',0),'IconName':('s',self.icon),'IconPixmap':('a(iiay)',[]),
                'OverlayIconName':('s',''),'AttentionIconName':('s','phone-symbolic'),'AttentionMovieName':('s',''),
                'ToolTip':('(sa(iiay)ss)',(self.icon,[],'Phone Link',self.description)),
                'ItemIsMenu':('b',False),'Menu':('o',MENU_PATH)}
        else:values={'Version':('u',3),'TextDirection':('s','ltr'),'Status':('s','normal'),'IconThemePath':('as',[])}
        signature,value=values[name];return GLib.Variant(signature,value)

    def _items(self):
        def props(label,enabled=True):return {'label':GLib.Variant('s',label),'enabled':GLib.Variant('b',enabled),'visible':GLib.Variant('b',True)}
        return {0:{'children-display':GLib.Variant('s','submenu')},1:props(self.description,False),
            2:props('Άνοιγμα Phone Link'),3:props('Επανασύνδεση με POCO')}

    def _action(self,identifier,event):
        if event!='clicked':return
        if identifier==2:self.open()
        elif identifier==3:subprocess.Popen(['systemctl','--user','restart','tahoe-phone-link.service'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def open(self):
        subprocess.Popen([str(Path.home()/'.local/bin/tahoe-phone-link'),'open'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def _method(self,connection,sender,path,interface,method,parameters,invocation):
        args=parameters.unpack();items=self._items()
        if interface==SNI:
            if method in ('Activate','SecondaryActivate'):self.open()
            invocation.return_value(None);return
        if method=='GetLayout':
            parent,depth,names=args
            def layout(identifier):
                props={k:v for k,v in items.get(identifier,{}).items() if not names or k in names}
                children=[]
                if identifier==0 and depth!=0:children=[GLib.Variant('(ia{sv}av)',(i,items[i],[])) for i in (1,2,3)]
                return identifier,props,children
            result=GLib.Variant('(u(ia{sv}av))',(self.revision,layout(parent)))
        elif method=='GetGroupProperties':
            ids,names=args;result=GLib.Variant('(a(ia{sv}))',([(i,{k:v for k,v in items.get(i,{}).items() if not names or k in names}) for i in ids],))
        elif method=='GetProperty':result=GLib.Variant('(v)',(items.get(args[0],{}).get(args[1],GLib.Variant('s','')),))
        elif method=='Event':self._action(args[0],args[1]);result=None
        elif method=='EventGroup':
            for i,event,_,_ in args[0]:self._action(i,event)
            result=GLib.Variant('(ai)',([],))
        elif method=='AboutToShow':result=GLib.Variant('(b)',(False,))
        elif method=='AboutToShowGroup':result=GLib.Variant('(aiai)',([],[]))
        else:invocation.return_dbus_error('org.freedesktop.DBus.Error.UnknownMethod',method);return
        invocation.return_value(result)

_instance=None
def start_tray():
    """Start once, returning an object with ready Event and optional error type."""
    global _instance
    if _instance is None:_instance=TrayIcon()
    return _instance

if __name__=='__main__':
    import time
    tray=start_tray();tray.ready.wait(5)
    if tray.error:raise RuntimeError(tray.error)
    while True:time.sleep(60)
