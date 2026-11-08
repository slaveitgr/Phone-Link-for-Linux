"""Phone-owned wallpaper protocol; no phone reads or writes happen on import.

Route/protobuf from supplied Link to Windows APK, wallpaper-resource-*.json.
Only a received homescreen image is cached, in the app's private state directory.
"""
import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'generated'))
from platform_sdk.v1.device_resource_manager_pb2 import DeviceResourceManagerMessage
from device_info.v1.wallpaper_pb2 import WallpaperRequestMessage,WallpaperResponseMessage

RESOURCE_PATH='/wallpaper'
MAX_IMAGE_BYTES=16*1024*1024

def wallpaper_request():
    """PLATFORM plane1 request payload; empty versions asks for current images."""
    return DeviceResourceManagerMessage(request_type=1,resource_path=RESOURCE_PATH,
        payload=WallpaperRequestMessage().SerializeToString()).SerializeToString()

def image_format(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):return 'png','image/png'
    if data.startswith(b'\xff\xd8\xff'):return 'jpg','image/jpeg'
    if data.startswith(b'RIFF') and data[8:12]==b'WEBP':return 'webp','image/webp'
    raise ValueError('Wallpaper is not a supported raster image')

def cache_home_wallpaper(payload,*,directory=None):
    """Decode inner WallpaperResponseMessage and cache only a real type1 payload.

    Caller unwraps DeviceResourceManagerResponseMessage first and verifies the
    request correlation and paired sender. Returned values contain no image data.
    """
    response=WallpaperResponseMessage.FromString(payload)
    if response.status!=1:
        return {'status':{2:'sync_disabled',3:'need_permissions'}.get(response.status,'unknown')}
    home=next((x for x in response.wallpapers if x.wallpaper_type==1 and x.HasField('payload')),None)
    if home is None or not home.payload:return {'status':'unchanged'}
    return cache_wallpaper_image(home.payload,wallpaper_id=home.id,directory=directory)


def cache_wallpaper_image(data,*,wallpaper_id=None,directory=None):
    if len(data)>MAX_IMAGE_BYTES:raise ValueError('Wallpaper exceeds image size limit')
    extension,mime=image_format(data)
    directory=Path(directory) if directory is not None else Path.home()/'.local/state/tahoe-phone-link'
    if directory.is_symlink():raise ValueError('Unexpected cache directory')
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(directory,0o700)
    fd,temp=tempfile.mkstemp(prefix='.wallpaper-',dir=directory)
    target=directory/('phone-wallpaper.'+extension)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data)
        os.replace(temp,target)
        for suffix in ('jpg','png','webp'):
            old=directory/('phone-wallpaper.'+suffix)
            if old!=target:old.unlink(missing_ok=True)
    finally:
        Path(temp).unlink(missing_ok=True)
    return {'status':'received','path':str(target),'mime':mime,'wallpaper_id':wallpaper_id}


def cache_legacy_home_wallpaper(values,*,directory=None):
    """Legacy builder emits a byte[] wallpaper with internal home type0."""
    image=values.entries.get('wallpaper')
    if image is None or image.value_type!=18:return None
    kind=values.entries.get('wallpaperType')
    identifier=values.entries.get('wallpaperId')
    scalar={4:'int32_value',5:'uint32_value',6:'int64_value',7:'uint64_value'}
    def number(value):
        field=scalar.get(value.value_type) if value is not None else None
        return getattr(value,field) if field else None
    if number(kind)!=0:return None
    return cache_wallpaper_image(image.uint8_array,wallpaper_id=number(identifier),directory=directory)
