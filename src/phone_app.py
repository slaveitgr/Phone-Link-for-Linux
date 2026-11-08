"""Native Ubuntu account authorization window. Secrets never enter status.json."""
import os
import sys
from pathlib import Path
sys.path.append('/usr/lib/python3/dist-packages')
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('WebKit', '6.0')
from gi.repository import Gtk, Gio, GLib, WebKit, Pango
import json
import threading
import time
import subprocess
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from urllib.error import HTTPError
from msa_oauth import MsaLogin, REDIRECT
from device_identity import DeviceIdentity
from identity_service import IdentityService
from account_store import load_account, save_account
from secret_store import KeyringLocked
from pairing_service import PairingService
from cryptography.hazmat.primitives import serialization

STATE_DIR = Path.home()/'.local/state/tahoe-phone-link'

def status(state, message, **extra):
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    value = dict(schema_version=1, state=state, message=message,
        device={'name':'POCO F8 Ultra'}, capabilities=[], actions=['login','open'],
        updated_at=datetime.now(timezone.utc).isoformat())
    value.update(extra)
    temp = STATE_DIR/('status.'+uuid.uuid4().hex+'.tmp')
    fd = os.open(temp, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd,'w') as f: json.dump(value,f)
    os.replace(temp, STATE_DIR/'status.json')

