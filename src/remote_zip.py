"""Read-only, bounded HTTP Range access for a ZIP central directory and samples.

Never falls back to downloading a whole archive if the server ignores Range.
"""
import io
import re

import requests


class RangeReader(io.RawIOBase):
    def __init__(self,url,max_bytes=32*1024*1024):
        self.url=url
        self.session=requests.Session()
        self.position=0
        self.size=None
        self.downloaded=0
        self.max_bytes=max_bytes
        self.etag=None
        self.ranges=[]
        self._fetch(0,1)

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self,offset,whence=io.SEEK_SET):
        position=offset if whence==io.SEEK_SET else self.position+offset if whence==io.SEEK_CUR else self.size+offset
        if position<0:
            raise ValueError('Negative seek')
        self.position=position
        return position

    def _fetch(self,start,count):
        if count<1:
            return b''
        if self.downloaded+count>self.max_bytes:
            raise ValueError('HTTP Range byte budget exceeded; full download refused')
        headers={'Range':f'bytes={start}-{start+count-1}','Accept-Encoding':'identity'}
        if self.etag:
            headers['If-Range']=self.etag
        with self.session.get(self.url,headers=headers,stream=True,timeout=(10,60)) as response:
            if response.status_code!=206:
                raise ValueError(f'HTTP {response.status_code}: server did not honor Range; download refused')
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
            if not match or (int(match[1]),int(match[2]))!=(start,start+count-1):
                raise ValueError('Unexpected Content-Range')
            size=int(match[3])
            if self.size is not None and self.size!=size:
                raise ValueError('Remote ZIP changed during validation')
            self.size=size
            self.etag=self.etag or response.headers.get('ETag')
            data=response.raw.read(count+1)
            if len(data)!=count:
                raise ValueError('Unexpected range length')
        self.downloaded+=count
        self.ranges.append([start,count])
        return data

    def read(self,size=-1):
        count=min(self.size-self.position,size if size is not None and size>=0 else self.size-self.position)
        if count<=0:
            return b''
        data=self._fetch(self.position,count)
        self.position+=len(data)
        return data

    def close(self):
        self.session.close()
        super().close()
