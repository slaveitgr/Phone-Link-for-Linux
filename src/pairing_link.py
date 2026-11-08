"""The Android pairing-link parser, reconstructed from the observed Java method.

Parsing a link does not authenticate or connect a device. Links must originate
from a verified pairing-service response before being offered to the user.
"""
from dataclasses import dataclass
import re
from urllib.parse import unquote_plus, urlsplit, parse_qs

@dataclass(frozen=True)
class PairingLink:
    session_id: str
    region: str
    visit_mode: str
    trace_id: str

def parse_pairing_link(value):
    if not isinstance(value, str):
        raise TypeError('Expected a pairing link string')
    if len(value) > 16384:
        raise ValueError('Pairing link too long')
    if re.search(r'%(?![0-9a-fA-F]{2})', value):
        raise ValueError('Malformed percent escape')
    decoded = unquote_plus(value, encoding='utf-8', errors='replace')
    values = parse_qs(urlsplit(decoded).query, keep_blank_values=True)
    def first(name):
        return values.get(name, [''])[0]
    return PairingLink(first('cpsi'), first('r'), first('vm'), first('ti'))
