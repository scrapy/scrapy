import sqlite3
import cPickle
from UserDict import DictMixin

from scrapy.utils.py26 import json


class SqliteDict(DictMixin):
    """SQLite-backed dictionary"""

    def __init__(self, database=None, table="dict"):
        self.database = database or ':memory:'
        self.table = table
        # about check_same_thread: http://twistedmatrix.com/trac/ticket/4040
        self.conn = sqlite3.connect(self.database, check_same_thread=False)
        q = "create table if not exists %s (key text primary key, value blob)" \
            % table
        self.conn.execute(q)

    def __getitem__(self, key):
        key = self.encode(key)
        q = "select value from %s where key=?" % self.table
        value = self.conn.execute(q, (key,)).fetchone()
        if value:
            return self.decode(value[0])
        raise KeyError(key)

    def __setitem__(self, key, value):
        key, value = self.encode(key), self.encode(value)
        q = "insert or replace into %s (key, value) values (?,?)" % self.table
        self.conn.execute(q, (key, value))
        self.conn.commit()

    def __delitem__(self, key):
        key = self.encode(key)
        q = "delete from %s where key=?" % self.table
        self.conn.execute(q, (key,))
        self.conn.commit()

    def iterkeys(self):
        q = "select key from %s" % self.table
        return (self.decode(x[0]) for x in self.conn.execute(q))

    def keys(self):
        return list(self.iterkeys())

    def itervalues(self):
        q = "select value from %s" % self.table
        return (self.decode(x[0]) for x in self.conn.execute(q))

    def values(self):
        return list(self.itervalues())

    def iteritems(self):
        q = "select key, value from %s" % self.table
        return ((self.decode(x[0]), self.decode(x[1])) for x in self.conn.execute(q))

    def items(self):
        return list(self.iteritems())

    def encode(self, obj):
        return obj

    def decode(self, text):
        return text


class PickleSqliteDict(SqliteDict):

    def encode(self, obj):
        return buffer(cPickle.dumps(obj, protocol=2))

    def decode(self, text):
        return cPickle.loads(str(text))


class JsonSqliteDict(SqliteDict):

    def encode(self, obj):
        return json.dumps(obj)

    def decode(self, text):
        return json.loads(text)



class SqlitePriorityQueue(object):
    """SQLite priority queue. It relies on SQLite concurrency support for
    providing atomic inter-process operations.
    """

    def __init__(self, database=None, table="queue"):
        self.database = database or ':memory:'
        self.table = table
        # about check_same_thread: http://twistedmatrix.com/trac/ticket/4040
        self.conn = sqlite3.connect(self.database, check_same_thread=False)
        q = "create table if not exists %s (id integer primary key, " \
            "priority real key, message blob)" % table
        self.conn.execute(q)

    def put(self, message, priority=0.0):
        args = (priority, self.encode(message))
        q = "insert into %s (priority, message) values (?,?)" % self.table
        self.conn.execute(q, args)
        self.conn.commit()

    def pop(self):
        q = "select id, message from %s order by priority desc limit 1" \
            % self.table
        idmsg = self.conn.execute(q).fetchone()
        if idmsg is None:
            return
        id, msg = idmsg
        q = "delete from %s where id=?" % self.table
        c = self.conn.execute(q, (id,))
        if not c.rowcount: # record vanished, so let's try again
            self.conn.rollback()
            return self.pop()
        self.conn.commit()
        return self.decode(msg)

    def clear(self):
        self.conn.execute("delete from %s" % self.table)
        self.conn.commit()

    def __len__(self):
        q = "select count(*) from %s" % self.table
        return self.conn.execute(q).fetchone()[0]

    def __iter__(self):
        q = "select message, priority from %s order by priority desc" % \
            self.table
        return ((self.decode(x), y) for x, y in self.conn.execute(q))

    def encode(self, obj):
        return obj

    def decode(self, text):
        return text


class PickleSqlitePriorityQueue(SqlitePriorityQueue):

    def encode(self, obj):
        return buffer(cPickle.dumps(obj, protocol=2))

    def decode(self, text):
        return cPickle.loads(str(text))


class JsonSqlitePriorityQueue(SqlitePriorityQueue):

    def encode(self, obj):
        return json.dumps(obj)

    def decode(self, text):
        return json.loads(text)


