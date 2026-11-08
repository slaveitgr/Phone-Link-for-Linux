"""Recover embedded Protobuf descriptors from REA's observed ldstr literals."""
import base64
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent

def varint(data, offset):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError('Truncated varint')
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError('Oversized varint')

def fields(data):
    offset = 0
    result = []
    while offset < len(data):
        key, offset = varint(data, offset)
        number, wire = key >> 3, key & 7
        if not number:
            raise ValueError('Invalid field zero')
        if wire == 0:
            value, offset = varint(data, offset)
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value = data[offset:offset + size]
            offset += size
            if len(value) != size:
                raise ValueError('Truncated fixed field')
        elif wire == 2:
            size, offset = varint(data, offset)
            value = data[offset:offset + size]
            offset += size
            if len(value) != size:
                raise ValueError('Truncated length field')
        else:
            raise ValueError('Unsupported wire type')
        result.append((number, value))
    return result

def one(rows, number, default=None):
    return next((v for n, v in rows if n == number), default)

def text(rows, number):
    return one(rows, number, b'').decode('utf-8')

def message(data):
    rows = fields(data)
    return {'name': text(rows, 1), 'fields': [
        {'name': text(f, 1), 'number': one(f, 3), 'label': one(f, 4),
         'type': one(f, 5), 'type_name': text(f, 6)}
        for n, raw in rows if n == 2 for f in [fields(raw)]],
        'messages': [message(raw) for n, raw in rows if n == 3]}

def recover():
    evidence = json.loads((ROOT / 'managed-evidence.json').read_text())
    destination = ROOT / 'recovered-protocols'
    destination.mkdir(exist_ok=True)
    recovered = []
    for component in ('onboarding', 'connectivity'):
        record = evidence[component]
        literals = record['normalized_result']['page']['rows']
        chunks = []
        for row in literals:
            value = row['value']
            if len(value) >= 50 and re.fullmatch(r'[A-Za-z0-9+/=]+', value):
                chunks.append(value)
            elif chunks:
                break
        raw = base64.b64decode(''.join(chunks), validate=True)
        descriptor = fields(raw)
        name = text(descriptor, 1)
        assert name.endswith('.proto')
        item = {'source_evidence': record['evidence_id'], 'name': name,
                'package': text(descriptor, 2),
                'messages': [message(v) for n, v in descriptor if n == 4]}
        (destination / (component + '.descriptor.pb')).write_bytes(raw)
        (destination / (component + '.json')).write_text(json.dumps(item, indent=2) + '\n')
        recovered.append(item)
    return recovered

if __name__ == '__main__':
    print(json.dumps(recover(), indent=2))
