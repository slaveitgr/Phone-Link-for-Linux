"""Read-only native PhoneFiles wire helpers. No device access on import.

Caller verifies paired sender and DRM correlation. All returned phone metadata
and thumbnail bytes belong in RAM, never in logs or public status.json.
"""
import sys,uuid,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'generated'))
from phone_files.v1.get_pb2 import FilesGetRequest,FilesGetResponse
from phone_files.v1.response_payload_pb2 import FilesResponsePayload
from platform_sdk.v1.device_resource_manager_pb2 import DeviceResourceManagerMessage
from platform_sdk.v1.msaep_message_pb2 import MsaepMessage
from platform_sdk.v1.pub_sub_payload_pb2 import PubSubPayload

RESOURCE_PATH='/filesmetadata' # wifi-files-resource-path.json, shipped APK getResourcePath
MAX_FILES=20000
MAX_RESPONSE_BYTES=16*1024*1024
MAX_THUMBNAIL_BYTES=1024*1024
_STATUS={1:'ok',2:'need_permissions',3:'not_found',4:'checksum_mismatch',5:'io_error',6:'not_supported',7:'request_not_set',8:'feature_disabled',9:'platform_error',10:'cancelled',11:'sync_failed',12:'batch_restart_required',13:'directory_not_empty'}

def _wrap(body):
    if RESOURCE_PATH is None:raise RuntimeError('PhoneFiles route evidence is not finalized')
    return DeviceResourceManagerMessage(request_type=1,resource_path=RESOURCE_PATH,payload=body.SerializeToString()).SerializeToString()

def metadata_request(*,continuation='',request_id=None):
    if not isinstance(continuation,str) or len(continuation)>16384:raise ValueError('Invalid metadata cursor')
    body=FilesGetRequest(request_id=request_id or str(uuid.uuid4()))
    request=body.files_metadata_sync_request
    request.sync_type=1
    request.is_user_initiated=True
    request.supports_batched_response=True
    if continuation:request.batch_continuation_token=continuation
    return _wrap(body)

def thumbnail_request(metadata,*,width=256,height=256,request_id=None):
    uri=metadata.get('uri');checksum=metadata.get('checksum')
    if not isinstance(uri,str) or not uri or len(uri)>8192:raise ValueError('Invalid phone file URI')
    try:checksum=int(checksum)
    except (ValueError,TypeError):raise ValueError('Invalid file checksum')
    if not -(2**63)<=checksum<2**63:raise ValueError('Invalid file checksum')
    if type(width) is not int or type(height) is not int or not 16<=width<=1024 or not 16<=height<=1024:raise ValueError('Invalid thumbnail dimensions')
    identifier=request_id or str(uuid.uuid4())
    body=FilesGetRequest(request_id=identifier)
    body.thumbnail_request.target_uri=uri
    body.thumbnail_request.target_checksum=checksum
    body.thumbnail_request.width=width
    body.thumbnail_request.height=height
    body.thumbnail_request.request_id=identifier
    return _wrap(body)

def _metadata(item):
    result={'id':str(item.id),'uri':item.uri[:8192],'name':item.name[:1000],'path':item.path[:8192],
        'file_type':item.file_type,'size':item.size,'checksum':str(item.checksum),'is_directory':item.is_directory}
    for source,key in [('created_time','created_at'),('modified_time','modified_at')]:
        if item.HasField(source):
            try:result[key]=getattr(item,source).ToJsonString()
            except (ValueError,OverflowError):pass
    return result

def parse_get_response(payload,*,expected_request_id=None):
    if not isinstance(payload,bytes) or len(payload)>MAX_RESPONSE_BYTES:raise ValueError('Invalid PhoneFiles response size')
    body=FilesGetResponse.FromString(payload)
    if expected_request_id and body.request_id and body.request_id!=expected_request_id:raise ValueError('PhoneFiles response ID mismatch')
    result={'status':_STATUS.get(body.status,'unknown'),'request_id':body.request_id,'outer_status':body.status,'wire_kind':body.WhichOneof('response')}
    if body.HasField('thumbnail_response'):
        result.update(nested_status=body.thumbnail_response.status,thumbnail_bytes=len(body.thumbnail_response.thumbnail),has_metadata=body.thumbnail_response.HasField('metadata'))
    if body.status!=1:return result
    kind=body.WhichOneof('response');result['kind']=kind
    if kind=='files_metadata_sync_response':
        sync=body.files_metadata_sync_response
        if sync.WhichOneof('payload')=='full_sync':
            full=sync.full_sync
            if len(full.metadata)>MAX_FILES:raise ValueError('PhoneFiles record limit exceeded')
            result.update(files=[_metadata(x) for x in full.metadata],has_more=full.has_more_batches,
                continuation=full.batch_continuation_token,ending_sequence=full.ending_sequence_number,
                max_capacity_reached=full.full_sync_max_capacity_reached)
            if result['has_more'] and not result['continuation']:raise ValueError('PhoneFiles batch lacks cursor')
        else:result.update(status='unexpected_incremental_response',files=[])
    elif kind=='thumbnail_response':
        thumb=body.thumbnail_response
        # Native FilesThumbnailRequestHandler.successResponse sets outer SUCCESS,
        # bytes and metadata, but deliberately leaves nested status UNSPECIFIED0.
        # Preserve explicit nested error statuses; outer SUCCESS plus validated
        # image bytes is authoritative for the native success response.
        result['status']='ok' if thumb.status in (0,1) else _STATUS.get(thumb.status,'unknown')
        if thumb.status not in (0,1):return result
        image=thumb.thumbnail
        if not image or len(image)>MAX_THUMBNAIL_BYTES:raise ValueError('Invalid thumbnail image size')
        if image.startswith(b'\xff\xd8\xff'):mime='image/jpeg'
        elif image.startswith(b'\x89PNG\r\n\x1a\n'):mime='image/png'
        elif image.startswith(b'RIFF') and image[8:12]==b'WEBP':mime='image/webp'
        else:raise ValueError('Unsupported thumbnail image')
        result.update(metadata=_metadata(thumb.metadata),mime=mime,data_url='data:'+mime+';base64,'+base64.b64encode(image).decode())
    return result

def parse_configuration_publication(payload):
    """Incoming Msaep tag4 -> PubSub -> FilesResponsePayload, no phone writes."""
    if not isinstance(payload,bytes) or len(payload)>MAX_RESPONSE_BYTES:raise ValueError('Invalid PhoneFiles publication size')
    message=MsaepMessage.FromString(payload)
    if message.message_tag!=4:return None
    pubsub=PubSubPayload.FromString(message.payload)
    data=FilesResponsePayload.FromString(pubsub.data)
    kind=data.WhichOneof('payload')
    if kind=='file_configuration':
        config=data.file_configuration
        return {'kind':'configuration','capable':config.capability,'permission':config.permission,
            'request_over_nano_capable':config.is_files_request_over_nano_capable,
            'thumbnail_types':list(config.thumbnail_supported_file_types)}
    if kind=='storage_info':return {'kind':'storage_info','available_bytes':data.storage_info.available_size_bytes,'total_bytes':data.storage_info.total_size_bytes}
    if kind=='file_sync_update':return {'kind':'sync_update','sync_type':data.file_sync_update.sync_type,'sequence':data.file_sync_update.seq_num}
    return None
