import os
import glob
import json
import struct
import sqlite3
from collections import deque


class FifoMemoryQueue(object):
    """In-memory FIFO queue, API compliant with FifoDiskQueue."""

    def __init__(self):
        self.q = deque()
        self.push = self.q.append

    def pop(self):
        q = self.q
        return q.popleft() if q else None

    def close(self):
        pass

    def __len__(self):
        return len(self.q)


class LifoMemoryQueue(FifoMemoryQueue):
    """In-memory LIFO queue, API compliant with LifoDiskQueue."""

    def pop(self):
        q = self.q
        return q.pop() if q else None


class FifoDiskQueue(object):
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
        os.lseek(self.tailf.fileno(), self.info['tail'][2], os.SEEK_SET)

    def push(self, string):
        if not isinstance(string, bytes):
            raise TypeError('Unsupported type: {}'.format(type(string).__name__))
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
        self.info['head'] = [hnum, hpos]

    def _openchunk(self, number, mode='rb'):
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
        self.info['tail'] = [tnum, tcnt, toffset]
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



class LifoDiskQueue(object):
    """Persistent LIFO queue."""

    SIZE_FORMAT = ">L"
    SIZE_SIZE = struct.calcsize(SIZE_FORMAT)

    def __init__(self, path):
        self.path = path
        if os.path.exists(path):
            self.f = open(path, 'rb+')
            qsize = self.f.read(self.SIZE_SIZE)
            self.size, = struct.unpack(self.SIZE_FORMAT, qsize)
            self.f.seek(0, os.SEEK_END)
        else:
            self.f = open(path, 'wb+')
            self.f.write(struct.pack(self.SIZE_FORMAT, 0))
            self.size = 0

    def push(self, string):
        if not isinstance(string, bytes):
            raise TypeError('Unsupported type: {}'.format(type(string).__name__))
        self.f.write(string)
        ssize = struct.pack(self.SIZE_FORMAT, len(string))
        self.f.write(ssize)
        self.size += 1

    def pop(self):
        if not self.size:
            return
        self.f.seek(-self.SIZE_SIZE, os.SEEK_END)
        size, = struct.unpack(self.SIZE_FORMAT, self.f.read())
        self.f.seek(-size-self.SIZE_SIZE, os.SEEK_END)
        data = self.f.read(size)
        self.f.seek(-size, os.SEEK_CUR)
        self.f.truncate()
        self.size -= 1
        return data

    def close(self):
        if self.size:
            self.f.seek(0)
            self.f.write(struct.pack(self.SIZE_FORMAT, self.size))
        self.f.close()
        if not self.size:
            os.remove(self.path)

    def __len__(self):
        return self.size


class FifoSQLiteQueue(object):

    _sql_create = (
        'CREATE TABLE IF NOT EXISTS queue '
        '(id INTEGER PRIMARY KEY AUTOINCREMENT, item BLOB)'
    )
    _sql_size = 'SELECT COUNT(*) FROM queue'
    _sql_push = 'INSERT INTO queue (item) VALUES (?)'
    _sql_pop = 'SELECT id, item FROM queue ORDER BY id LIMIT 1'
    _sql_del = 'DELETE FROM queue WHERE id = ?'

    def __init__(self, path):
        self._path = os.path.abspath(path)
        self._db = sqlite3.Connection(self._path, timeout=60)
        self._db.text_factory = bytes
        with self._db as conn:
            conn.execute(self._sql_create)

    def push(self, item):
        if not isinstance(item, bytes):
            raise TypeError('Unsupported type: {}'.format(type(item).__name__))

        with self._db as conn:
            conn.execute(self._sql_push, (item,))

    def pop(self):
        with self._db as conn:
            for id_, item in conn.execute(self._sql_pop):
                conn.execute(self._sql_del, (id_,))
                return item

    def close(self):
        size = len(self)
        self._db.close()
        if not size:
            os.remove(self._path)

    def __len__(self):
        with self._db as conn:
            return next(conn.execute(self._sql_size))[0]


class LifoSQLiteQueue(FifoSQLiteQueue):

    _sql_pop = 'SELECT id, item FROM queue ORDER BY id DESC LIMIT 1'


#FifoDiskQueue = FifoSQLiteQueue  # noqa
#LifoDiskQueue = LifoSQLiteQueue  # noqa
