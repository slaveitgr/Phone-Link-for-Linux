"""Account-scoped enrollment and QR session creation; no I/O on import."""
from device_service import DeviceService
from pairing_service import PairingService
from account_store import serialize_identity


def prepare_pairing(account, identity, persist, *, region=None,
                    display_name='Linux desktop', transport=None):
    """Resume saved work. Persist enrollment before attempting session creation.

    Caller must provide fresh user-authorized MSA/device tokens. The server,
    never this client, issues pairingLink and pairingSessionId.
    """
    options = {} if transport is None else {'transport': transport}
    def save():
        if not persist(account):
            raise RuntimeError('Secure pairing persistence failed')
    if not account.get('enrollment'):
        response, trust = DeviceService(
            lambda: account['msa']['access_token'],
            lambda: account['device_auth']['accessToken'], **options
        ).enroll(identity.client_id, display_name=display_name)
        account['enrollment'] = response
        account['trust'] = serialize_identity(trust)
        save()
    session = account.get('pairing_session')
    if session and not any(word in session.get('state', '')
                           for word in ('FAILED', 'MISMATCHED', 'CANCELLED', 'EXPIRED')):
        return session
    session = PairingService(lambda: account['msa']['access_token'], '3.0.0',
                             region=region, **options).create_session({
        'flow': 'QRLINK_CHALLENGEPIN_SIGNIN', 'optionalPermission': ['ALL']})
    if (not isinstance(session, dict) or not session.get('pairingSessionId')
            or not session.get('pairingLink')):
        raise ValueError('Pairing service returned no session or QR link')
    account['pairing_session'] = session
    save()
    return session
