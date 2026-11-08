"""Linux HTTP adapter for observed Phone Link pairing routes.

Authentication bootstrap and user consent remain to be implemented. No account
credentials are read or network calls made merely by importing this module.
"""
import json
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

class AuthenticationRequired(RuntimeError):
    pass

class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward a device identity bearer token to another endpoint.
        return None

def http_transport(method, url, headers, body):
    request = Request(url, data=body, headers=headers, method=method)
    with build_opener(NoRedirects()).open(request, timeout=20) as response:
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Pairing response exceeds size limit')
        return json.loads(raw) if raw else None

class PairingService:
    def __init__(self, authorization_provider, api_version, *,
                 base_url='https://dcg.microsoft.com', transport=http_transport, region=None):
        url = urlsplit(base_url)
        allowed = {'dcg.microsoft.com', 'dcg-beta.microsoft.com', 'dcg-df.microsoft.com'}
        if (url.scheme != 'https' or url.hostname not in allowed or url.port not in (None,443)
                or url.username or url.password or url.query or url.fragment or url.path not in ('','/')):
            raise ValueError('An observed Microsoft HTTPS service origin is required')
        if not re.fullmatch(r'\d+(?:\.\d+){1,3}', api_version):
            raise ValueError('Explicit API version is required')
        self.base_url = base_url.rstrip('/')
        self.api_version = api_version
        self.authorization_provider = authorization_provider
        self.transport = transport
        if region is not None and not re.fullmatch(r'[A-Z]{2}', region):
            raise ValueError('Region must be a two-letter country code')
        self.region = region

    def _request(self, method, session_id=None, action=None, payload=None):
        route = '/DevicePairingProxy/PairingSessions'
        if session_id is not None:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', session_id):
                raise ValueError('Invalid session identifier')
            route += '/' + session_id
        if action:
            route += '/' + action
        token = self.authorization_provider()
        if not isinstance(token, str) or not token or '\r' in token or '\n' in token:
            raise AuthenticationRequired('A valid, user-authorized device identity token is required')
        headers = {'Authorization': 'Bearer ' + token, 'Authorization-Type': 'MSA',
                   'Accept': 'application/json'}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        query = {'Api-Version': self.api_version}
        if self.region and method == 'POST' and session_id is None:
            query['clientRegionName'] = self.region
        url = self.base_url + route + '?' + urlencode(query)
        return self.transport(method, url, headers, body)

    def create_session(self, payload):
        return self._request('POST', payload=payload)

    def get_session(self, session_id):
        return self._request('GET', session_id)

    def refresh_challenge_pin(self, session_id):
        return self._request('POST', session_id, 'RefreshChallengePIN')

    def complete_session(self, session_id, payload=None):
        return self._request('POST', session_id, 'Complete', payload)
