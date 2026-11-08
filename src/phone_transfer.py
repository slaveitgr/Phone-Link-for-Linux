"""Explicit, user-selected Wi-Fi file transfer over the authorized Android link."""
import os,shlex,shutil,subprocess,uuid,posixpath
from pathlib import Path,PurePosixPath
from webcam_controller import _selected_android

ROOT='/storage/emulated/0'
class PhoneTransfer:
    def _adb(self,*args,timeout=120,binary=False):
        serial,reason=_selected_android()
        if reason:raise RuntimeError(reason)
        return subprocess.run([shutil.which('adb'),'-s',serial,*args],capture_output=True,text=not binary,timeout=timeout,check=True).stdout
    @staticmethod
    def safe_path(path):
        if not isinstance(path,str) or len(path)>8192 or '\x00' in path or '\n' in path:raise ValueError('Invalid phone path')
        if path.startswith('/sdcard/'):path=ROOT+path[len('/sdcard'):]
        if path=='/sdcard':path=ROOT
        if not path.startswith('/'):path=posixpath.join(ROOT,path)
        normalized=posixpath.normpath(path)
        if normalized!=ROOT and not normalized.startswith(ROOT+'/'):raise ValueError('Path is outside shared phone storage')
        return normalized
    def list_folder(self,path=ROOT):
        path=self.safe_path(path);records=[]
        for kind in ('d','f'):
            command='find '+shlex.quote(path)+' -mindepth 1 -maxdepth 1 -type '+kind+' -print0'
            raw=self._adb('shell',command,timeout=15,binary=True)
            for item in raw.split(b'\0'):
                if not item:continue
                decoded=item.decode('utf-8','replace')
                try:remote=self.safe_path(decoded)
                except ValueError:continue
                records.append({'name':posixpath.basename(remote),'path':remote,'directory':kind=='d'})
                if len(records)>=1000:break
            if len(records)>=1000:break
        return {'status':'ok','path':path,'parent':posixpath.dirname(path) if path!=ROOT else None,
            'files':sorted(records,key=lambda f:(not f['directory'],f['name'].casefold()))}
    def send(self,local_path):
        local=Path(local_path)
        if not local.is_file():raise ValueError('Select a regular file')
        destination=ROOT+'/Download/Phone Link'
        self._adb('shell','mkdir -p -- '+shlex.quote(destination),timeout=10)
        remote=destination+'/'+local.name
        try:self._adb('shell','test ! -e '+shlex.quote(remote),timeout=10)
        except subprocess.CalledProcessError:
            remote=destination+'/'+local.stem+'-'+uuid.uuid4().hex[:8]+local.suffix
        self._adb('push',str(local),remote,timeout=300)
        return {'status':'sent','name':local.name,'path':remote,'bytes':local.stat().st_size}
    def receive(self,remote_path,directory=None):
        remote=self.safe_path(remote_path)
        directory=Path(directory) if directory else Path.home()/'Downloads/Phone Link'
        directory.mkdir(parents=True,exist_ok=True)
        target=directory/posixpath.basename(remote)
        if target.exists():target=directory/(target.stem+'-'+uuid.uuid4().hex[:8]+target.suffix)
        partial=directory/('.phone-link-'+uuid.uuid4().hex+'.part')
        fd=os.open(partial,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        try:
            self._adb('pull',remote,str(partial),timeout=300)
            while True:
                try:os.link(partial,target);break
                except FileExistsError:target=directory/(target.stem+'-'+uuid.uuid4().hex[:8]+target.suffix)
            partial.unlink();target.chmod(0o600)
        finally:partial.unlink(missing_ok=True)
        return {'status':'received','name':target.name,'path':str(target),'bytes':target.stat().st_size}
    def photo_path(self,metadata):
        path=metadata.get('path','');name=metadata.get('name','')
        if not path:raise ValueError('Photo path is unavailable')
        if name and posixpath.basename(path)!=name:path=posixpath.join(path,name)
        return self.safe_path(path)
