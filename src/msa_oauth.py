"""User-interactive public native-client MSA flow; no embedded password handling.

Constants corroborated by the APK and ZonD80/msft-phone-link-docs (MIT).
Server acceptance, including legacy endpoint PKCE support, remains untested.
Tokens stay in memory; callers must not log token responses or callback URLs.
"""
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener
from pairing_service import NoRedirects

CLIENT_ID = '000000004018945C'
SCOPE = 'service::msatoken.dcg.microsoft.com::MBI_SSL'
ENROLLMENT_SCOPE = 'service::msatoken.dcg.microsoft.com::SAPI'
REDIRECT = 'https://login.live.com/oauth20_desktop.srf'
TOKEN_URL = 'https://login.live.com/oauth20_token.srf'

def refresh_tokens(previous, *, transport=None, scope=SCOPE):
    if scope not in (SCOPE,ENROLLMENT_SCOPE):raise ValueError("Unexpected Microsoft service scope")
    refresh=previous.get('refresh_token')
    if not isinstance(refresh,str) or not refresh:
        raise ValueError('Interactive authorization is required')
    body=urlencode({'client_id':CLIENT_ID,'grant_type':'refresh_token',
        'refresh_token':refresh,'scope':scope}).encode()
    if transport:
        result=transport(TOKEN_URL,body)
    else:
        request=Request(TOKEN_URL,data=body,method='POST',
            headers={'Content-Type':'application/x-www-form-urlencoded'})
        with build_opener(NoRedirects()).open(request,timeout=20) as response:
            raw=response.read(1024*1024+1)
            if len(raw)>1024*1024:raise ValueError('Token response exceeds limit')
            result=json.loads(raw)
    if not isinstance(result,dict) or not result.get('access_token'):
        raise ValueError('Microsoft did not refresh authorization')
    result.setdefault('refresh_token',refresh)
    result['obtained_at']=time.time()
    return result

class MsaLogin:
    def __init__(self, *, scope=SCOPE, fresh=False):
        if scope not in (SCOPE,ENROLLMENT_SCOPE):raise ValueError("Unexpected Microsoft service scope")
        self.scope=scope
        self.fresh=fresh
        self._state = secrets.token_urlsafe(32)
        self._verifier = secrets.token_urlsafe(64)
        self._used = False

    def authorization_url(self):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self._verifier.encode()).digest()).rstrip(b'=').decode()
        return 'https://login.live.com/oauth20_authorize.srf?' + urlencode({
            'client_id': CLIENT_ID, 'response_type': 'code', 'redirect_uri': REDIRECT,
            'scope': self.scope, 'state': self._state,
            **({'prompt':'login'} if self.fresh else {}),
            'code_challenge': challenge, 'code_challenge_method': 'S256'})

    def exchange_callback(self, callback_url, *, transport=None):
        if self._used:
            raise ValueError('This login attempt has already been consumed')
        parsed = urlsplit(callback_url)
        expected = urlsplit(REDIRECT)
        if (parsed.scheme, parsed.netloc, parsed.path) != (expected.scheme, expected.netloc, expected.path) or parsed.fragment:
            raise ValueError('Unexpected Microsoft redirect')
        params = parse_qs(parsed.query, keep_blank_values=True)
        if len(params.get('state', [])) != 1 or not secrets.compare_digest(params['state'][0], self._state):
            raise ValueError('Login state mismatch')
        if 'error' in params:
            self._used = True
            raise ValueError('Microsoft authorization was declined or failed')
        if len(params.get('code', [])) != 1 or not params['code'][0]:
            raise ValueError('Missing authorization code')
        self._used = True
        payload = urlencode({'client_id': CLIENT_ID, 'grant_type': 'authorization_code',
            'redirect_uri': REDIRECT, 'code': params['code'][0],
            'code_verifier': self._verifier, 'scope': self.scope}).encode()
        self._verifier = ''
        if transport is None:
            request = Request(TOKEN_URL, data=payload, method='POST',
                headers={'Content-Type':'application/x-www-form-urlencoded'})
            with build_opener(NoRedirects()).open(request, timeout=20) as response:
                raw = response.read(1024*1024+1)
                if len(raw)>1024*1024:
                    raise ValueError('Token response exceeds size limit')
                result = json.loads(raw)
        else:
            result = transport(TOKEN_URL, payload)
        if not isinstance(result,dict) or not isinstance(result.get('access_token'),str) or not result['access_token']:
            raise ValueError('Microsoft did not issue an access token')
        result['obtained_at']=time.time()
        return result
