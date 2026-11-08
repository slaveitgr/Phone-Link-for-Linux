"""Cross-check the portable implementation against the APK's actual schemas."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent / 'generated'))
from fre.v1.proximal_onboarding_message_pb2 import ProximalOnboardingMessage
from value_set.valueset_pb2 import ValueSet, DataVariant
from device_info.v1.status_pb2 import DeviceStatusResponseMessage, DEVICE_STATUS_RESPONSE_STATUS_OK
from phonelink_protocol import encode_onboarding, decode_onboarding, encode_valueset, decode_valueset

class GeneratedProtocolTests(unittest.TestCase):
    def test_onboarding_matches_original_android_schema(self):
        message = ProximalOnboardingMessage(device_name='POCO F8 Ultra')
        self.assertEqual(message.SerializeToString(), encode_onboarding('POCO F8 Ultra'))
        self.assertEqual(decode_onboarding(message.SerializeToString()), message.device_name)

    def test_value_set_matches_original_android_schema(self):
        for value in ('POCO F8 Ultra', '', True, False, 0, -2147483648, 2147483647):
            if isinstance(value, str):
                variant = DataVariant(value_type=12, string_value=value)
            elif isinstance(value, bool):
                variant = DataVariant(value_type=11, bool_value=value)
            else:
                variant = DataVariant(value_type=4, int32_value=value)
            message = ValueSet()
            message.entries['test'].CopyFrom(variant)
            self.assertEqual(message.SerializeToString(), encode_valueset({'test': value}))
            self.assertEqual(decode_valueset(message.SerializeToString()), {'test': value})

    def test_battery_wire_vector_from_schema(self):
        # status=OK; info message: battery_percent=97, battery_charging=true.
        vector = bytes.fromhex('0801120408611001')
        response = DeviceStatusResponseMessage.FromString(vector)
        self.assertEqual(response.status, DEVICE_STATUS_RESPONSE_STATUS_OK)
        self.assertTrue(response.HasField('info'))
        self.assertEqual(response.info.battery_percent, 97)
        self.assertTrue(response.info.battery_charging)

if __name__ == '__main__':
    unittest.main()
