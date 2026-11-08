"""Observed Windows MSA -> device identity bootstrap, with injected consent token.

Static reconstruction only: service acceptance has not been tested. This module
never obtains tokens from other applications or stores credentials/private keys.

Request headers/version: ev_84f044aef0419015bdf97a4a699d1a6454a9c982ad0fb56a59728441ca6811a7.
Request/response models: ev_59254a80a6269db3b0a3186d5bfc82c635a059e6d465a523e230d5c71be3bc3d.
"""
from datetime import datetime, timedelta, timezone
import json
from urllib.parse import urlencode
from pairing_service import PairingService, AuthenticationRequired, http_transport

class IdentityService:
    def __init__(self, msa_token_provider, *, transport=http_transport,
                 base_url='https://dcg.microsoft.com'):
        # Reuse the observed HTTPS origin validation; identity API has its own version.
        validated = PairingService(msa_token_provider, '1.1.0', base_url=base_url)
        self.base_url = validated.base_url
        self.msa_token_provider = msa_token_provider
        self.transport = transport

    def _post(self, action, payload, token):
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json',
                   'UserIdentityType': 'MSA', 'UserIdentityToken': token,
                   'Authorization': 'Bearer ' + token, 'Authorization-Type': 'MSA'}
        return self.transport('POST', self.base_url + '/Auth/' + action + '?' +
                              urlencode({'api-version': '1.1.0'}), headers,
                              json.dumps(payload, separators=(',', ':')).encode())

    def create_identity(self, identity, *, now=None):
        return self._authenticate(identity, action='CreateIdentity', now=now)

    def sign_in(self, identity, *, now=None):
        return self._authenticate(identity, action='SignIn', now=now)

    def _authenticate(self, identity, *, action, now=None):
        token = self.msa_token_provider()
        if not isinstance(token, str) or not token or '\r' in token or '\n' in token:
            raise AuthenticationRequired('User-authorized MSA token required')
        nonce_response = self._post('GenerateNonce', {'deviceId': identity.client_id}, token)
        if not isinstance(nonce_response, dict) or not isinstance(nonce_response.get('nonce'), str) or not nonce_response['nonce']:
            raise ValueError('Identity service did not return a nonce')
        # Observed default JWT expiration/skew: 12 hours; caller may supply time for testing.
        proof = identity.sign_server_nonce(nonce_response['nonce'],
                    now=now or datetime.now(timezone.utc),
                    jwt_validity=timedelta(hours=12), clock_skew=timedelta(hours=12))
        response = self._post(action, {'certificateJWT': proof}, token)
        if not isinstance(response, dict) or not isinstance(response.get('accessToken'), str) or not response['accessToken']:
            raise ValueError('Identity service did not return an access token')
        expiration = response.get('epochExpirationTime')
        if isinstance(expiration, bool) or not isinstance(expiration, (int, float)):
            raise ValueError('Identity service did not return a Unix expiry')
        datetime.fromtimestamp(expiration, timezone.utc)
        return response
