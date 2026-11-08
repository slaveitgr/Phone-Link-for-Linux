"""Persistence for this application's user-consented connection, in libsecret only."""
import json
from secret_store import SecretStore
from device_identity import DeviceIdentity
from cryptography.hazmat.primitives import serialization

def load_account():
    with SecretStore() as store:
        raw=store.load()
    if not raw:return None
    account=json.loads(raw)
    identity=DeviceIdentity.from_pem(account['client_id'],account['key'],account['certificate'])
    return account,identity

def save_account(account):
    with SecretStore() as store:
        return store.save(json.dumps(account))

def serialize_identity(identity):
    return {'client_id':identity.client_id,
        'key':identity._key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode(),
        'certificate':identity.certificate.public_bytes(serialization.Encoding.PEM).decode()}
