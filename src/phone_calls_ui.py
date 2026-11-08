"""User-operated Bluetooth call controls; never dials on startup."""
import threading
import gi
gi.require_version("Gtk","4.0")
from gi.repository import Gtk,GLib
from phone_config import bluetooth_address
from phone_calls import PhoneCalls,CallAudio

class CallsWindow(Gtk.Window):
    def __init__(self, parent):
        super().__init__(title='Κλήσεις — POCO F8 Ultra',transient_for=parent)
        self.set_default_size(380,580)
        self.calls=PhoneCalls(bluetooth_address())
        self.call_audio=CallAudio(self.calls)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14)
        for edge in ('top','bottom','start','end'):getattr(box,'set_margin_'+edge)(20)
        self.set_child(box)
        self.state=Gtk.Label(label='Έλεγχος Bluetooth…',wrap=True);box.append(self.state)
        phone=Gtk.Image.new_from_icon_name('call-start-symbolic');phone.set_pixel_size(48);box.append(phone)
        self.number=Gtk.Entry(placeholder_text='Αριθμός τηλεφώνου')
        self.number.set_alignment(.5);box.append(self.number)
        keypad=Gtk.Grid(column_homogeneous=True,row_homogeneous=True,column_spacing=10,row_spacing=10)
        for index,digit in enumerate('123456789*0#'):
            key=Gtk.Button(label=digit);key.set_size_request(64,48)
            key.connect('clicked',lambda _,d=digit:self.number.set_text(self.number.get_text()+d))
            keypad.attach(key,index%3,index//3,1,1)
        box.append(keypad)
        self.dial=Gtk.Button(label='Κλήση')
        self.dial.add_css_class('suggested-action')
        self.dial.connect('clicked',self.dial_number)
        box.append(self.dial)
        self.answer=Gtk.Button(label='Απάντηση');self.answer.connect('clicked',self.answer_call);box.append(self.answer)
        self.hangup=Gtk.Button(label='Τερματισμός κλήσης');self.hangup.connect('clicked',self.end_call);box.append(self.hangup)
        self.audio=Gtk.Button(label='Ήχος στο laptop');self.audio.connect('clicked',lambda *_:self.run_action(lambda:self.call_audio.start(user_initiated=True)));box.append(self.audio)
        self.error=Gtk.Label(wrap=True);box.append(self.error)
        self.records=[];self.closed=False;self.busy=False
        self.connect('close-request',self.on_close)
        self.tick();GLib.timeout_add_seconds(1,self.tick)

    def on_close(self,*_):
        self.closed=True
        threading.Thread(target=self.call_audio.stop,daemon=True).start()
        return False
    def run_action(self,action):
        def worker():
            try:action();GLib.idle_add(self.error.set_text,'')
            except Exception as error:GLib.idle_add(self.error.set_text,'Η ενέργεια δεν ολοκληρώθηκε ('+type(error).__name__+').')
        threading.Thread(target=worker,daemon=True).start()
    def dial_number(self,*_):
        number=self.number.get_text()
        self.start_call(lambda:self.calls.dial(number))

    def start_call(self,action):
        def connect_audio():
            import time
            action()
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                if any(c.get('State') in ('active','dialing','alerting') for c in self.calls.get_calls()):
                    self.call_audio.start(user_initiated=True)
                    return
                time.sleep(.25)
        self.run_action(connect_audio)
    def answer_call(self,*_):
        call=next((c for c in self.records if c.get('State') in ('incoming','waiting')),None)
        if call:self.start_call(lambda:self.calls.answer(call['path']))
    def end_call(self,*_):
        if self.records:
            path=self.records[0]['path'];self.run_action(lambda:self.calls.hangup(path))
    def tick(self):
        if self.closed:return GLib.SOURCE_REMOVE
        if not self.busy:
            self.busy=True
            def worker():
                try:info=self.calls.status()
                except Exception:info={'available':False,'calls':[]}
                GLib.idle_add(self.update,info)
            threading.Thread(target=worker,daemon=True).start()
        return GLib.SOURCE_CONTINUE
    def update(self,info):
        self.busy=False
        if self.closed:return False
        self.records=info.get('calls',[])
        active=info.get('available',False)
        self.state.set_text('Bluetooth συνδεδεμένο'+(' · '+', '.join(c.get('State','') for c in self.records) if self.records else ' · Χωρίς ενεργή κλήση') if active else 'Το POCO δεν είναι διαθέσιμο για κλήσεις Bluetooth.')
        self.dial.set_sensitive(active and not self.records)
        self.answer.set_sensitive(any(c.get('State') in ('incoming','waiting') for c in self.records))
        self.hangup.set_sensitive(bool(self.records))
        self.audio.set_sensitive(any(c.get('State') in ('active','dialing','alerting') for c in self.records))
        return False
