import unittest
from relay_protocol import frame,SignalRDecoder,drm_encode,drm_decode
class RelayFramingTests(unittest.TestCase):
    def test_fragmented_and_concatenated_hub_frames(self):
        first=[1,{},'1','SendConnectedAsync',[{},'offline-partner',{}],[]]
        raw=frame(first)+frame([6]);decoder=SignalRDecoder()
        decoded=[]
        for b in raw:decoded+=decoder.feed(bytes([b]))
        self.assertEqual(decoded,[first,[6]])
    def test_counted_drm_preserves_binary_payload(self):
        headers={'_route':'/test','ms-content-type':'application/x-binary'}
        body=b'\x00\xff\x01'
        self.assertEqual(drm_decode(drm_encode(headers,body)),(headers,body))
    def test_truncated_and_oversized_wire_rejected(self):
        raw=drm_encode({'_route':'/test'},b'ab')
        for cut in range(len(raw)):
            with self.assertRaises(ValueError):drm_decode(raw[:cut])
        with self.assertRaises(ValueError):SignalRDecoder().feed(b'\xff\xff\xff\xff\x7f')
class AndroidHeaderCompatibilityTests(unittest.TestCase):
    def test_android_header_length_excludes_pair_counter(self):
        import struct
        raw=bytearray(drm_encode({'_route':'/DeviceResourceManager'},b'\x10\x01'))
        declared=struct.unpack_from('<I',raw,1)[0]
        struct.pack_into('<I',raw,1,declared-4)
        self.assertEqual(drm_decode(raw),({'_route':'/DeviceResourceManager'},b'\x10\x01'))

    def test_arbitrary_header_length_difference_is_rejected(self):
        import struct
        raw=bytearray(drm_encode({'_route':'/test'},b'x'))
        declared=struct.unpack_from('<I',raw,1)[0]
        struct.pack_into('<I',raw,1,declared-1)
        with self.assertRaises(ValueError):drm_decode(raw)

class FragmentCoordinatesTests(unittest.TestCase):
    def test_first_fragment_is_one_as_in_shipped_producer(self):
        from relay_protocol import dcg_fragment
        fragment=dcg_fragment(b'fixture','offline-session',1)
        self.assertEqual(fragment['Properties']['FragmentId'],1)
        with self.assertRaises(ValueError):dcg_fragment(b'fixture','offline-session',1,fragment_id=0)

class FragmentAssemblyTests(unittest.TestCase):
    def test_out_of_order_and_duplicate_phone_fragments(self):
        from relay_protocol import FragmentAssembler
        assembler=FragmentAssembler()
        meta={'SessionId':'offline-session','MessageId':1,'MessageType':0,'FragmentCount':2}
        self.assertIsNone(assembler.add(dict(meta,FragmentId=2),b'world'))
        self.assertIsNone(assembler.add(dict(meta,FragmentId=2),b'world'))
        self.assertEqual(assembler.add(dict(meta,FragmentId=1),b'hello '),b'hello world')

    def test_conflicting_duplicate_is_rejected(self):
        from relay_protocol import FragmentAssembler
        assembler=FragmentAssembler()
        meta={'SessionId':'offline-session','MessageId':1,'MessageType':0,'FragmentCount':2,'FragmentId':1}
        assembler.add(meta,b'first')
        with self.assertRaises(ValueError):assembler.add(meta,b'different')

if __name__=='__main__':unittest.main()
