import subprocess,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from phone_streaming import PhoneStreaming

class StreamingTests(unittest.TestCase):
    def test_requires_explicit_request(self):
        with patch('phone_streaming.subprocess.Popen') as launch:
            with self.assertRaises(PermissionError):PhoneStreaming().start()
            launch.assert_not_called()
    def test_rejects_shell_like_package(self):
        with self.assertRaises(ValueError):PhoneStreaming().start(package='com.example;bad',user_initiated=True)
    def test_early_failure_is_not_reported_running(self):
        process=MagicMock();process.wait.return_value=1
        with patch('phone_streaming._selected_android',return_value=('wifi-test:5555',None)),patch('phone_streaming.find_scrcpy',return_value=Path('/nonexistent/scrcpy')),patch('phone_streaming.subprocess.Popen',return_value=process):
            self.assertEqual(PhoneStreaming().start(user_initiated=True)['status'],'stream_start_failed')
    def test_running_app_uses_wifi_and_separate_display(self):
        process=MagicMock();process.wait.side_effect=subprocess.TimeoutExpired('scrcpy',.8)
        with patch('phone_streaming._selected_android',return_value=('wifi-test:5555',None)),patch('phone_streaming.find_scrcpy',return_value=Path('/nonexistent/scrcpy')),patch('phone_streaming.subprocess.Popen',return_value=process) as launch:
            result=PhoneStreaming().start(package='com.example.app',user_initiated=True)
            self.assertEqual(result['status'],'running')
            command=launch.call_args.args[0]
            self.assertIn('wifi-test:5555',command)
            self.assertIn('--new-display=1080x1920/420',command)
            self.assertIn('--no-audio',command)
            self.assertNotIn('--turn-screen-off',command)
