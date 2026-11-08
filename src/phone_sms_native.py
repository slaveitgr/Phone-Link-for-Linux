"""Bounded, read-only native SMS sync helpers for the paired legacy channel.

No transport, persistence, SMS sending or read-flag changes. Callers must verify
that the incoming sender is the paired phone before decoding records.
The static APK evidence is indexed in sms-native-findings.json.
"""
from value_set_codec import value_set

ROUTE='/legacy/phonecontent'
PLANE=0
MAX_MESSAGES=50
MAX_WIRE_BYTES=4*1024*1024
MAX_METADATA_IDS=100000


def _request(correlation,installation_id,request_type):
    if not isinstance(correlation,str) or not 1<=len(correlation)<=256:raise ValueError('Invalid correlation')
    if not isinstance(installation_id,str) or not 1<=len(installation_id)<=256:raise ValueError('Invalid installation')
    return value_set({'contentType':'messaging','subcontentTypes':['messages'],
        'correlationVector':correlation,'installationId':installation_id,
        'displayName':'Ubuntu desktop','appVersion':'1.26101.114.0',
        'contractVersion':3.99,'isuserinitiated':True,'requestType':request_type})


def metadata_request(correlation,installation_id):
    """Request only SMS ID/checksum metadata, not MMS, RCS or message bodies."""
    return _request(correlation,installation_id,0)


def content_request(correlation,installation_id,identifiers):
    """Read at most 50 SMS IDs previously obtained from trusted phone metadata."""
    if not isinstance(identifiers,(list,tuple)) or not 1<=len(identifiers)<=MAX_MESSAGES:raise ValueError('Invalid SMS ID count')
    if any(type(x) is not int or not 0<=x<2**63 for x in identifiers):raise ValueError('Invalid SMS ID')
    if len(set(identifiers))!=len(identifiers):raise ValueError('Duplicate SMS ID')
    request=_request(correlation,installation_id,1)
    item=request.entries['messagingSmsIds'];item.value_type=23;item.int64_array.extend(identifiers)
    return request


def parse_metadata(values,limit=MAX_MESSAGES):
    """Return bounded known IDs; None means this is not an SMS metadata payload.

    Highest numeric IDs are selected to bound the body request, but ID order is
    not claimed to be a message timestamp. UI must sort actual record dates.
    """
    if type(limit) is not int or not 1<=limit<=MAX_MESSAGES:raise ValueError('Invalid SMS limit')
    if values.ByteSize()>MAX_WIRE_BYTES:raise ValueError('SMS payload size exceeded')
    if 'messagingSmsIds' not in values.entries:return None
    field=values.entries['messagingSmsIds']
    if field.value_type!=23 or len(field.int64_array)>MAX_METADATA_IDS:raise ValueError('Invalid SMS metadata array')
    identifiers=list(field.int64_array)
    if any(x<0 for x in identifiers):raise ValueError('Invalid SMS metadata ID')
    known=sorted(set(identifiers),reverse=True)[:limit]
    return {'ids':known,'total_count':len(identifiers),'source':'native_relay'}
