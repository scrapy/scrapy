# SYNOPSIS: a shim to use sqlite3 where in apps that expect dbm's API
#
#   import dbm2sqlite as dbm
#   db = dbm.open('porn')
#   db['Alice'] = 'Bob'
#   db['Alice']
#   db['Clara']
#   del db['Alice']
#   db.close()
#
# SEE ALSO:
#
#   https://sqlite.org/affcase1.html
#
# PRIOR ART (just use that instead?):
#
#   https://bugs.python.org/issue3783

import sqlite3


class DBMLikeSqliteConnection:
    def __init__(self, path, flags='c', mode=None):
        if mode is not None:
            raise NotImplementedError(mode)
        for c in flags:
            if c not in 'wc':
                raise NotImplementedError('Unsupported flag', c)
        self.conn = sqlite3.connect(path)
        # Enable "go faster" stripes
        self.conn.execute('PRAGMA journal_mode = WAL')
        self.conn.execute('CREATE TABLE IF NOT EXISTS main(key BLOB PRIMARY KEY, value BLOB) WITHOUT ROWID;')

    # db['foo']
    def __getitem__(self, key):
        row = self.conn.execute(
            'SELECT value FROM main WHERE key = :key',
            {'key': _bytes(key)}).fetchone()
        if row:
            return row[0]
        else:
            return None

    # db['foo'] = 'bar'
    def __setitem__(self, key, value):
        self.conn.execute(
            'REPLACE INTO main (key, value) VALUES (:key, :value)',
            {'key': _bytes(key),
             'value': _bytes(value)})
        self.conn.commit()      # FIXME: yuk

    # del db['foo']
    def __delitem__(self, key):
        self.conn.execute(
            'DELETE FROM main WHERE key = :key',
            {'key': _bytes(key)})
        self.conn.commit()      # FIXME: yuk

    # 'foo' in db
    # 'foo' not in db
    def __contains__(self, key):
        return self.__getitem__(key) is not None

    def close(self):
        return self.conn.close()

    def sync(self):
        raise NotImplementedError()

    def firstkey(self):
        raise NotImplementedError()

    def nextkey(self):
        raise NotImplementedError()

    def reorganize(self):
        raise NotImplementedError()


def open(*args, **kwargs):
    return DBMLikeSqliteConnection(*args, **kwargs)


def whichdb(*args, **kwargs):
    raise NotImplementedError()


def _bytes(b):
    if isinstance(b, bytes):
        return b
    elif isinstance(b, str):
        return bytes(b, encoding='UTF-8')
    else:
        raise ValueError(b)
