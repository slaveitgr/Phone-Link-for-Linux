import subprocess,tempfile,unittest
from pathlib import Path
from phone_transfer import PhoneTransfer,ROOT

class TransferTests(unittest.TestCase):
    def test_paths_are_confined_to_shared_storage(self):
        for path in ['/data/private','../../data/private','/sdcard/../../data','bad\\x00name'.replace('\\x00','\x00'),'bad\nname']:
            with self.subTest(path=repr(path)),self.assertRaises(ValueError):PhoneTransfer.safe_path(path)
        self.assertEqual(PhoneTransfer.safe_path('/sdcard/DCIM/a.jpg'),ROOT+'/DCIM/a.jpg')
    def test_receive_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            existing=Path(folder)/'a.jpg';existing.write_bytes(b'original')
            client=PhoneTransfer()
            def adb(*args,**kwargs):Path(args[2]).write_bytes(b'download')
            client._adb=adb
            result=client.receive('/sdcard/DCIM/a.jpg',folder)
            self.assertEqual(existing.read_bytes(),b'original')
            self.assertEqual(Path(result['path']).read_bytes(),b'download')
            self.assertEqual(Path(result['path']).stat().st_mode & 0o777,0o600)
            self.assertEqual(list(Path(folder).glob('*.part')),[])
    def test_failed_download_removes_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            client=PhoneTransfer()
            def adb(*args,**kwargs):raise subprocess.CalledProcessError(1,['adb'])
            client._adb=adb
            with self.assertRaises(subprocess.CalledProcessError):client.receive('/sdcard/a.jpg',folder)
            self.assertEqual(list(Path(folder).iterdir()),[])
