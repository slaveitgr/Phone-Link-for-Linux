"""Validate the native phone's Mirror to PC launch trigger.

This recognizes a user launch request, not the Microsoft screen-video handshake.
Caller must restrict the route to PL /legacy/phonecontent and only start its
local receiver after successful paired-peer validation. Never execute the URI.
"""
from urllib.parse import urlsplit,parse_qs
from uuid import UUID


def is_phone_screen_trigger(values,*,sender,paired_partner):
    if not paired_partner or sender!=paired_partner:return False
    def scalar(key,kind,field):
        item=values.entries.get(key)
        return getattr(item,field) if item is not None and item.value_type==kind else None
    if scalar('contentType',12,'string_value')!='phoneCommand':return False
    if scalar('phoneCommandType',4,'int32_value')!=1:return False
    uri=scalar('launchURI',12,'string_value')
    if not isinstance(uri,str) or len(uri)>2048:return False
    try:
        parsed=urlsplit(uri)
        # Native Uri.Builder output has every '/' removed before sending.
        if parsed.scheme!='ms-phone' or parsed.netloc or parsed.path!='remoting' or parsed.fragment:return False
        query=parse_qs(parsed.query,strict_parsing=True,max_num_fields=8)
        if query.get('packagename')!=['yourphone.phonescreen']:return False
        if any(len(v)!=1 for v in query.values()):return False
        if set(query)-{'packagename','launchsource','cid'}:return False
        cid=query.get('cid')
        if cid is None or len(cid)!=1:return False
        UUID(cid[0])
    except (ValueError,TypeError):return False
    return True


def trigger_result(success):
    """Native Windows ProcessItem reply: Int32 result 0 accepted, 1 invalid.

    This is a legacy ValueSet item payload, not a DRM response wrapper.
    Caller supplies its existing native legacy reply framing/correlation.
    """
    from value_set_codec import value_set
    return value_set({'result':0 if success is True else 1})
