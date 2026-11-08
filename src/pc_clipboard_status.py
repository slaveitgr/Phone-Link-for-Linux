"""Read-only response to a phone's modern PC clipboard STATUS request.

The Linux app currently implements manual legacy text transfer, not the modern
WEA automatic clipboard feature. Report FEATURE_OFF honestly. Never read or
change either clipboard, feature switch, permission, or any saved account.
Caller verifies paired sender and wraps the returned inner response in its
existing correlated DeviceResourceManagerResponseMessage (GET response_type1).
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'generated'))
from google.protobuf.message import DecodeError
from clipboard.v1.clipboard_pb2 import ClipboardRequestMessage,ClipboardResponseMessage

EVIDENCE = {
    'request_builder':'ev_485389c19cc6cad4dcf27966fca0b56bacf2415534c2924e7f288981edd27580',
    'request_send':'ev_f4b49971d493b1fc267c39c9d39631f4b4a324a435727ac880bce0099f8695bc',
    'status_result':'ev_996e8b140fa56809acdaf40420871edfc2d276ed38abb0c6c532f697ee473336',
    'off_mapping':'ev_0feaaae612d7fdbbb5c2c48256ef6c26514fe85f81d7b2929432fd6a64148879',
}
RESOURCE_PATH='/clipboard'
STATUS_REQUEST=5
FEATURE_OFF=9


def build_status_response(payload,*,request_type=1):
    """Return bytes only for valid modern GET STATUS5; otherwise None.

    Do not route the separate legacy `/clipboard` plane0 ValueSet through here.
    This helper is only for the inner modern DRM `/clipboard` plane1 resource.
    """
    if request_type!=1 or not isinstance(payload,bytes) or len(payload)>4096:return None
    try:request=ClipboardRequestMessage.FromString(payload)
    except DecodeError:return None
    if request.request_type!=STATUS_REQUEST or len(request.correlation_id)>500:return None
    return ClipboardResponseMessage(status=FEATURE_OFF,correlation_id=request.correlation_id).SerializeToString()
