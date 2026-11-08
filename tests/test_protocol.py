import unittest
from phonelink_protocol import encode_onboarding, decode_onboarding, encode_valueset, decode_valueset

class ProtocolTests(unittest.TestCase):
    def test_known_onboarding_wire_vector(self):
        # Independently specified protobuf: field1, length13, UTF-8 device name.
        vector = b'\x0a\x0dPOCO F8 Ultra'
        self.assertEqual(encode_onboarding('POCO F8 Ultra'), vector)
        self.assertEqual(decode_onboarding(vector), 'POCO F8 Ultra')

    def test_native_valueset_string_vector(self):
        # ValueSet entries -> key='a', DataVariant type12/string field13='b'.
        vector = bytes.fromhex('0a0a0a01611205080c6a0162')
        self.assertEqual(encode_valueset({'a':'b'}), vector)
        self.assertEqual(decode_valueset(vector), {'a':'b'})

    def test_signed_and_boolean_boundaries(self):
        values = {'minimum': -(2**31), 'maximum': 2**31-1, 'enabled': True, 'off': False}
        self.assertEqual(decode_valueset(encode_valueset(values)), values)

    def test_truncated_wire_rejected(self):
        with self.assertRaises(ValueError):
            decode_onboarding(b'\x0a\x20short')

if __name__ == '__main__':
    unittest.main()
