# SYNOPSIS: a shim to use lmdb where in apps that expect dbm's API
#
#   import dbm2lmdb as dbm
#   db = dbm.open('porn')
#   db['Alice'] = 'Bob'
#   db['Alice']
#   db['Clara']
#   del db['Alice']
#   db.close()
#
# SEE ALSO:
#
#   https://lmdb.readthedocs.io
#   http://www.lmdb.tech/doc/

import lmdb


class DBMLikeLMDBEnvironment:
    def __init__(self,
                 path: str,
                 flags: str = 'r',
                 mode: int = 0o666):
        for c in flags:
            if c not in 'rwc':
                raise NotImplementedError('Unsupported flag', c)
        self.env = lmdb.Environment(
            str(path),          # str() to add pathlib support
            readonly='r' in flags,
            create='c' in flags)
        # By default LMDB lets you store up to 10MiB; increase that to 1GiB.
        # UPDATE: requires python3-lmdb (>= 0.87); Debian 10 has 0.86.
        # Ouch!  I give up for today.
        self.env.set_mapsize(2**30)

    # db['foo']
    def __getitem__(self, key):
        with self.env.begin() as txn:
            return txn.get(_bytes(key))

    # db['foo'] = 'bar'
    def __setitem__(self, key, value):
        with self.env.begin(write=True) as txn:
            return txn.put(_bytes(key), _bytes(value))

    # del db['foo']
    def __delitem__(self, key):
        with self.env.begin() as txn:
            return txn.delete(_bytes(key))

    # 'foo' in db
    # 'foo' not in db
    def __contains__(self, key):
        return self.__getitem__(key) is not None

    def close(self):
        return self.env.close()

    def sync(self):
        return self.env.sync()

    def firstkey(self):
        raise NotImplementedError()

    def nextkey(self):
        raise NotImplementedError()

    def reorganize(self):
        raise NotImplementedError()


def open(*args, **kwargs):
    return DBMLikeLMDBEnvironment(*args, **kwargs)


def whichdb(*args, **kwargs):
    raise NotImplementedError()


def _bytes(b):
    if isinstance(b, bytes):
        return b
    elif isinstance(b, str):
        return bytes(b, encoding='UTF-8')
    else:
        raise ValueError(b)
