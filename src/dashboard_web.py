"""Local mockup design bound to the real Phone Link bridge."""
import base64,json,threading
from concurrent.futures import ThreadPoolExecutor
_PHOTO_WORKER=ThreadPoolExecutor(max_workers=1,thread_name_prefix="phone-photo")
from pathlib import Path
from gi.repository import Gtk,GLib,WebKit,Gdk
from runtime_cache import read_snapshot,send_clipboard,search_contacts

class Dashboard:
    def __init__(self,app):
        self.app=app;self.alive=True;self.ready=False;self.image_key=None;self.image=None;self.photo_pending=set()
        manager=WebKit.UserContentManager()
        manager.register_script_message_handler('phoneLink',None)
        manager.connect('script-message-received::phoneLink',self.message)
        self.web=WebKit.WebView(user_content_manager=manager,network_session=WebKit.NetworkSession.new_ephemeral())
        color=Gdk.RGBA();color.parse('transparent');self.web.set_background_color(color)
        self.web.get_settings().set_enable_write_console_messages_to_stdout(True)
        self.web.set_vexpand(True);self.web.set_hexpand(True)
        self.web.connect('decide-policy',self.policy)
        self.web.connect('load-changed',self.loaded)
        self.web.load_uri((Path(__file__).parent/'ui/index.html').as_uri())
        self.root=(Path(__file__).parent/'ui').as_uri()+'/'
        GLib.timeout_add_seconds(1,self.tick)
    def policy(self,web,decision,kind):
        if kind==WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            uri=decision.get_navigation_action().get_request().get_uri()
            if not uri.startswith(self.root):decision.ignore();return True
        return False
    def loaded(self,web,event):
        if event==WebKit.LoadEvent.FINISHED:
            self.ready=True;self.tick()
            tab=getattr(self.app,'pending_dashboard_tab',None)
            if tab:
                self.app.pending_dashboard_tab=None
                self.js('phoneLinkNavigate',tab)
    def js(self,name,value):
        if self.ready:self.web.evaluate_javascript('if(typeof window.'+name+'==="function")window.'+name+'('+json.dumps(value)+')',-1,None,None,None,None,None)
    def tick(self):
        if not self.alive:return GLib.SOURCE_REMOVE
        if self.ready and not getattr(self,'busy',False):
            self.busy=True;threading.Thread(target=self.collect,daemon=True).start()
        return GLib.SOURCE_CONTINUE
    def collect(self):
        try:
            directory=Path.home()/'.local/state/tahoe-phone-link'
            data=json.loads((directory/'status.json').read_text())
            try:data.update(read_snapshot())
            except (OSError,ValueError):pass
            path=data.get('device',{}).get('wallpaper_path')
            if path in {str(directory/('phone-wallpaper.'+ext)) for ext in ('jpg','png','webp')}:
                p=Path(path);key=(path,p.stat().st_mtime_ns)
                if key!=self.image_key:
                    raw=p.read_bytes()
                    if len(raw)<=16*1024*1024:
                        mime={'jpg':'jpeg','png':'png','webp':'webp'}[p.suffix[1:]]
                        self.image='data:image/'+mime+';base64,'+base64.b64encode(raw).decode();self.image_key=key
                data['wallpaper']=self.image
            data['telephony']=self.app.call_controller.snapshot()
            GLib.idle_add(self.deliver,data)
        except (OSError,ValueError):GLib.idle_add(self.deliver,{})
    def deliver(self,data):
        self.busy=False
        if data:
            self.js('phoneLinkUpdate',data)
            self.js('dialerUpdate',data)
        return GLib.SOURCE_REMOVE
    def message(self,manager,value):
        try:
            request=json.loads(value.to_string());action=request.get('action')
            if action=='calls':self.app.open_dashboard_tab('calls')
            elif action in ('dial','answer','hangup','audio'):
                self.app.call_controller.action(action,request.get('number'))
                if action=='answer':self.app.open_dashboard_tab('calls')
            elif action=='contact_photo':
                number=request.get('number');key=request.get('key')
                if isinstance(number,str) and isinstance(key,str) and len(number)<=100 and len(key)<=200 and key not in self.photo_pending and len(self.photo_pending)<24:
                    self.photo_pending.add(key)
                    _PHOTO_WORKER.submit(self.load_photo,key,number)
            elif action=='search_contacts':
                query=request.get('query')
                if isinstance(query,str) and query.strip() and len(query)<=500:
                    def search():
                        try:search_contacts(query)
                        except (OSError,ValueError):pass
                    threading.Thread(target=search,daemon=True).start()
            elif action=='copy_clipboard':
                def copy():
                    try:text=read_snapshot().get('clipboard')
                    except (OSError,ValueError):return
                    if isinstance(text,str):GLib.idle_add(self.copy,text)
                threading.Thread(target=copy,daemon=True).start()
            elif action=='send_clipboard':
                text=request.get('text')
                if isinstance(text,str) and len(text.encode())<=65536:
                    threading.Thread(target=self.send,args=(text,),daemon=True).start()
        except (ValueError,TypeError):pass
    def load_photo(self,key,number):
        from phone_contact_photos import pull_contact_photo
        try:result=pull_contact_photo(number)
        except Exception:result={'status':'unavailable'}
        GLib.idle_add(self.deliver_photo,key,result)
    def deliver_photo(self,key,result):
        self.photo_pending.discard(key)
        if self.alive:self.js('phoneLinkPhoto',{'key':key,'status':result.get('status'),'data_url':result.get('data_url')})
        return GLib.SOURCE_REMOVE
    def copy(self,text):
        self.web.get_clipboard().set(text);self.js('phoneLinkToast','Copied from phone')
    def send(self,text):
        try:send_clipboard(text);result='Queued for sending to phone'
        except (OSError,ValueError):result='Phone connection is unavailable'
        GLib.idle_add(self.js,'phoneLinkToast',result)


class IncomingCallPopup(Gtk.Window):
    def __init__(self,app):
        super().__init__(application=app,title='Incoming call — Phone Link')
        self.set_default_size(350,540)
        self.controller=Dashboard(app)
        self.controller.web.load_uri((Path(__file__).parent/'ui/dialer/index.html').as_uri()+'?incoming=1')
        self.set_child(self.controller.web)
        self.connect('close-request',self.hide_popup)
        self.connect('destroy',lambda *_:setattr(self.controller,'alive',False))
    def hide_popup(self,*_):
        self.hide()
        return True
