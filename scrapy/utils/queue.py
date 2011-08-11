from __future__ import with_statement

import os
import struct
import glob
from collections import deque

from scrapy.utils.py26 import json


class MemoryQueue(object):
    """Memory FIFO queue."""

    def __init__(self):
        self.q = deque()

    def push(self, obj):
        self.q.appendleft(obj)

    def pop(self):
        if self.q:
            return self.q.pop()

    def close(self):
        pass

    def __len__(self):
        return len(self.q)


class DiskQueue(object):
    """Persistent FIFO queue."""

    szhdr_format = ">L"
    szhdr_size = struct.calcsize(szhdr_format)

    def __init__(self, path, chunksize=100000):
        self.path = path
        if not os.path.exists(path):
            os.makedirs(path)
        self.info = self._loadinfo(chunksize)
        self.chunksize = self.info['chunksize']
        self.headf = self._openchunk(self.info['head'][0], 'ab+')
        self.tailf = self._openchunk(self.info['tail'][0])
        self.tailf.seek(self.info['tail'][2])

    def push(self, string):
        hnum, hpos = self.info['head']
        hpos += 1
        szhdr = struct.pack(self.szhdr_format, len(string))
        os.write(self.headf.fileno(), szhdr + string)
        if hpos == self.chunksize:
            hpos = 0
            hnum += 1
            self.headf.close()
            self.headf = self._openchunk(hnum, 'ab+')
        self.info['size'] += 1
        self.info['head'] = hnum, hpos

    def _openchunk(self, number, mode='r'):
        return open(os.path.join(self.path, 'q%05d' % number), mode)

    def pop(self):
        tnum, tcnt, toffset = self.info['tail']
        if [tnum, tcnt] >= self.info['head']:
            return
        tfd = self.tailf.fileno()
        szhdr = os.read(tfd, self.szhdr_size)
        if not szhdr:
            return
        size, = struct.unpack(self.szhdr_format, szhdr)
        data = os.read(tfd, size)
        tcnt += 1
        toffset += self.szhdr_size + size
        if tcnt == self.chunksize and tnum <= self.info['head'][0]:
            tcnt = toffset = 0
            tnum += 1
            self.tailf.close()
            os.remove(self.tailf.name)
            self.tailf = self._openchunk(tnum)
        self.info['size'] -= 1
        self.info['tail'] = tnum, tcnt, toffset
        return data

    def close(self):
        self.headf.close()
        self.tailf.close()
        self._saveinfo(self.info)
        if len(self) == 0:
            self._cleanup()

    def __len__(self):
        return self.info['size']

    def _loadinfo(self, chunksize):
        infopath = self._infopath()
        if os.path.exists(infopath):
            with open(infopath) as f:
                info = json.load(f)
        else:
            info = {
                'chunksize': chunksize,
                'size': 0,
                'tail': [0, 0, 0],
                'head': [0, 0],
            }
        return info

    def _saveinfo(self, info):
        with open(self._infopath(), 'w') as f:
            json.dump(info, f)

    def _infopath(self):
        return os.path.join(self.path, 'info.json')

    def _cleanup(self):
        for x in glob.glob(os.path.join(self.path, 'q*')):
            os.remove(x)
        os.remove(os.path.join(self.path, 'info.json'))
        if not os.listdir(self.path):
            os.rmdir(self.path)
