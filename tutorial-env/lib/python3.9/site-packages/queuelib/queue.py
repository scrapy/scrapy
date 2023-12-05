import glob
import json
import os
import sqlite3
import struct
from abc import abstractmethod
from collections import deque
from contextlib import suppress
from typing import Any, Optional


class _BaseQueueMeta(type):
    """
    Metaclass to check queue classes against the necessary interface
    """

    def __instancecheck__(cls, instance):
        return cls.__subclasscheck__(type(instance))  # pylint: disable=no-value-for-parameter

    def __subclasscheck__(cls, subclass):
        return (
            hasattr(subclass, "push")
            and callable(subclass.push)
            and hasattr(subclass, "pop")
            and callable(subclass.pop)
            and hasattr(subclass, "peek")
            and callable(subclass.peek)
            and hasattr(subclass, "close")
            and callable(subclass.close)
            and hasattr(subclass, "__len__")
            and callable(subclass.__len__)
        )


class BaseQueue(metaclass=_BaseQueueMeta):
    @abstractmethod
    def push(self, obj: Any) -> None:
        raise NotImplementedError()

    @abstractmethod
    def pop(self) -> Optional[Any]:
        raise NotImplementedError()

    @abstractmethod
    def peek(self) -> Optional[Any]:
        raise NotImplementedError()

    @abstractmethod
    def __len__(self):
        raise NotImplementedError()

    def close(self) -> None:
        pass


class FifoMemoryQueue:
    """In-memory FIFO queue, API compliant with FifoDiskQueue."""

    def __init__(self) -> None:
        self.q = deque()  # type: deque

    def push(self, obj: Any) -> None:
        self.q.append(obj)

    def pop(self) -> Optional[Any]:
        return self.q.popleft() if self.q else None

    def peek(self) -> Optional[Any]:
        return self.q[0] if self.q else None

    def close(self) -> None:
        pass

    def __len__(self):
        return len(self.q)


class LifoMemoryQueue(FifoMemoryQueue):
    """In-memory LIFO queue, API compliant with LifoDiskQueue."""

    def pop(self) -> Optional[Any]:
        return self.q.pop() if self.q else None

    def peek(self) -> Optional[Any]:
        return self.q[-1] if self.q else None


class FifoDiskQueue:
    """Persistent FIFO queue."""

    szhdr_format = ">L"
    szhdr_size = struct.calcsize(szhdr_format)

    def __init__(self, path: str, chunksize: int = 100000) -> None:
        self.path = path
        if not os.path.exists(path):
            os.makedirs(path)
        self.info = self._loadinfo(chunksize)
        self.chunksize = self.info["chunksize"]
        self.headf = self._openchunk(self.info["head"][0], "ab+")
        self.tailf = self._openchunk(self.info["tail"][0])
        os.lseek(self.tailf.fileno(), self.info["tail"][2], os.SEEK_SET)

    def push(self, string: bytes) -> None:
        if not isinstance(string, bytes):
            raise TypeError("Unsupported type: {}".format(type(string).__name__))
        hnum, hpos = self.info["head"]
        hpos += 1
        szhdr = struct.pack(self.szhdr_format, len(string))
        os.write(self.headf.fileno(), szhdr + string)
        if hpos == self.chunksize:
            hpos = 0
            hnum += 1
            self.headf.close()
            self.headf = self._openchunk(hnum, "ab+")
        self.info["size"] += 1
        self.info["head"] = [hnum, hpos]

    def _openchunk(self, number: int, mode: str = "rb"):
        return open(os.path.join(self.path, "q%05d" % number), mode)

    def pop(self) -> Optional[bytes]:
        tnum, tcnt, toffset = self.info["tail"]
        if [tnum, tcnt] >= self.info["head"]:
            return None
        tfd = self.tailf.fileno()
        szhdr = os.read(tfd, self.szhdr_size)
        if not szhdr:
            return None
        (size,) = struct.unpack(self.szhdr_format, szhdr)
        data = os.read(tfd, size)
        tcnt += 1
        toffset += self.szhdr_size + size
        if tcnt == self.chunksize and tnum <= self.info["head"][0]:
            tcnt = toffset = 0
            tnum += 1
            self.tailf.close()
            os.remove(self.tailf.name)
            self.tailf = self._openchunk(tnum)
        self.info["size"] -= 1
        self.info["tail"] = [tnum, tcnt, toffset]
        return data

    def peek(self) -> Optional[bytes]:
        tnum, tcnt, _ = self.info["tail"]
        if [tnum, tcnt] >= self.info["head"]:
            return None
        tfd = self.tailf.fileno()
        tfd_initial_pos = os.lseek(tfd, 0, os.SEEK_CUR)
        szhdr = os.read(tfd, self.szhdr_size)
        if not szhdr:
            return None
        (size,) = struct.unpack(self.szhdr_format, szhdr)
        data = os.read(tfd, size)
        os.lseek(tfd, tfd_initial_pos, os.SEEK_SET)
        return data

    def close(self) -> None:
        self.headf.close()
        self.tailf.close()
        self._saveinfo(self.info)
        if len(self) == 0:
            self._cleanup()

    def __len__(self) -> int:
        return self.info["size"]

    def _loadinfo(self, chunksize: int) -> dict:
        infopath = self._infopath()
        if os.path.exists(infopath):
            with open(infopath) as f:
                info = json.load(f)
        else:
            info = {
                "chunksize": chunksize,
                "size": 0,
                "tail": [0, 0, 0],
                "head": [0, 0],
            }
        return info

    def _saveinfo(self, info: dict) -> None:
        with open(self._infopath(), "w") as f:
            json.dump(info, f)

    def _infopath(self) -> str:
        return os.path.join(self.path, "info.json")

    def _cleanup(self) -> None:
        for x in glob.glob(os.path.join(self.path, "q*")):
            os.remove(x)
        os.remove(os.path.join(self.path, "info.json"))
        with suppress(OSError):
            os.rmdir(self.path)


