"""Fresh user-operated Microsoft enrollment authorization; retains PL pairing."""
import sys,threading
sys.path.append('/usr/lib/python3/dist-packages')
import gi
gi.require_version('Gtk','4.0');gi.require_version('WebKit','6.0')
from gi.repository import Gtk,WebKit,GLib
from urllib.parse import urlsplit
from urllib.error import HTTPError
from msa_oauth import MsaLogin,ENROLLMENT_SCOPE,REDIRECT
from account_store import load_account,save_account
from crossdevice_role import ensure_role

class Enrollment(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.tahoe.PhoneLink.Enrollment')
        self.connect('activate',self.activate);self.window=None
    def activate(self,*_):
        if self.window:self.window.present();return
        self.oauth=MsaLogin(scope=ENROLLMENT_SCOPE,fresh=True)
        self.window=Gtk.ApplicationWindow(application=self,title='Phone Link — Λειτουργίες υπολογιστή')
        self.window.set_default_size(760,780)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        self.label=Gtk.Label(label='Σύνδεση στον ίδιο Microsoft λογαριασμό για μπαταρία laptop και Lock PC.',wrap=True)
        box.append(self.label)
        self.web=WebKit.WebView(network_session=WebKit.NetworkSession.new_ephemeral());self.web.set_vexpand(True)
        self.web.connect('decide-policy',self.policy)
        box.append(self.web);self.window.set_child(box);self.window.present()
        self.web.load_uri(self.oauth.authorization_url())
    def policy(self,web,decision,kind):
        if kind not in (WebKit.PolicyDecisionType.NAVIGATION_ACTION,WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):return False
        uri=decision.get_navigation_action().get_request().get_uri()
        a,b=urlsplit(uri),urlsplit(REDIRECT)
        if (a.scheme,a.netloc,a.path)==(b.scheme,b.netloc,b.path):
            decision.ignore();self.web.set_visible(False)
            self.label.set_text('Ελέγχεται η ειδική άδεια εγγραφής στη Microsoft…')
            threading.Thread(target=self.finish,args=(uri,),daemon=True).start();return True
        return False
    def finish(self,uri):
        try:
            value=self.oauth.exchange_callback(uri)
            account,_=load_account();account['msa_sapi']=value
            role=ensure_role(account)
            if value.get('refresh_token'):account['msa']['refresh_token']=value['refresh_token']
            if not save_account(account):raise RuntimeError('Secure storage failed')
            GLib.idle_add(self.label.set_text,'Η Microsoft ενέκρινε την εγγραφή λειτουργιών υπολογιστή.')
            print('enrollment_authorization_accepted',flush=True)
        except HTTPError as error:
            GLib.idle_add(self.label.set_text,'Η Microsoft δεν ενέκρινε ακόμη την ειδική εγγραφή (HTTP '+str(error.code)+'). Η υπάρχουσα σύζευξη διατηρείται.')
            print('enrollment_authorization_http_'+str(error.code),flush=True)
        except Exception as error:
            GLib.idle_add(self.label.set_text,'Η ειδική εγγραφή δεν ολοκληρώθηκε ('+type(error).__name__+'). Η υπάρχουσα σύζευξη διατηρείται.')
            print('enrollment_authorization_error_'+type(error).__name__,flush=True)

if __name__=='__main__':Enrollment().run([sys.argv[0]])
