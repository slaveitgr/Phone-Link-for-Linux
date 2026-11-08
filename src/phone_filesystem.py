"""Read-only Wi-Fi phone filesystem for the Linux file manager.

Only shared storage is exposed. Reading uses bounded chunks over the authorized
Wi-Fi Android link; no file contents are written to a persistent local cache.
"""
import errno,os,posixpath,shlex,stat,sys,time,threading
from collections import OrderedDict
from pathlib import Path
from phone_transfer import PhoneTransfer,ROOT
from fuse import FUSE,FuseOSError,Operations

MOUNT=Path.home()/'.local/share/tahoe-phone-link/Phone Files'
class PhoneFilesystem(Operations):
    def __init__(self):
        self.client=PhoneTransfer();self.directories={};self.attrs={};self.blocks=OrderedDict();self.lock=threading.RLock();self.started=int(time.time());self.capacity=None
    def remote(self,path):return self.client.safe_path(ROOT+path)
    def listing(self,path):
        now=time.monotonic();cached=self.directories.get(path)
        if cached and now-cached[0]<5:return cached[1]
        remote=self.remote(path)
        command='find '+shlex.quote(remote)+" -mindepth 1 -maxdepth 1 -exec stat -c '%f|%s|%Y|%n' -- {} +"
        try:output=self.client._adb('shell',command,timeout=20)
        except Exception:raise FuseOSError(errno.EHOSTUNREACH)
        for key in list(self.attrs):
            if posixpath.dirname(key)==path:self.attrs.pop(key,None)
        names=[]
        for line in output.splitlines()[:20000]:
            parts=line.split('|',3)
            if len(parts)!=4:continue
            try:
                mode=int(parts[0],16);size=int(parts[1]);stamp=int(parts[2]);full=self.client.safe_path(parts[3])
            except ValueError:continue
            name=posixpath.basename(full)
            if name in ('.','..') or not name:continue
            names.append(name);key=full[len(ROOT):] or '/'
            self.attrs[key]=(now,self.attributes(mode,size,stamp))
        self.directories[path]=(now,names)
        return names
    def attributes(self,mode,size,stamp):
        directory=stat.S_ISDIR(mode)
        return {'st_mode':(stat.S_IFDIR|0o555) if directory else (stat.S_IFREG|0o444),
            'st_nlink':2 if directory else 1,'st_size':size,'st_uid':os.getuid(),'st_gid':os.getgid(),
            'st_atime':stamp,'st_mtime':stamp,'st_ctime':stamp}
    def getattr(self,path,fh=None):
        if path=='/':return self.attributes(stat.S_IFDIR,0,self.started)
        cached=self.attrs.get(path)
        if cached and time.monotonic()-cached[0]<5:return cached[1]
        parent=posixpath.dirname(path) or '/';self.listing(parent)
        cached=self.attrs.get(path)
        if cached:return cached[1]
        raise FuseOSError(errno.ENOENT)
    def readdir(self,path,fh):return ['.','..',*self.listing(path)]
    def open(self,path,flags):
        if flags & (os.O_WRONLY|os.O_RDWR):raise FuseOSError(errno.EROFS)
        self.getattr(path);return 0
    def read(self,path,size,offset,fh):
        if size<=0:return b''
        remote=self.remote(path);block_size=256*1024
        start=offset//block_size;end=(offset+size-1)//block_size;result=[]
        for index in range(start,end+1):
            key=(path,index);cached=self.blocks.get(key)
            if cached and time.monotonic()-cached[0]<10:data=cached[1]
            else:
                command='dd if='+shlex.quote(remote)+' bs='+str(block_size)+' skip='+str(index)+' count=1 2>/dev/null'
                try:data=self.client._adb('exec-out',command,timeout=30,binary=True)
                except Exception:raise FuseOSError(errno.EHOSTUNREACH)
                self.blocks[key]=(time.monotonic(),data)
                while len(self.blocks)>32:self.blocks.popitem(last=False)
            result.append(data)
        raw=b''.join(result);relative=offset-start*block_size
        return raw[relative:relative+size]
    def statfs(self,path):
        try:
            if self.capacity is None or time.monotonic()-self.capacity[0]>60:
                raw=self.client._adb('shell',"stat -f -c '%S|%b|%f|%a' "+shlex.quote(ROOT),timeout=10).strip()
                size,total,free,available=map(int,raw.split('|'))
                self.capacity=(time.monotonic(),{'f_bsize':size,'f_frsize':size,'f_blocks':total,'f_bfree':free,'f_bavail':available,'f_files':20000,'f_ffree':0,'f_favail':0,'f_namemax':255})
            return self.capacity[1]
        except Exception:pass
        return {'f_bsize':4096,'f_frsize':4096,'f_blocks':0,'f_bfree':0,'f_bavail':0,'f_files':20000,'f_ffree':0,'f_favail':0,'f_namemax':255}

def main():
    MOUNT.mkdir(parents=True,exist_ok=True)
    FUSE(PhoneFilesystem(),str(MOUNT),foreground=True,nothreads=True,ro=True,fsname='PhoneLink',subtype='phone-link')
if __name__=='__main__':main()
