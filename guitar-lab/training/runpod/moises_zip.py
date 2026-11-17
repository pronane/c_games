"""A seekable file over HTTP range requests, so zipfile can read single members of a large
remote zip (MoisesDB is 89 GB) without downloading the whole archive."""
import io
import sys
import time
import urllib.request


class HTTPFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        self.size = int(self._get(0, 0)[1].split('/')[-1])

    def _get(self, a, b):
        for attempt in range(20):
            try:
                request = urllib.request.Request(self.url, headers={'Range': f'bytes={a}-{b}'})
                with urllib.request.urlopen(request, timeout=120) as response:
                    return response.read(), response.headers['Content-Range']
            except Exception as exc:
                print('retry', a, attempt, repr(exc)[:80], file=sys.stderr, flush=True)
                time.sleep(3 * (attempt + 1))
        raise SystemExit('range read failed')

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def readinto(self, b):
        n = min(len(b), self.size - self.pos)
        if n <= 0:
            return 0
        data = self._get(self.pos, self.pos + n - 1)[0]
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)
