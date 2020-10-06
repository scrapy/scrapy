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
#   https://en.wikipedia.org/wiki/Tokyo_Cabinet_and_Kyoto_Cabinet
#   https://dbmx.net/kyotocabinet/pythondoc/  (seriously, frames?)
#
# NOTE: this is not even remotely working currently.

import pathlib
import logging

import kyotocabinet


class DBMLikeKyotoCabinet:
    def __init__(self, path, flags=None, mode=None):
        if flags is not None or mode is not None:
            raise NotImplementedError(flags, mode)
        # kyotocabinet databases MUST have a specific extension?
        path_kch = pathlib.Path(path).with_suffix('.kch')
        self.db = kyotocabinet.DB()
        ok = self.db.open(path_kch)
        if not ok:                          # seriously?
            raise RuntimeError(self.db.error())  # seriously?

    # db['foo']
    def __getitem__(self, key):
        value = self.db.get(_bytes(key))
        if not value:                         # seriously?
            logging.warn('%s', self.db.error)  # seriously?
            return None                        # seriously?

    # db['foo'] = 'bar'
    def __setitem__(self, key, value):
        ok = self.db.set(_bytes(key), _bytes(value))
        if not ok:                              # seriously?
            raise RuntimeError(self.db.error())  # seriously?

    # del db['foo']
    def __delitem__(self, key):
        raise NotImplementedError()

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
    return DBMLikeKyotoCabinet(*args, **kwargs)


def whichdb(*args, **kwargs):
    raise NotImplementedError()


def _bytes(b):
    if isinstance(b, bytes):
        return b
    elif isinstance(b, str):
        return bytes(b, encoding='UTF-8')
    else:
        raise ValueError(b)
