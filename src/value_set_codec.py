"""Encoding using the schemas embedded in the supplied Phone Link APK."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'generated'))
from value_set.valueset_pb2 import ValueSet

def value_set(values):
    result=ValueSet()
    for key,value in values.items():
        item=result.entries[key]
        if isinstance(value,bool):item.value_type=11;item.bool_value=value
        elif isinstance(value,str):item.value_type=12;item.string_value=value
        elif isinstance(value,float):item.value_type=9;item.double_value=value
        elif isinstance(value,int):item.value_type=4;item.int32_value=value
        elif isinstance(value,dict):item.value_type=17;item.object_value.CopyFrom(value_set(value))
        elif isinstance(value,list) and all(isinstance(v,str) for v in value):
            item.value_type=29;item.string_array.extend(value)
        else:raise TypeError('Unsupported ValueSet entry')
    return result

def connection_configuration(correlation,installation_id=None,*,remote_lock=False):
    return value_set({'contentType':'connect','correlationVector':correlation,
        'displayName':'Ubuntu desktop','appVersion':'1.26101.114.0',
        'installationId':installation_id or correlation,'contractVersion':3.99,
        'sequenceNumbers':{},'configuration':{'SequencedContentSyncs':False,
            'BatteryIndicator':True,'DeviceIndicators':True,'DeviceIndicatorsBluetooth':True,
            'DeviceIndicatorsDND':True,'DeviceIndicatorsVolume':True,
            'ContentTransferCopyPaste':True,**({'RemoteControlPhoneToPc':True} if remote_lock else {})},
        'attributes':{'displayName':'Ubuntu desktop','appVersion':'1.26101.114.0','flightRing':'Public'}})

def clipboard_request(text,correlation,installation_id=None):
    if not isinstance(text,str) or len(text.encode())>65536:raise ValueError('Clipboard text exceeds limit')
    return value_set({'contentType':'PCPhoneCopy','correlationVector':correlation,
        'displayName':'Ubuntu desktop','appVersion':'1.26101.114.0',
        'installationId':installation_id or correlation,
        'contractVersion':3.99,'isuserinitiated':True,'mimetypes':['text/plain'],'data':[text]})
