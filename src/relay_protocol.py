"""Bounded SignalR MessagePack and counted DRM framing for DCG interoperability.

Wire conventions corroborated with ZonD80/msft-phone-link-docs (MIT research).
This module never marks a phone connected and never executes message content.
"""
import struct
import time
import msgpack
MAX_FRAME=16*1024*1024

def dcg_fragment(raw,session_id,sequence,*,plane=0,fragment_id=1,fragment_count=1):
    # Shipped OutgoingMessageFragmenter increments its counter before assigning
    # FragmentId. Zero is transport-acknowledged but never assembled by Android.
    if not 1<=fragment_id<=fragment_count or sequence<1 or plane not in (0,1):
        raise ValueError('Invalid DCG fragment coordinates')
    return {'Type':'ms-dcg','Properties':{'Version':1.0,'Type':2,
        'SessionId':session_id,'SequenceNumber':sequence,'MessageId':sequence,
        'MessageType':plane,'FragmentId':fragment_id,'FragmentCount':fragment_count},'Raw':raw}

class FragmentAssembler:
    def __init__(self):self.pending={}
    def add(self,properties,raw):
        now=time.monotonic()
        self.pending={k:v for k,v in self.pending.items() if now-v['time']<60}
        count=properties.get('FragmentCount',1);index=properties.get('FragmentId',1)
        if int(count)!=count or int(index)!=index or not 1<=index<=count<=256:
            raise ValueError('Invalid incoming fragment coordinates')
        if not isinstance(raw,bytes) or len(raw)>MAX_FRAME:raise ValueError('Invalid fragment payload')
        if count==1:return raw
        key=(str(properties.get('SessionId',''))[:128],properties.get('MessageId'),properties.get('MessageType'))
        if key not in self.pending:
            if len(self.pending)>=32:self.pending.pop(next(iter(self.pending)))
            self.pending[key]={'time':now,'count':count,'parts':{}}
        message=self.pending[key]
        if message['count']!=count:raise ValueError('Fragment count changed')
        old=message['parts'].get(index)
        if old is not None and old!=raw:raise ValueError('Conflicting duplicate fragment')
        message['parts'][index]=raw
        if sum(len(part) for part in message['parts'].values())>MAX_FRAME:
            del self.pending[key];raise ValueError('Assembled payload exceeds limit')
        if len(message['parts'])!=count:return None
        del self.pending[key]
        return b''.join(message['parts'][i] for i in range(1,int(count)+1))

def prefix(size):
    if not 0<=size<=MAX_FRAME:raise ValueError('Frame size exceeds limit')
    result=bytearray()
    while size>=128:result.append((size&127)|128);size>>=7
    result.append(size)
    return bytes(result)

def frame(value):
    raw=msgpack.packb(value,use_bin_type=True)
    return prefix(len(raw))+raw

class SignalRDecoder:
    def __init__(self):self.buffer=bytearray()
    def feed(self,data):
        if len(self.buffer)+len(data)>MAX_FRAME+5:raise ValueError('Receive buffer exceeds limit')
        self.buffer.extend(data);result=[]
        while self.buffer:
            size=0;end=None
            for i,b in enumerate(self.buffer[:5]):
                if i==4 and b>7:raise ValueError('Invalid SignalR length prefix')
                size|=(b&127)<<(i*7)
                if not b&128:end=i+1;break
            if end is None:
                if len(self.buffer)>=5:raise ValueError('Unterminated length prefix')
                break
            if size>MAX_FRAME:raise ValueError('Frame exceeds limit')
            if len(self.buffer)<end+size:break
            value=msgpack.unpackb(bytes(self.buffer[end:end+size]),raw=False,strict_map_key=False)
            del self.buffer[:end+size]
            if not isinstance(value,list) or not value:raise ValueError('Expected hub frame array')
            result.append(value)
        return result

def drm_encode(headers,body):
    pairs=bytearray(struct.pack('<I',len(headers)))
    for key,value in headers.items():
        for text in (key,value):
            raw=text.encode('utf-8');pairs.extend(struct.pack('<I',len(raw)));pairs.extend(raw)
    raw=b'\x01'+struct.pack('<I',len(pairs))+pairs+struct.pack('<Q',len(body))+body
    if len(raw)>MAX_FRAME:raise ValueError('DRM payload exceeds limit')
    return raw

def drm_decode(raw):
    if len(raw)>MAX_FRAME or len(raw)<17 or raw[0]!=1:raise ValueError('Invalid DRM envelope')
    header_size=struct.unpack_from('<I',raw,1)[0]
    boundary=5+header_size
    if boundary+8>len(raw):raise ValueError('Invalid DRM header boundary')
    count=struct.unpack_from('<I',raw,5)[0]
    if count>1024:raise ValueError('Too many DRM headers')
    offset=9;headers={}
    # Android's observed header count can exclude the four-byte pair counter.
    parse_boundary=min(boundary+4,len(raw)-8)
    for _ in range(count):
        pair=[]
        for __ in range(2):
            if offset+4>parse_boundary:raise ValueError('Truncated DRM header')
            size=struct.unpack_from('<I',raw,offset)[0];offset+=4
            if offset+size>parse_boundary:raise ValueError('Truncated DRM header value')
            pair.append(raw[offset:offset+size].decode('utf-8'));offset+=size
        headers[pair[0]]=pair[1]
    if offset not in (boundary,boundary+4):raise ValueError('DRM header length mismatch')
    body_size=struct.unpack_from('<Q',raw,offset)[0];offset+=8
    if body_size!=len(raw)-offset:raise ValueError('DRM body length mismatch')
    return headers,raw[offset:]
