"""Portable subset of the actual Phone Link protobuf wire structures.

Field numbers and enum values were recovered from embedded descriptors.
This implements serialization only, not authenticated phone connectivity.
"""
from recover_protocols import fields, one

def encode_varint(value):
    if not 0 <= value < 2**64:
        raise ValueError('Unsigned 64-bit value required')
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)

def scalar(number, value):
    return encode_varint(number << 3) + encode_varint(value)

def blob(number, value):
    return encode_varint((number << 3) | 2) + encode_varint(len(value)) + value

def encode_onboarding(device_name):
    if not isinstance(device_name, str) or not device_name:
        raise ValueError('A nonempty device name is required')
    return blob(1, device_name.encode('utf-8'))

def decode_onboarding(payload):
    value = one(fields(payload), 1, b'')
    if not isinstance(value, bytes):
        raise ValueError('Invalid device name wire type')
    return value.decode('utf-8')

def encode_valueset(values):
    result = bytearray()
    for key, value in values.items():
        if not isinstance(key, str):
            raise TypeError('ValueSet keys must be strings')
        if isinstance(value, bool):
            variant = scalar(1, 11) + (scalar(12, 1) if value else b'')
        elif isinstance(value, str):
            variant = scalar(1, 12) + (blob(13, value.encode('utf-8')) if value else b'')
        elif isinstance(value, int) and -(2**31) <= value < 2**31:
            variant = scalar(1, 4) + (scalar(5, value & (2**64 - 1)) if value else b'')
        else:
            raise TypeError('Only descriptor-verified bool, string and int32 supported')
        result.extend(blob(1, blob(1, key.encode('utf-8')) + blob(2, variant)))
    return bytes(result)

def decode_valueset(payload):
    result = {}
    for number, entry in fields(payload):
        if number != 1:
            continue
        row = fields(entry)
        key = one(row, 1, b'').decode('utf-8')
        variant = fields(one(row, 2, b''))
        kind = one(variant, 1, 0)
        if kind == 11:
            value = bool(one(variant, 12, 0))
        elif kind == 12:
            value = one(variant, 13, b'').decode('utf-8')
        elif kind == 4:
            value = one(variant, 5, 0) & 0xffffffff
            if value >= 2**31:
                value -= 2**32
        else:
            raise NotImplementedError(f'Unsupported DataValueType {kind}')
        result[key] = value
    return result
