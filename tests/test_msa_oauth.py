import unittest
from urllib.parse import parse_qs,urlsplit,urlencode
from msa_oauth import MsaLogin,REDIRECT,TOKEN_URL

class MsaLoginTests(unittest.TestCase):
    def test_pkce_exchange_and_single_use(self):
        login=MsaLogin();query=parse_qs(urlsplit(login.authorization_url()).query)
        self.assertEqual(query['code_challenge_method'],['S256'])
        callback=REDIRECT+'?'+urlencode({'state':query['state'][0],'code':'offline-test-code'})
        calls=[]
        def transport(url,body):
            calls.append((url,parse_qs(body.decode())))
            return {'access_token':'offline-test-token'}
        self.assertEqual(login.exchange_callback(callback,transport=transport)['access_token'],'offline-test-token')
        self.assertEqual(calls[0][0],TOKEN_URL)
        self.assertIn('code_verifier',calls[0][1])
        with self.assertRaises(ValueError):login.exchange_callback(callback,transport=transport)

    def test_wrong_origin_and_state_never_exchange(self):
        login=MsaLogin()
        def unexpected(*args):self.fail('Unexpected token request')
        for callback in ['https://example.com/?code=x&state=x',REDIRECT+'?code=x&state=x']:
            with self.assertRaises(ValueError):login.exchange_callback(callback,transport=unexpected)

    def test_attempts_have_independent_state_and_pkce(self):
        a=parse_qs(urlsplit(MsaLogin().authorization_url()).query)
        b=parse_qs(urlsplit(MsaLogin().authorization_url()).query)
        self.assertNotEqual(a['state'],b['state'])
        self.assertNotEqual(a['code_challenge'],b['code_challenge'])

class RefreshTests(unittest.TestCase):
    def test_refresh_preserves_token_when_server_does_not_rotate(self):
        from msa_oauth import refresh_tokens
        result=refresh_tokens({'refresh_token':'offline-refresh'},
            transport=lambda url,body:{'access_token':'offline-access','expires_in':3600})
        self.assertEqual(result['refresh_token'],'offline-refresh')
        self.assertGreater(result['obtained_at'],0)

    def test_refresh_uses_replacement_from_server(self):
        from msa_oauth import refresh_tokens
        result=refresh_tokens({'refresh_token':'old-offline-refresh'},
            transport=lambda url,body:{'access_token':'offline-access','refresh_token':'new-offline-refresh'})
        self.assertEqual(result['refresh_token'],'new-offline-refresh')

if __name__=='__main__':unittest.main()
