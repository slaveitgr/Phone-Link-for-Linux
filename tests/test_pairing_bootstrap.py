import json
import unittest
from types import SimpleNamespace
from pairing_bootstrap import prepare_pairing

class BootstrapTests(unittest.TestCase):
    def test_first_run_enrolls_saves_then_creates_server_qr(self):
        account={'msa':{'access_token':'fixture-msa'},
                 'device_auth':{'accessToken':'fixture-device'}}
        events=[]
        session={'pairingSessionId':'fixture-session','pairingLink':'https://example.invalid/fixture',
                 'state':'PENDING_PAIRING_LINK_VISIT'}
        def transport(method,url,headers,body):
            events.append(('request',url,json.loads(body)))
            return {'deviceId':'fixture-device'} if 'EnrollDevice?' in url else session.copy()
        def save(value):
            events.append(('save','pairing_session' in value))
            return True
        result=prepare_pairing(account,SimpleNamespace(client_id='fixture'),save,transport=transport)
        self.assertEqual(result,session)
        self.assertEqual([e[0] for e in events],['request','save','request','save'])
        self.assertEqual(events[2][2]['flow'],'QRLINK_CHALLENGEPIN_SIGNIN')
        self.assertIn('trust',account)

    def test_existing_session_needs_no_request(self):
        account={'enrollment':{'deviceId':'fixture'},'pairing_session':{'state':'DEVICE_PAIRED'}}
        self.assertEqual(prepare_pairing(account,None,lambda _:self.fail('save')),
                         account['pairing_session'])

    def test_failed_secure_save_prevents_session_request(self):
        calls=[]
        def transport(*args):calls.append(args);return {'deviceId':'fixture'}
        account={'msa':{'access_token':'fixture'},'device_auth':{'accessToken':'fixture'}}
        with self.assertRaises(RuntimeError):
            prepare_pairing(account,SimpleNamespace(client_id='fixture'),lambda _:False,transport=transport)
        self.assertEqual(len(calls),1)

    def test_incomplete_server_response_not_saved_as_session(self):
        account={'enrollment':{'deviceId':'fixture'},'msa':{'access_token':'fixture'}}
        with self.assertRaises(ValueError):
            prepare_pairing(account,None,lambda _:self.fail('save'),transport=lambda *args:{})
        self.assertNotIn('pairing_session',account)

if __name__=='__main__':unittest.main()