class LifoDiskQueue:
    """Persistent LIFO queue."""

    SIZE_FORMAT = ">L"
    SIZE_SIZE = struct.calcsize(SIZE_FORMAT)

    def __init__(self, path: str) -> None:
        self.path = path
        if os.path.exists(path):
            self.f = open(path, "rb+")
            qsize = self.f.read(self.SIZE_SIZE)
            (self.size,) = struct.unpack(self.SIZE_FORMAT, qsize)
            self.f.seek(0, os.SEEK_END)
        else:
            self.f = open(path, "wb+")
            self.f.write(struct.pack(self.SIZE_FORMAT, 0))
            self.size = 0

    def push(self, string: bytes) -> None:
        if not isinstance(string, bytes):
            raise TypeError("Unsupported type: {}".format(type(string).__name__))
        self.f.write(string)
        ssize = struct.pack(self.SIZE_FORMAT, len(string))
        self.f.write(ssize)
        self.size += 1

    def pop(self) -> Optional[bytes]:
        if not self.size:
            return None
        self.f.seek(-self.SIZE_SIZE, os.SEEK_END)
        (size,) = struct.unpack(self.SIZE_FORMAT, self.f.read())
        self.f.seek(-size - self.SIZE_SIZE, os.SEEK_END)
        data = self.f.read(size)
        self.f.seek(-size, os.SEEK_CUR)
        self.f.truncate()
        self.size -= 1
        return data

    def peek(self) -> Optional[bytes]:
        if not self.size:
            return None
        self.f.seek(-self.SIZE_SIZE, os.SEEK_END)
        (size,) = struct.unpack(self.SIZE_FORMAT, self.f.read())
        self.f.seek(-size - self.SIZE_SIZE, os.SEEK_END)
        data = self.f.read(size)
        return data

    def close(self) -> None:
        if self.size:
            self.f.seek(0)
            self.f.write(struct.pack(self.SIZE_FORMAT, self.size))
        self.f.close()
        if not self.size:
            os.remove(self.path)

    def __len__(self) -> int:
        return self.size


class FifoSQLiteQueue:
    _sql_create = "CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY AUTOINCREMENT, item BLOB)"
    _sql_size = "SELECT COUNT(*) FROM queue"
    _sql_push = "INSERT INTO queue (item) VALUES (?)"
    _sql_pop = "SELECT id, item FROM queue ORDER BY id LIMIT 1"
    _sql_del = "DELETE FROM queue WHERE id = ?"

    def __init__(self, path: str) -> None:
        self._path = os.path.abspath(path)
        self._db = sqlite3.Connection(self._path, timeout=60)
        self._db.text_factory = bytes
        with self._db as conn:
            conn.execute(self._sql_create)

    def push(self, item: bytes) -> None:
        if not isinstance(item, bytes):
            raise TypeError("Unsupported type: {}".format(type(item).__name__))
        with self._db as conn:
            conn.execute(self._sql_push, (item,))

    def pop(self) -> Optional[bytes]:
        with self._db as conn:
            for id_, item in conn.execute(self._sql_pop):
                conn.execute(self._sql_del, (id_,))
                return item
        return None

    def peek(self) -> Optional[bytes]:
        with self._db as conn:
            for _, item in conn.execute(self._sql_pop):
                return item
        return None

    def close(self) -> None:
        size = len(self)
        self._db.close()
        if not size:
            os.remove(self._path)

    def __len__(self) -> int:
        with self._db as conn:
            return next(conn.execute(self._sql_size))[0]


class LifoSQLiteQueue(FifoSQLiteQueue):
    _sql_pop = "SELECT id, item FROM queue ORDER BY id DESC LIMIT 1"
