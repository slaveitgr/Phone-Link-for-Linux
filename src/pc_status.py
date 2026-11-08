"""Read real local hardware state; protocol encoding is based on shipped APK evidence."""
from pathlib import Path
import subprocess


def read_local_status(power_supply=Path('/sys/class/power_supply')):
    """Missing battery remains unknown rather than reporting a fabricated percentage."""
    result={}
    for battery in sorted(Path(power_supply).glob('*')):
        try:
            if (battery/'type').read_text().strip()!='Battery':continue
            percent=int((battery/'capacity').read_text().strip())
            state=(battery/'status').read_text().strip()
            if not 0<=percent<=100:continue
            result.update(battery_percent=percent,battery_charging=state=='Charging')
            break
        except (OSError,ValueError):continue
    try:
        output=subprocess.run(['nmcli','-t','-f','TYPE,STATE','device'],
            capture_output=True,text=True,timeout=3,check=True).stdout
        result['wifi_connected']=any(line=='wifi:connected' for line in output.splitlines())
        result['ethernet_connected']=any(line=='ethernet:connected' for line in output.splitlines())
        # Query signal strength without exposing or persisting network names.
        signals=subprocess.run(['nmcli','-t','-f','IN-USE,SIGNAL','device','wifi','list','--rescan','no'],
            capture_output=True,text=True,timeout=3,check=True).stdout
        for line in signals.splitlines():
            if line.startswith('*:'):
                signal=int(line.split(':')[1])
                if 0<=signal<=100:result['wifi_signal_percent']=signal
                break
    except (OSError,ValueError,subprocess.SubprocessError):pass
    return result


def build_status_response(local=None):
    """Payload for PLATFORM `/remotedevicestatus` GET response.

    APK RemoteDeviceStatus.Companion.parseFrom directly parses this protobuf.
    Unknown hardware data produces NOT_FOUND, never a fake battery reading.
    Signal bar scaling is intentionally omitted until its range is corroborated.
    """
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parent/'generated'))
    from device_info.v1.status_pb2 import DeviceStatusResponseMessage
    local=read_local_status() if local is None else local
    response=DeviceStatusResponseMessage()
    if 'battery_percent' not in local:
        response.status=4
        return response.SerializeToString()
    response.status=1
    response.info.battery_percent=local['battery_percent']
    response.info.battery_charging=local['battery_charging']
    response.info.network_type=1 if local.get('wifi_connected') else (2 if local.get('ethernet_connected') else 0)
    response.info.wifi_state=bool(local.get('wifi_connected'))
    return response.SerializeToString()


def build_status_publication(client_id, message_id, *, status_response=None):
    """Context status publication: shipped APK tag8, PubSubPayload and Msaep 1.1."""
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parent/'generated'))
    from platform_sdk.v1.pub_sub_payload_pb2 import PubSubPayload
    from platform_sdk.v1.msaep_message_pb2 import MsaepMessage
    body=PubSubPayload(data=build_status_response() if status_response is None else status_response)
    return MsaepMessage(message_tag=8,dcg_client_id=client_id,message_id=message_id,
        payload=body.SerializeToString(),platform_major_version=1,platform_minor_version=1).SerializeToString()