class PhoneApp(Gtk.Application):
    def __init__(self, auto_login=False):
        super().__init__(application_id='local.tahoe.PhoneLink',flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.auto_login=auto_login
        self.hold()
        from call_controller import CallController
        self.call_controller=CallController(self)
        from phone_streaming import PhoneStreaming
        from webcam_controller import WebcamController
        self.streaming=PhoneStreaming();self.webcam_controller=WebcamController()
        self.file_state={'status':'not_loaded','files':[]}
        self.transfer_state=''
        self.phone_apps={'status':'not_loaded','apps':[]}
        self.phone_messages={'status':'not_loaded','messages':[]}
        self.connect('activate',self.activate_ui)
        calls_action=Gio.SimpleAction.new('calls',None)
        calls_action.connect('activate',lambda *_:self.open_dashboard_tab('calls'))
        self.add_action(calls_action)
        clipboard_action=Gio.SimpleAction.new('clipboard',None)
        clipboard_action.connect('activate',lambda *_:self.open_dashboard_tab('clipboard'))
        self.add_action(clipboard_action)
        for tab in ('notifications','messages','photos','settings','files','apps'):
            action=Gio.SimpleAction.new(tab,None)
            action.connect('activate',lambda _,param,target=tab:self.open_dashboard_tab(target))
            self.add_action(action)
        self.window=None
        self.oauth=None
        self.tokens=None
        self.identity=None
        self.device_auth=None
        self.account=None
        self.pairing_started=False

    def do_shutdown(self):
        self.streaming.stop_all()
        self.webcam_controller.stop()
        Gtk.Application.do_shutdown(self)

    def activate_ui(self,*args):
        if self.window:
            self.window.present()
            return
        self.window=Gtk.ApplicationWindow(application=self,title='Phone Link — Ubuntu')
        self.window.set_default_size(760,780)
        self.window.connect('close-request',lambda window:(window.hide(),True)[1])
        layout=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        self.layout=layout
        for side in ['top','bottom','start','end']:getattr(layout,'set_margin_'+side)(12)
        self.label=Gtk.Label(label='Σύνδεσε το POCO με το Ubuntu μέσω Microsoft.',wrap=True)
        layout.append(self.label)
        self.login_button=Gtk.Button(label='Σύνδεση με Microsoft')
        self.login_button.connect('clicked',self.login_clicked)
        self.keyring_locked=False
        layout.append(self.login_button)
        self.qr=Gtk.Picture()
        self.qr.set_size_request(320,320)
        self.qr.set_visible(False)
        layout.append(self.qr)
        self.pin=Gtk.Label(label='',selectable=True)
        self.pin.set_visible(False)
        layout.append(self.pin)
        self.web=WebKit.WebView(network_session=WebKit.NetworkSession.new_ephemeral())
        self.web.set_vexpand(True)
        self.web.connect('decide-policy',self.decide_policy)
        self.web.connect('load-failed',self.load_failed)
        layout.append(self.web)
        self.window.set_child(layout)
        self.window.present()
        threading.Thread(target=self.restore_connection,daemon=True).start()

    def restore_connection(self):
        try:
            current=json.loads((STATE_DIR/'status.json').read_text())
            if current.get('authenticated') and current.get('state') in ('paired','connected','connecting','disconnected','error'):
                GLib.idle_add(self.show_dashboard)
                return
        except (OSError,ValueError):pass
        try:
            saved=load_account()
            if saved:
                self.account,self.identity=saved
                self.tokens=self.account['msa']
                self.device_auth=self.account['device_auth']
                if self.account.get('pairing_session'):
                    GLib.idle_add(self.show_pairing)
                    return
                GLib.idle_add(self.set_message,'Ο Microsoft λογαριασμός είναι συνδεδεμένος. Ετοιμάζεται η σύζευξη.')
                return
            status('signed_out','Χρειάζεται σύνδεση Microsoft στο Ubuntu.')
            if self.auto_login:GLib.idle_add(self.start_login)
        except KeyringLocked:
            self.keyring_locked=True
            GLib.idle_add(self.login_button.set_label,'Ξεκλείδωμα αποθηκευμένης σύνδεσης')
            GLib.idle_add(self.set_message,'Ξεκλείδωσε το Login keyring για να ανακτηθεί η σύνδεση.')
        except Exception as error:
            self.keyring_locked=True
            GLib.idle_add(self.login_button.set_label,'Ανάκτηση αποθηκευμένης σύνδεσης')
            GLib.idle_add(self.set_message,'Δεν ανακτήθηκε ακόμη η αποθηκευμένη σύνδεση ('+type(error).__name__+'). Δεν χρειάζεται νέα σύζευξη.')

    def login_clicked(self,*args):
        if self.keyring_locked:
            threading.Thread(target=self.restore_connection,daemon=True).start()
        else:self.start_login()

    def show_pairing(self):
        if self.pairing_started:return GLib.SOURCE_REMOVE
        self.pairing_started=True
        self.login_button.set_visible(False)
        self.web.set_visible(False)
        session=self.account['pairing_session']
        if session.get('state')=='DEVICE_PAIRED':
            self.show_dashboard()
            return GLib.SOURCE_REMOVE
        if session.get('pairingLink'):
            import qrcode
            from qrcode.image.svg import SvgPathFillImage
            qr=qrcode.make(session['pairingLink'],image_factory=SvgPathFillImage,
                           border=4,box_size=10)
            path=STATE_DIR/'pairing-qr.svg'
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(fd,'wb') as stream:qr.save(stream)
            self.qr.set_filename(str(path))
            self.qr.set_visible(True)
        self.set_message('Στο POCO άνοιξε «Σύνδεση στα Windows» → Προσθήκη υπολογιστή και σάρωσε το QR. Επίλεξε PC/Windows αν σε ρωτήσει.')
        status('pairing','Σάρωσε το QR στο παράθυρο Phone Link με το POCO.',authenticated=True)
        threading.Thread(target=self.poll_pairing,daemon=True).start()
        return GLib.SOURCE_REMOVE

    def show_dashboard(self):
        if getattr(self,'dashboard',False):return
        from dashboard_web import Dashboard
        self.dashboard=True
        child=self.layout.get_first_child()
        while child:
            following=child.get_next_sibling()
            self.layout.remove(child)
            child=following
        for side in ['top','bottom','start','end']:getattr(self.layout,'set_margin_'+side)(0)
        self.layout.set_spacing(0)
        self.window.set_default_size(1180,780)
        self.dashboard_view=Dashboard(self)
        self.layout.append(self.dashboard_view.web)

    def open_dashboard_tab(self,tab):
        self.activate_ui()
        self.pending_dashboard_tab=tab
        view=getattr(self,'dashboard_view',None)
        if view and view.ready:view.js('phoneLinkNavigate',tab)

    def open_calls(self,*args):
        from phone_calls_ui import CallsWindow
        window=getattr(self,'calls_window',None)
        if window is None or window.closed:
            window=CallsWindow(self.window)
            self.calls_window=window
        window.present()

    def refresh_dashboard(self):
        try:
            info=json.loads((STATE_DIR/'status.json').read_text())
            state=info.get('state','paired')
            if state=='connected':
                updated=datetime.fromisoformat(info['updated_at'])
                if (datetime.now(timezone.utc)-updated).total_seconds()>90:state='disconnected'
            labels={'connected':'● Συνδεδεμένο','paired':'● Συζευγμένο',
                'connecting':'● Γίνεται σύνδεση…','disconnected':'● Εκτός σύνδεσης',
                'error':'● Χρειάζεται έλεγχος'}
            self.connection_label.set_text(labels.get(state,'● Συζευγμένο'))
            self.detail_label.set_text(info.get('message','Η σύζευξη με το POCO είναι αποθηκευμένη.'))
            device=info.get('device',{})
            clip_ready=state=='connected' and 'clipboard' in info.get('capabilities',[])
            self.send_clipboard_button.set_sensitive(clip_ready and self.clipboard_input.get_buffer().get_char_count()>0)
            self.receive_clipboard_button.set_sensitive(clip_ready and self.phone_clipboard is not None)
            if clip_ready and not self.pending_clipboard:
                self.clipboard_message.set_text('Στείλε κείμενο ή αντέγραψε το τελευταίο κείμενο από το POCO.')
            wallpaper=device.get('wallpaper_path')
            allowed={str(STATE_DIR/('phone-wallpaper.'+ext)) for ext in ('jpg','png','webp')}
            if wallpaper in allowed and Path(wallpaper).is_file():
                if self.phone_wallpaper_path!=wallpaper:
                    self.phone_preview.set_filename(wallpaper)
                    self.phone_wallpaper_path=wallpaper
                self.phone_preview.set_visible(True)
            radios=[]
            if state=='connected':
                for key,label in [('wifi_enabled','Wi-Fi'),('bluetooth_enabled','Bluetooth')]:
                    if type(device.get(key)) is bool:radios.append(label+(': On' if device[key] else ': Off'))
            self.radio_label.set_text(' · '.join(radios))
            battery=device.get('battery_percent')
            if isinstance(battery,int) and 0<=battery<=100 and state=='connected':
                self.battery_label.set_text('Μπαταρία: '+str(battery)+'%'+(' · Φόρτιση' if device.get('charging') else ''))
                self.battery_bar.set_fraction(battery/100)
                self.battery_bar.set_visible(True)
            else:
                self.battery_label.set_text('Μπαταρία: αναμονή ενημέρωσης')
                self.battery_bar.set_visible(False)
        except (OSError,ValueError,TypeError):pass
        try:
            from runtime_cache import read_snapshot
            view=read_snapshot()
            self.phone_clipboard=view.get('clipboard')
            if self.pending_clipboard:
                outcome=view.get('command_results',{}).get(self.pending_clipboard)
                if outcome:
                    self.clipboard_message.set_text('Το κείμενο στάλθηκε στο POCO.' if outcome=='sent' else 'Η αποστολή δεν ολοκληρώθηκε.')
                    self.pending_clipboard=None
            revision=json.dumps(view.get('notifications',[]),ensure_ascii=False)
            if revision!=self.notification_revision:
                self.notification_revision=revision
                child=self.notification_box.get_first_child()
                while child:
                    following=child.get_next_sibling()
                    self.notification_box.remove(child);child=following
                records=view.get('notifications',[])
                if not records:
                    text='Δεν υπάρχουν ειδοποιήσεις από τη σύνδεση αυτή.' if view.get('notifications_synced') else 'Αναμονή ειδοποιήσεων από το κινητό.'
                    self.notification_box.append(Gtk.Label(label=text,wrap=True,xalign=0))
                for record in reversed(records):
                    row=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
                    app=Gtk.Label(label=record.get('app',''),xalign=0)
                    app.add_css_class('dim-label');row.append(app)
                    title=Gtk.Label(label=record.get('title',''),xalign=0,wrap=True)
                    title.add_css_class('heading');row.append(title)
                    text=Gtk.Label(label=record.get('body',''),xalign=0,wrap=True)
                    text.set_max_width_chars(60);text.set_lines(4)
                    text.set_ellipsize(Pango.EllipsizeMode.END);row.append(text)
                    self.notification_box.append(row)
        except (OSError,ValueError,TypeError):pass
        return GLib.SOURCE_CONTINUE

    def send_clipboard_text(self,*args):
        from runtime_cache import send_clipboard
        buffer=self.clipboard_input.get_buffer()
        text=buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True)
        if not text:
            self.clipboard_message.set_text('Γράψε ή επικόλλησε πρώτα το κείμενο που θέλεις να στείλεις.')
            return
        try:
            response=send_clipboard(text)
            self.pending_clipboard=response['id']
            self.clipboard_message.set_text('Αποστολή του κειμένου στο POCO…')
        except (OSError,ValueError,KeyError):
            self.clipboard_message.set_text('Η σύνδεση δεν είναι έτοιμη για αποστολή.')

    def copy_phone_clipboard(self,*args):
        if self.phone_clipboard is not None:
            self.window.get_clipboard().set(self.phone_clipboard)
            self.clipboard_message.set_text('Το κείμενο του POCO αντιγράφηκε στο πρόχειρο του Ubuntu.')

    def update_pairing(self,session):
        state=session.get('state','')
        pin=session.get('challengePIN') or session.get('pairingPIN')
        if pin:
            self.pin.set_text('Κωδικός επιβεβαίωσης: '+str(pin))
            self.pin.set_visible(True)
        if state=='DEVICE_PAIRED':
            self.qr.set_visible(False)
            self.pin.set_visible(False)
            self.set_message('Το POCO συζεύχθηκε επιτυχώς με το Ubuntu. Ετοιμάζεται η ζωντανή σύνδεση.')
            self.show_dashboard()
        elif state!='PENDING_PAIRING_LINK_VISIT':
            self.set_message('Συνέχισε την επιβεβαίωση στο POCO. Κατάσταση: '+state)
        return GLib.SOURCE_REMOVE

    def poll_pairing(self):
        client=PairingService(lambda:self.tokens['access_token'],'3.0.0',region='GR')
        session_id=self.account['pairing_session']['pairingSessionId']
        completed=False
        try:
            for _ in range(400):
                session=client.get_session(session_id)
                self.account['pairing_session'].update(session)
                state=session.get('state','')
                GLib.idle_add(self.update_pairing,self.account['pairing_session'].copy())
                if state=='READY_FOR_COMPLETE' and not completed:
                    client.complete_session(session_id)
                    completed=True
                if state=='DEVICE_PAIRED':
                    save_account(self.account)
                    status('paired','Το POCO συζεύχθηκε. Η ζωντανή σύνδεση ετοιμάζεται.',authenticated=True)
                    try:(STATE_DIR/'pairing-qr.svg').unlink()
                    except FileNotFoundError:pass
                    return
                if any(x in state for x in ['FAILED','MISMATCHED','CANCELLED','EXPIRED']):
                    status('error','Η σύζευξη χρειάζεται νέα προσπάθεια: '+state,authenticated=True)
                    return
                time.sleep(3)
            status('disconnected','Η αναμονή σύζευξης έληξε.',authenticated=True)
        except HTTPError as error:
            status('error',f'Σφάλμα σύζευξης Microsoft HTTP {error.code}.',authenticated=True)
            GLib.idle_add(self.set_message,f'Η σύζευξη επέστρεψε HTTP {error.code}.')
        except Exception as error:
            status('error','Σφάλμα σύζευξης: '+type(error).__name__,authenticated=True)
            GLib.idle_add(self.set_message,'Η σύζευξη διακόπηκε: '+type(error).__name__)

    def set_message(self,message):
        self.label.set_text(message)
        return GLib.SOURCE_REMOVE

    def start_login(self):
        self.oauth=MsaLogin()
        self.login_button.set_sensitive(False)
        self.set_message('Συνδέσου στην επίσημη σελίδα της Microsoft. Μην στείλεις κωδικό στο chat.')
        status('signing_in','Περιμένει σύνδεση και έγκριση στη σελίδα Microsoft.')
        self.web.load_uri(self.oauth.authorization_url())

    def decide_policy(self,web,decision,kind):
        if kind != WebKit.PolicyDecisionType.NAVIGATION_ACTION:return False
        uri=decision.get_navigation_action().get_request().get_uri()
        p=urlsplit(uri);r=urlsplit(REDIRECT)
        if (p.scheme,p.netloc,p.path)==(r.scheme,r.netloc,r.path) and p.query:
            decision.ignore()
            # No callback URL, authorization code or token is printed or written to disk.
            self.web.load_html('<html><body><h2>Ολοκλήρωση σύνδεσης…</h2></body></html>',None)
            threading.Thread(target=self.finish_login,args=(uri,),daemon=True).start()
            return True
        return False

    def load_failed(self,web,event,uri,error):
        if not self.oauth:return False
        # Do not echo the URI because a redirect could contain an authorization code.
        GLib.idle_add(self.set_message,'Η σελίδα δεν φορτώθηκε. Δοκίμασε ξανά τη σύνδεση Microsoft.')
        GLib.idle_add(self.login_button.set_sensitive,True)
        return False

    def finish_login(self,callback):
        try:
            self.tokens=self.oauth.exchange_callback(callback)
            GLib.idle_add(self.set_message,'Εγκρίθηκε ο Microsoft λογαριασμός. Δημιουργείται ταυτότητα Ubuntu…')
            now=datetime.now(timezone.utc)
            self.identity=DeviceIdentity(str(uuid.uuid4()),now=now,
                  certificate_validity=timedelta(days=365),clock_skew=timedelta(hours=12))
            self.device_auth=IdentityService(lambda:self.tokens['access_token']).create_identity(self.identity)
            secret={'msa':self.tokens,'client_id':self.identity.client_id,'device_auth':self.device_auth,
                'key':self.identity._key.private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode(),
                'certificate':self.identity.certificate.public_bytes(serialization.Encoding.PEM).decode()}
            stored=save_account(secret)
            status('disconnected','Εγκρίθηκε η ταυτότητα του Ubuntu. Ακολουθεί σύζευξη με το POCO.',
                authenticated=True,credentials_saved=bool(stored))
            GLib.idle_add(self.set_message,'Η Microsoft ενέκρινε την ταυτότητα του Ubuntu. Η σύζευξη δεν έχει ολοκληρωθεί ακόμη.')
        except HTTPError as error:
            message=f'Η υπηρεσία Microsoft επέστρεψε HTTP {error.code}. Η σύζευξη δεν ολοκληρώθηκε.'
            status('error',message,authenticated=False)
            GLib.idle_add(self.set_message,message)
        except Exception as error:
            # Avoid logging exception data that may contain server responses or credentials.
            message='Η σύνδεση δεν ολοκληρώθηκε ('+type(error).__name__+'). Μπορείς να δοκιμάσεις ξανά.'
            status('error',message,authenticated=False)
            GLib.idle_add(self.set_message,message)
        finally:
            GLib.idle_add(self.login_button.set_sensitive,True)

if __name__=='__main__':
    command=sys.argv[1] if len(sys.argv)>1 else 'open'
    if command=='status':
        p=STATE_DIR/'status.json'
        print(p.read_text() if p.exists() else '{"schema_version":1,"state":"signed_out"}')
    elif command in ('login','open'):
        PhoneApp(auto_login=command=='login').run([sys.argv[0]])
    else:
        raise SystemExit('Pairing is not enabled until account authorization and enrollment succeed.')
