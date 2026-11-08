import unittest
from value_set_codec import connection_configuration,clipboard_request
class ConfigurationTests(unittest.TestCase):
    def test_connect_schema_and_explicit_supported_features(self):
        values=connection_configuration('offline-correlation')
        self.assertEqual(values.entries['contentType'].string_value,'connect')
        config=values.entries['configuration'].object_value.entries
        self.assertTrue(config['ContentTransferCopyPaste'].bool_value)
        self.assertTrue(config['BatteryIndicator'].bool_value)
        self.assertFalse(config['SequencedContentSyncs'].bool_value)
        self.assertNotIn('RemoteControlPhoneToPc',config)
    def test_clipboard_format_and_size_limit(self):
        values=clipboard_request('offline fixture text','fixture')
        self.assertEqual(values.entries['data'].string_array[0],'offline fixture text')
        self.assertEqual(values.entries['mimetypes'].string_array[0],'text/plain')
        self.assertEqual(values.entries['contractVersion'].double_value,3.99)
        with self.assertRaises(ValueError):clipboard_request('x'*65537,'fixture')
if __name__=='__main__':unittest.main()
