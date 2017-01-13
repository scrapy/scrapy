# -*- test-case-name: twisted.test.test_adbapi -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
An asynchronous mapping to U{DB-API
2.0<http://www.python.org/topics/database/DatabaseAPI-2.0.html>}.
"""

import sys

from twisted.internet import threads
from twisted.python import reflect, log, compat


class ConnectionLost(Exception):
    """
    This exception means that a db connection has been lost.  Client code may
    try again.
    """



class Connection(object):
    """
    A wrapper for a DB-API connection instance.

    The wrapper passes almost everything to the wrapped connection and so has
    the same API. However, the L{Connection} knows about its pool and also
    handle reconnecting should when the real connection dies.
    """

    def __init__(self, pool):
        self._pool = pool
        self._connection = None
        self.reconnect()


    def close(self):
        # The way adbapi works right now means that closing a connection is
        # a really bad thing  as it leaves a dead connection associated with
        # a thread in the thread pool.
        # Really, I think closing a pooled connection should return it to the
        # pool but that's handled by the runWithConnection method already so,
        # rather than upsetting anyone by raising an exception, let's ignore
        # the request
        pass


    def rollback(self):
        if not self._pool.reconnect:
            self._connection.rollback()
            return

        try:
            self._connection.rollback()
            curs = self._connection.cursor()
            curs.execute(self._pool.good_sql)
            curs.close()
            self._connection.commit()
            return
        except:
            log.err(None, "Rollback failed")

        self._pool.disconnect(self._connection)

        if self._pool.noisy:
            log.msg("Connection lost.")

        raise ConnectionLost()


    def reconnect(self):
        if self._connection is not None:
            self._pool.disconnect(self._connection)
        self._connection = self._pool.connect()


    def __getattr__(self, name):
        return getattr(self._connection, name)



class Transaction:
    """
    A lightweight wrapper for a DB-API 'cursor' object.

    Relays attribute access to the DB cursor. That is, you can call
    C{execute()}, C{fetchall()}, etc., and they will be called on the
    underlying DB-API cursor object. Attributes will also be retrieved from
    there.
    """
    _cursor = None

    def __init__(self, pool, connection):
        self._pool = pool
        self._connection = connection
        self.reopen()


    def close(self):
        _cursor = self._cursor
        self._cursor = None
        _cursor.close()


    def reopen(self):
        if self._cursor is not None:
            self.close()

        try:
            self._cursor = self._connection.cursor()
            return
        except:
            if not self._pool.reconnect:
                raise
            else:
                log.err(None, "Cursor creation failed")

        if self._pool.noisy:
            log.msg('Connection lost, reconnecting')

        self.reconnect()
        self._cursor = self._connection.cursor()


    def reconnect(self):
        self._connection.reconnect()
        self._cursor = None


    def __getattr__(self, name):
        return getattr(self._cursor, name)



class ConnectionPool:
    """
    Represent a pool of connections to a DB-API 2.0 compliant database.

    @ivar connectionFactory: factory for connections, default to L{Connection}.
    @type connectionFactory: any callable.

    @ivar transactionFactory: factory for transactions, default to
        L{Transaction}.
    @type transactionFactory: any callable

    @ivar shutdownID: L{None} or a handle on the shutdown event trigger which
        will be used to stop the connection pool workers when the reactor
        stops.

    @ivar _reactor: The reactor which will be used to schedule startup and
        shutdown events.
    @type _reactor: L{IReactorCore} provider
    """

    CP_ARGS = "min max name noisy openfun reconnect good_sql".split()

    noisy = False # If true, generate informational log messages
    min = 3 # Minimum number of connections in pool
    max = 5 # Maximum number of connections in pool
    name = None # Name to assign to thread pool for debugging
    openfun = None # A function to call on new connections
    reconnect = False # Reconnect when connections fail
    good_sql = 'select 1' # A query which should always succeed

    running = False # True when the pool is operating
    connectionFactory = Connection
    transactionFactory = Transaction

    # Initialize this to None so it's available in close() even if start()
    # never runs.
    shutdownID = None

    def __init__(self, dbapiName, *connargs, **connkw):
        """
        Create a new L{ConnectionPool}.

        Any positional or keyword arguments other than those documented here
        are passed to the DB-API object when connecting. Use these arguments to
        pass database names, usernames, passwords, etc.

        @param dbapiName: an import string to use to obtain a DB-API compatible
            module (e.g. C{'pyPgSQL.PgSQL'})

        @param cp_min: the minimum number of connections in pool (default 3)

        @param cp_max: the maximum number of connections in pool (default 5)

        @param cp_noisy: generate informational log messages during operation
            (default C{False})

        @param cp_openfun: a callback invoked after every C{connect()} on the
            underlying DB-API object. The callback is passed a new DB-API
            connection object. This callback can setup per-connection state
            such as charset, timezone, etc.

        @param cp_reconnect: detect connections which have failed and reconnect
            (default C{False}). Failed connections may result in
            L{ConnectionLost} exceptions, which indicate the query may need to
            be re-sent.

        @param cp_good_sql: an sql query which should always succeed and change
            no state (default C{'select 1'})

        @param cp_reactor: use this reactor instead of the global reactor
            (added in Twisted 10.2).
        @type cp_reactor: L{IReactorCore} provider
        """
        self.dbapiName = dbapiName
        self.dbapi = reflect.namedModule(dbapiName)

        if getattr(self.dbapi, 'apilevel', None) != '2.0':
            log.msg('DB API module not DB API 2.0 compliant.')

        if getattr(self.dbapi, 'threadsafety', 0) < 1:
            log.msg('DB API module not sufficiently thread-safe.')

        reactor = connkw.pop('cp_reactor', None)
        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor

        self.connargs = connargs
        self.connkw = connkw

        for arg in self.CP_ARGS:
            cpArg = 'cp_%s' % (arg,)
            if cpArg in connkw:
                setattr(self, arg, connkw[cpArg])
                del connkw[cpArg]

        self.min = min(self.min, self.max)
        self.max = max(self.min, self.max)

        # All connections, hashed on thread id
        self.connections = {}

        # These are optional so import them here
        from twisted.python import threadpool
        from twisted.python import threadable

        self.threadID = threadable.getThreadID
        self.threadpool = threadpool.ThreadPool(self.min, self.max)
        self.startID = self._reactor.callWhenRunning(self._start)


    def _start(self):
        self.startID = None
        return self.start()


    def start(self):
        """
        Start the connection pool.

        If you are using the reactor normally, this function does *not*
        need to be called.
        """
        if not self.running:
            self.threadpool.start()
            self.shutdownID = self._reactor.addSystemEventTrigger(
                'during', 'shutdown', self.finalClose)
            self.running = True


    def runWithConnection(self, func, *args, **kw):
        """
        Execute a function with a database connection and return the result.

        @param func: A callable object of one argument which will be executed
            in a thread with a connection from the pool. It will be passed as
            its first argument a L{Connection} instance (whose interface is
            mostly identical to that of a connection object for your DB-API
            module of choice), and its results will be returned as a
            L{Deferred}. If the method raises an exception the transaction will
            be rolled back. Otherwise, the transaction will be committed.
            B{Note} that this function is B{not} run in the main thread: it
            must be threadsafe.

        @param *args: positional arguments to be passed to func

        @param **kw: keyword arguments to be passed to func

        @return: a L{Deferred} which will fire the return value of
            C{func(Transaction(...), *args, **kw)}, or a
            L{twisted.python.failure.Failure}.
        """
        from twisted.internet import reactor
        return threads.deferToThreadPool(reactor, self.threadpool,
                                         self._runWithConnection,
                                         func, *args, **kw)


    def _runWithConnection(self, func, *args, **kw):
        conn = self.connectionFactory(self)
        try:
            result = func(conn, *args, **kw)
            conn.commit()
            return result
        except:
            excType, excValue, excTraceback = sys.exc_info()
            try:
                conn.rollback()
            except:
                log.err(None, "Rollback failed")
            compat.reraise(excValue, excTraceback)


    def runInteraction(self, interaction, *args, **kw):
        """
        Interact with the database and return the result.

        The 'interaction' is a callable object which will be executed in a
        thread using a pooled connection. It will be passed an L{Transaction}
        object as an argument (whose interface is identical to that of the
        database cursor for your DB-API module of choice), and its results will
        be returned as a L{Deferred}. If running the method raises an
        exception, the transaction will be rolled back. If the method returns a
        value, the transaction will be committed.

        NOTE that the function you pass is *not* run in the main thread: you
        may have to worry about thread-safety in the function you pass to this
        if it tries to use non-local objects.

        @param interaction: a callable object whose first argument is an
            L{adbapi.Transaction}.

        @param *args: additional positional arguments to be passed to
            interaction

        @param **kw: keyword arguments to be passed to interaction

        @return: a Deferred which will fire the return value of
            C{interaction(Transaction(...), *args, **kw)}, or a
            L{twisted.python.failure.Failure}.
        """
        from twisted.internet import reactor
        return threads.deferToThreadPool(reactor, self.threadpool,
                                         self._runInteraction,
                                         interaction, *args, **kw)


    def runQuery(self, *args, **kw):
        """
        Execute an SQL query and return the result.

        A DB-API cursor will will be invoked with C{cursor.execute(*args,
        **kw)}. The exact nature of the arguments will depend on the specific
        flavor of DB-API being used, but the first argument in C{*args} be an
        SQL statement. The result of a subsequent C{cursor.fetchall()} will be
        fired to the L{Deferred} which is returned. If either the 'execute' or
        'fetchall' methods raise an exception, the transaction will be rolled
        back and a L{twisted.python.failure.Failure} returned.

        The C{*args} and C{**kw} arguments will be passed to the DB-API
        cursor's 'execute' method.

        @return: a L{Deferred} which will fire the return value of a DB-API
            cursor's 'fetchall' method, or a L{twisted.python.failure.Failure}.
        """
        return self.runInteraction(self._runQuery, *args, **kw)


    def runOperation(self, *args, **kw):
        """
        Execute an SQL query and return L{None}.

        A DB-API cursor will will be invoked with C{cursor.execute(*args,
        **kw)}. The exact nature of the arguments will depend on the specific
        flavor of DB-API being used, but the first argument in C{*args} will be
        an SQL statement. This method will not attempt to fetch any results
        from the query and is thus suitable for C{INSERT}, C{DELETE}, and other
        SQL statements which do not return values. If the 'execute' method
        raises an exception, the transaction will be rolled back and a
        L{Failure} returned.

        The C{*args} and C{*kw} arguments will be passed to the DB-API cursor's
        'execute' method.

        @return: a L{Deferred} which will fire with L{None} or a
            L{twisted.python.failure.Failure}.
        """
        return self.runInteraction(self._runOperation, *args, **kw)


    def close(self):
        """
        Close all pool connections and shutdown the pool.
        """
        if self.shutdownID:
            self._reactor.removeSystemEventTrigger(self.shutdownID)
            self.shutdownID = None
        if self.startID:
            self._reactor.removeSystemEventTrigger(self.startID)
            self.startID = None
        self.finalClose()


    def finalClose(self):
        """
        This should only be called by the shutdown trigger.
        """
        self.shutdownID = None
        self.threadpool.stop()
        self.running = False
        for conn in self.connections.values():
            self._close(conn)
        self.connections.clear()


    def connect(self):
        """
        Return a database connection when one becomes available.

        This method blocks and should be run in a thread from the internal
        threadpool. Don't call this method directly from non-threaded code.
        Using this method outside the external threadpool may exceed the
        maximum number of connections in the pool.

        @return: a database connection from the pool.
        """

        tid = self.threadID()
        conn = self.connections.get(tid)
        if conn is None:
            if self.noisy:
                log.msg('adbapi connecting: %s %s%s' % (self.dbapiName,
                                                        self.connargs or '',
                                                        self.connkw or ''))
            conn = self.dbapi.connect(*self.connargs, **self.connkw)
            if self.openfun != None:
                self.openfun(conn)
            self.connections[tid] = conn
        return conn


    def disconnect(self, conn):
        """
        Disconnect a database connection associated with this pool.

        Note: This function should only be used by the same thread which called
        L{ConnectionPool.connect}. As with C{connect}, this function is not
        used in normal non-threaded Twisted code.
        """
        tid = self.threadID()
        if conn is not self.connections.get(tid):
            raise Exception("wrong connection for thread")
        if conn is not None:
            self._close(conn)
            del self.connections[tid]


    def _close(self, conn):
        if self.noisy:
            log.msg('adbapi closing: %s' % (self.dbapiName,))
        try:
            conn.close()
        except:
            log.err(None, "Connection close failed")


    def _runInteraction(self, interaction, *args, **kw):
        conn = self.connectionFactory(self)
        trans = self.transactionFactory(self, conn)
        try:
            result = interaction(trans, *args, **kw)
            trans.close()
            conn.commit()
            return result
        except:
            excType, excValue, excTraceback = sys.exc_info()
            try:
                conn.rollback()
            except:
                log.err(None, "Rollback failed")
            compat.reraise(excValue, excTraceback)


    def _runQuery(self, trans, *args, **kw):
        trans.execute(*args, **kw)
        return trans.fetchall()


    def _runOperation(self, trans, *args, **kw):
        trans.execute(*args, **kw)


    def __getstate__(self):
        return {'dbapiName': self.dbapiName,
                'min': self.min,
                'max': self.max,
                'noisy': self.noisy,
                'reconnect': self.reconnect,
                'good_sql': self.good_sql,
                'connargs': self.connargs,
                'connkw': self.connkw}


    def __setstate__(self, state):
        self.__dict__ = state
        self.__init__(self.dbapiName, *self.connargs, **self.connkw)



__all__ = ['Transaction', 'ConnectionPool']
