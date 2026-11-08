"""Shared real HFP call controller for embedded dialer and incoming popup."""
import threading,time,re,json
from gi.repository import GLib,Gio
from phone_config import bluetooth_address
from phone_calls import PhoneCalls,CallAudio

class CallController:
    def __init__(self,app):
        self.app=app;self.phone=PhoneCalls(bluetooth_address()) if bluetooth_address() else None;self.audio=CallAudio(self.phone) if self.phone else None
        self.info={'available':False,'calls':[]};self.busy=False;self.action_busy=False;self.error='';self.popup=None;self.audio_busy=False;self.audio_state='idle';self.media_cleanup_needed=True
        GLib.timeout_add_seconds(1,self.tick)
    def tick(self):
        if not self.busy:
            self.busy=True
            threading.Thread(target=self.read,daemon=True).start()
        return GLib.SOURCE_CONTINUE
    def read(self):
        try:info=self.phone.status() if self.phone else {'available':False,'calls':[]}
        except Exception:info={'available':False,'calls':[]}
        if self.phone and info.get('available') and not info.get('calls') and self.media_cleanup_needed:
            try:
                if self.phone.disconnect_media_audio():self.media_cleanup_needed=False
            except Exception:pass
        if info.get('calls'):self.media_cleanup_needed=True
        GLib.idle_add(self.update,info)
    def update(self,info):
        self.busy=False;self.info=info
        incoming=any(c.get('State') in ('incoming','waiting') for c in info.get('calls',[]))
        if incoming and self.popup is None:
            from dashboard_web import IncomingCallPopup
            self.popup=IncomingCallPopup(self.app)
            self.popup.present()
        elif not incoming and self.popup is not None:
            self.popup.destroy();self.popup=None
        return GLib.SOURCE_REMOVE
    def snapshot(self):
        return {**self.info,'error':self.error,'action_busy':self.action_busy,'audio_state':self.audio_state}
    def action(self,kind,number=None):
        if self.action_busy:return
        if kind=='dial':
            if not isinstance(number,str):return
            number=re.sub(r'[\s()-]','',number)
            if not re.fullmatch(r'[0-9+*#,ABCD]{1,80}',number):return
        self.action_busy=True
        threading.Thread(target=self.perform,args=(kind,number),daemon=True).start()
    def perform(self,kind,number):
        try:
            calls=self.phone.get_calls()
            if kind=='dial':
                if calls:raise RuntimeError('Call already active')
                self.phone.dial(number)
            elif kind=='answer':
                call=next((c for c in calls if c.get('State') in ('incoming','waiting')),None)
                if not call:raise RuntimeError('No incoming call')
                self.phone.answer(call['path'])
            elif kind=='hangup':
                if calls:self.phone.hangup(calls[0]['path'])
            elif kind=='audio':self.audio.start(user_initiated=True)
            else:raise ValueError('Unsupported action')
            self.error=''
            if kind in ('dial','answer') and not self.audio_busy:
                self.audio_busy=True
                threading.Thread(target=self.ensure_audio,daemon=True).start()
        except Exception as error:
            # A successfully created HFP call is authoritative even if a later
            # D-Bus response races the call object or audio transport.
            accepted=False
            if kind in ('dial','answer'):
                try:accepted=any(c.get('State') in ('active','dialing','alerting') for c in self.phone.get_calls())
                except Exception:pass
            self.error='' if accepted else 'The call command could not be completed.'
            remote=Gio.DBusError.get_remote_error(error) if isinstance(error,GLib.Error) else None
            print(json.dumps({'event':'call_command_error','action':kind,'type':type(error).__name__,'remote_error':remote,'live_call_observed':accepted}),flush=True)
        finally:self.action_busy=False

    def ensure_audio(self):
        self.audio_state='connecting'
        try:
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                try:
                    calls=self.phone.get_calls()
                    if not calls:
                        self.audio_state='idle';return
                    if any(c.get('State') in ('active','dialing','alerting') for c in calls):
                        self.audio.start(user_initiated=True)
                        self.audio_state='active';return
                except Exception as error:
                    remote=Gio.DBusError.get_remote_error(error) if isinstance(error,GLib.Error) else None
                    print(json.dumps({'event':'call_audio_retry','type':type(error).__name__,'remote_error':remote}),flush=True)
                time.sleep(.75)
            self.audio_state='unavailable'
        finally:self.audio_busy=False
