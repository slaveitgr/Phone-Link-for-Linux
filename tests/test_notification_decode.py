import sys,json,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'generated'))
from value_set.valueset_pb2 import ValueSet
from notification_decode import notification_records
class NotificationDecodeTests(unittest.TestCase):
    def test_json_array_and_parallel_keys_without_logging_text(self):
        values=ValueSet()
        values.entries['notifications'].value_type=29
        values.entries['notifications'].string_array.append(json.dumps(
            {'appName':'Fixture app','title':'Fixture title','text':'Fixture text'}))
        values.entries['notificationKeys'].value_type=29
        values.entries['notificationKeys'].string_array.append('fixture-key')
        self.assertEqual(notification_records(values),[{'id':'fixture-key','app':'Fixture app',
            'title':'Fixture title','body':'Fixture text'}])
    def test_missing_payload_is_not_empty_sync(self):
        self.assertIsNone(notification_records(ValueSet()))
    def test_invalid_json_is_ignored(self):
        values=ValueSet();values.entries['notifications'].value_type=12
        values.entries['notifications'].string_value='bad-json'
        self.assertIsNone(notification_records(values))
if __name__=='__main__':unittest.main()
