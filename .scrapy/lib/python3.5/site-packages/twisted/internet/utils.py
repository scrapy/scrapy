# -*- test-case-name: twisted.test.test_iutils -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Utility methods.
"""

from __future__ import division, absolute_import

import sys, warnings
from functools import wraps

from twisted.internet import protocol, defer
from twisted.python import failure
from twisted.python.compat import reraise

from io import BytesIO



def _callProtocolWithDeferred(protocol, executable, args, env, path, reactor=None):
    if reactor is None:
        from twisted.internet import reactor

    d = defer.Deferred()
    p = protocol(d)
    reactor.spawnProcess(p, executable, (executable,)+tuple(args), env, path)
    return d



class _UnexpectedErrorOutput(IOError):
    """
    Standard error data was received where it was not expected.  This is a
    subclass of L{IOError} to preserve backward compatibility with the previous
    error behavior of L{getProcessOutput}.

    @ivar processEnded: A L{Deferred} which will fire when the process which
        produced the data on stderr has ended (exited and all file descriptors
        closed).
    """

    def __init__(self, text, processEnded):
        IOError.__init__(self, "got stderr: %r" % (text,))
        self.processEnded = processEnded



class _BackRelay(protocol.ProcessProtocol):
    """
    Trivial protocol for communicating with a process and turning its output
    into the result of a L{Deferred}.

    @ivar deferred: A L{Deferred} which will be called back with all of stdout
        and, if C{errortoo} is true, all of stderr as well (mixed together in
        one string).  If C{errortoo} is false and any bytes are received over
        stderr, this will fire with an L{_UnexpectedErrorOutput} instance and
        the attribute will be set to L{None}.

    @ivar onProcessEnded: If C{errortoo} is false and bytes are received over
        stderr, this attribute will refer to a L{Deferred} which will be called
        back when the process ends.  This C{Deferred} is also associated with
        the L{_UnexpectedErrorOutput} which C{deferred} fires with earlier in
        this case so that users can determine when the process has actually
        ended, in addition to knowing when bytes have been received via stderr.
    """

    def __init__(self, deferred, errortoo=0):
        self.deferred = deferred
        self.s = BytesIO()
        if errortoo:
            self.errReceived = self.errReceivedIsGood
        else:
            self.errReceived = self.errReceivedIsBad

    def errReceivedIsBad(self, text):
        if self.deferred is not None:
            self.onProcessEnded = defer.Deferred()
            err = _UnexpectedErrorOutput(text, self.onProcessEnded)
            self.deferred.errback(failure.Failure(err))
            self.deferred = None
            self.transport.loseConnection()

    def errReceivedIsGood(self, text):
        self.s.write(text)

    def outReceived(self, text):
        self.s.write(text)

    def processEnded(self, reason):
        if self.deferred is not None:
            self.deferred.callback(self.s.getvalue())
        elif self.onProcessEnded is not None:
            self.onProcessEnded.errback(reason)



def getProcessOutput(executable, args=(), env={}, path=None, reactor=None,
                     errortoo=0):
    """
    Spawn a process and return its output as a deferred returning a L{bytes}.

    @param executable: The file name to run and get the output of - the
                       full path should be used.

    @param args: the command line arguments to pass to the process; a
                 sequence of strings. The first string should B{NOT} be the
                 executable's name.

    @param env: the environment variables to pass to the processs; a
                dictionary of strings.

    @param path: the path to run the subprocess in - defaults to the
                 current directory.

    @param reactor: the reactor to use - defaults to the default reactor

    @param errortoo: If true, include stderr in the result.  If false, if
        stderr is received the returned L{Deferred} will errback with an
        L{IOError} instance with a C{processEnded} attribute.  The
        C{processEnded} attribute refers to a L{Deferred} which fires when the
        executed process ends.
    """
    return _callProtocolWithDeferred(lambda d:
                                        _BackRelay(d, errortoo=errortoo),
                                     executable, args, env, path,
                                     reactor)


class _ValueGetter(protocol.ProcessProtocol):

    def __init__(self, deferred):
        self.deferred = deferred

    def processEnded(self, reason):
        self.deferred.callback(reason.value.exitCode)


def getProcessValue(executable, args=(), env={}, path=None, reactor=None):
    """Spawn a process and return its exit code as a Deferred."""
    return _callProtocolWithDeferred(_ValueGetter, executable, args, env, path,
                                    reactor)


class _EverythingGetter(protocol.ProcessProtocol):

    def __init__(self, deferred):
        self.deferred = deferred
        self.outBuf = BytesIO()
        self.errBuf = BytesIO()
        self.outReceived = self.outBuf.write
        self.errReceived = self.errBuf.write

    def processEnded(self, reason):
        out = self.outBuf.getvalue()
        err = self.errBuf.getvalue()
        e = reason.value
        code = e.exitCode
        if e.signal:
            self.deferred.errback((out, err, e.signal))
        else:
            self.deferred.callback((out, err, code))


def getProcessOutputAndValue(executable, args=(), env={}, path=None,
                             reactor=None):
    """Spawn a process and returns a Deferred that will be called back with
    its output (from stdout and stderr) and it's exit code as (out, err, code)
    If a signal is raised, the Deferred will errback with the stdout and
    stderr up to that point, along with the signal, as (out, err, signalNum)
    """
    return _callProtocolWithDeferred(_EverythingGetter, executable, args, env, path,
                                    reactor)


def _resetWarningFilters(passthrough, addedFilters):
    for f in addedFilters:
        try:
            warnings.filters.remove(f)
        except ValueError:
            pass
    return passthrough


def runWithWarningsSuppressed(suppressedWarnings, f, *a, **kw):
    """Run the function C{f}, but with some warnings suppressed.

    @param suppressedWarnings: A list of arguments to pass to filterwarnings.
                               Must be a sequence of 2-tuples (args, kwargs).
    @param f: A callable, followed by its arguments and keyword arguments
    """
    for args, kwargs in suppressedWarnings:
        warnings.filterwarnings(*args, **kwargs)
    addedFilters = warnings.filters[:len(suppressedWarnings)]
    try:
        result = f(*a, **kw)
    except:
        exc_info = sys.exc_info()
        _resetWarningFilters(None, addedFilters)
        reraise(exc_info[1], exc_info[2])
    else:
        if isinstance(result, defer.Deferred):
            result.addBoth(_resetWarningFilters, addedFilters)
        else:
            _resetWarningFilters(None, addedFilters)
        return result


def suppressWarnings(f, *suppressedWarnings):
    """
    Wrap C{f} in a callable which suppresses the indicated warnings before
    invoking C{f} and unsuppresses them afterwards.  If f returns a Deferred,
    warnings will remain suppressed until the Deferred fires.
    """
    @wraps(f)
    def warningSuppressingWrapper(*a, **kw):
        return runWithWarningsSuppressed(suppressedWarnings, f, *a, **kw)
    return warningSuppressingWrapper


__all__ = [
    "runWithWarningsSuppressed", "suppressWarnings",
    "getProcessOutput", "getProcessValue", "getProcessOutputAndValue",
    ]
