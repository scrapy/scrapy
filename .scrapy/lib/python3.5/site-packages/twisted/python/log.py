# -*- test-case-name: twisted.test.test_log -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Logging and metrics infrastructure.
"""

from __future__ import division, absolute_import

import sys
import time
import warnings

from datetime import datetime

from zope.interface import Interface

from twisted.python.compat import unicode, _PY3
from twisted.python import context
from twisted.python import reflect
from twisted.python import util
from twisted.python import failure
from twisted.python.threadable import synchronize
from twisted.logger import (
    Logger as NewLogger, LogLevel as NewLogLevel,
    STDLibLogObserver as NewSTDLibLogObserver,
    LegacyLogObserverWrapper, LoggingFile, LogPublisher as NewPublisher,
    globalLogPublisher as newGlobalLogPublisher,
    globalLogBeginner as newGlobalLogBeginner,
)

from twisted.logger._global import LogBeginner
from twisted.logger._legacy import publishToNewObserver as _publishNew



class ILogContext:
    """
    Actually, this interface is just a synonym for the dictionary interface,
    but it serves as a key for the default information in a log.

    I do not inherit from C{Interface} because the world is a cruel place.
    """



class ILogObserver(Interface):
    """
    An observer which can do something with log events.

    Given that most log observers are actually bound methods, it's okay to not
    explicitly declare provision of this interface.
    """
    def __call__(eventDict):
        """
        Log an event.

        @type eventDict: C{dict} with C{str} keys.
        @param eventDict: A dictionary with arbitrary keys.  However, these
            keys are often available:
              - C{message}: A C{tuple} of C{str} containing messages to be
                logged.
              - C{system}: A C{str} which indicates the "system" which is
                generating this event.
              - C{isError}: A C{bool} indicating whether this event represents
                an error.
              - C{failure}: A L{failure.Failure} instance
              - C{why}: Used as header of the traceback in case of errors.
              - C{format}: A string format used in place of C{message} to
                customize the event.  The intent is for the observer to format
                a message by doing something like C{format % eventDict}.
        """



context.setDefault(ILogContext,
                   {"system": "-"})


def callWithContext(ctx, func, *args, **kw):
    newCtx = context.get(ILogContext).copy()
    newCtx.update(ctx)
    return context.call({ILogContext: newCtx}, func, *args, **kw)



def callWithLogger(logger, func, *args, **kw):
    """
    Utility method which wraps a function in a try:/except:, logs a failure if
    one occurs, and uses the system's logPrefix.
    """
    try:
        lp = logger.logPrefix()
    except KeyboardInterrupt:
        raise
    except:
        lp = '(buggy logPrefix method)'
        err(system=lp)
    try:
        return callWithContext({"system": lp}, func, *args, **kw)
    except KeyboardInterrupt:
        raise
    except:
        err(system=lp)



def err(_stuff=None, _why=None, **kw):
    """
    Write a failure to the log.

    The C{_stuff} and C{_why} parameters use an underscore prefix to lessen
    the chance of colliding with a keyword argument the application wishes
    to pass.  It is intended that they be supplied with arguments passed
    positionally, not by keyword.

    @param _stuff: The failure to log.  If C{_stuff} is L{None} a new
        L{Failure} will be created from the current exception state.  If
        C{_stuff} is an C{Exception} instance it will be wrapped in a
        L{Failure}.
    @type _stuff: L{None}, C{Exception}, or L{Failure}.

    @param _why: The source of this failure.  This will be logged along with
        C{_stuff} and should describe the context in which the failure
        occurred.
    @type _why: C{str}
    """
    if _stuff is None:
        _stuff = failure.Failure()
    if isinstance(_stuff, failure.Failure):
        msg(failure=_stuff, why=_why, isError=1, **kw)
    elif isinstance(_stuff, Exception):
        msg(failure=failure.Failure(_stuff), why=_why, isError=1, **kw)
    else:
        msg(repr(_stuff), why=_why, isError=1, **kw)

deferr = err


class Logger:
    """
    This represents a class which may 'own' a log. Used by subclassing.
    """
    def logPrefix(self):
        """
        Override this method to insert custom logging behavior.  Its
        return value will be inserted in front of every line.  It may
        be called more times than the number of output lines.
        """
        return '-'



class LogPublisher:
    """
    Class for singleton log message publishing.
    """

    synchronized = ['msg']


    def __init__(self, observerPublisher=None, publishPublisher=None,
                 logBeginner=None, warningsModule=warnings):
        if publishPublisher is None:
            publishPublisher = NewPublisher()
            if observerPublisher is None:
                observerPublisher = publishPublisher
        if observerPublisher is None:
            observerPublisher = NewPublisher()
        self._observerPublisher = observerPublisher
        self._publishPublisher = publishPublisher
        self._legacyObservers = []
        if logBeginner is None:
            # This default behavior is really only used for testing.
            beginnerPublisher = NewPublisher()
            beginnerPublisher.addObserver(observerPublisher)
            logBeginner = LogBeginner(beginnerPublisher, NullFile(), sys,
                                      warnings)
        self._logBeginner = logBeginner
        self._warningsModule = warningsModule
        self._oldshowwarning = warningsModule.showwarning
        self.showwarning = self._logBeginner.showwarning


    @property
    def observers(self):
        """
        Property returning all observers registered on this L{LogPublisher}.

        @return: observers previously added with L{LogPublisher.addObserver}
        @rtype: L{list} of L{callable}
        """
        return [x.legacyObserver for x in self._legacyObservers]


    def _startLogging(self, other, setStdout):
        """
        Begin logging to the L{LogBeginner} associated with this
        L{LogPublisher}.

        @param other: the observer to log to.
        @type other: L{LogBeginner}

        @param setStdout: if true, send standard I/O to the observer as well.
        @type setStdout: L{bool}
        """
        wrapped = LegacyLogObserverWrapper(other)
        self._legacyObservers.append(wrapped)
        self._logBeginner.beginLoggingTo([wrapped], True, setStdout)


    def _stopLogging(self):
        """
        Clean-up hook for fixing potentially global state.  Only for testing of
        this module itself.  If you want less global state, use the new
        warnings system in L{twisted.logger}.
        """
        if self._warningsModule.showwarning == self.showwarning:
            self._warningsModule.showwarning = self._oldshowwarning


    def addObserver(self, other):
        """
        Add a new observer.

        @type other: Provider of L{ILogObserver}
        @param other: A callable object that will be called with each new log
            message (a dict).
        """
        wrapped = LegacyLogObserverWrapper(other)
        self._legacyObservers.append(wrapped)
        self._observerPublisher.addObserver(wrapped)


    def removeObserver(self, other):
        """
        Remove an observer.
        """
        for observer in self._legacyObservers:
            if observer.legacyObserver == other:
                self._legacyObservers.remove(observer)
                self._observerPublisher.removeObserver(observer)
                break


    def msg(self, *message, **kw):
        """
        Log a new message.

        The message should be a native string, i.e. bytes on Python 2 and
        Unicode on Python 3. For compatibility with both use the native string
        syntax, for example::

            >>> log.msg('Hello, world.')

        You MUST avoid passing in Unicode on Python 2, and the form::

            >>> log.msg('Hello ', 'world.')

        This form only works (sometimes) by accident.

        Keyword arguments will be converted into items in the event
        dict that is passed to L{ILogObserver} implementations.
        Each implementation, in turn, can define keys that are used
        by it specifically, in addition to common keys listed at
        L{ILogObserver.__call__}.

        For example, to set the C{system} parameter while logging
        a message::

        >>> log.msg('Started', system='Foo')

        """
        actualEventDict = (context.get(ILogContext) or {}).copy()
        actualEventDict.update(kw)
        actualEventDict['message'] = message
        actualEventDict['time'] = time.time()
        if "isError" not in actualEventDict:
            actualEventDict["isError"] = 0

        _publishNew(self._publishPublisher, actualEventDict, textFromEventDict)


synchronize(LogPublisher)



if 'theLogPublisher' not in globals():
    def _actually(something):
        """
        A decorator that returns its argument rather than the thing it is
        decorating.

        This allows the documentation generator to see an alias for a method or
        constant as an object with a docstring and thereby document it and
        allow references to it statically.

        @param something: An object to create an alias for.
        @type something: L{object}

        @return: a 1-argument callable that returns C{something}
        @rtype: L{object}
        """
        def decorate(thingWithADocstring):
            return something
        return decorate

    theLogPublisher = LogPublisher(
        observerPublisher=newGlobalLogPublisher,
        publishPublisher=newGlobalLogPublisher,
        logBeginner=newGlobalLogBeginner,
    )


    @_actually(theLogPublisher.addObserver)
    def addObserver(observer):
        """
        Add a log observer to the global publisher.

        @see: L{LogPublisher.addObserver}

        @param observer: a log observer
        @type observer: L{callable}
        """


    @_actually(theLogPublisher.removeObserver)
    def removeObserver(observer):
        """
        Remove a log observer from the global publisher.

        @see: L{LogPublisher.removeObserver}

        @param observer: a log observer previously added with L{addObserver}
        @type observer: L{callable}
        """


    @_actually(theLogPublisher.msg)
    def msg(*message, **event):
        """
        Publish a message to the global log publisher.

        @see: L{LogPublisher.msg}

        @param message: the log message
        @type message: C{tuple} of L{str} (native string)

        @param event: fields for the log event
        @type event: L{dict} mapping L{str} (native string) to L{object}
        """


    @_actually(theLogPublisher.showwarning)
    def showwarning():
        """
        Publish a Python warning through the global log publisher.

        @see: L{LogPublisher.showwarning}
        """



def _safeFormat(fmtString, fmtDict):
    """
    Try to format a string, swallowing all errors to always return a string.

    @note: For backward-compatibility reasons, this function ensures that it
        returns a native string, meaning C{bytes} in Python 2 and C{unicode} in
        Python 3.

    @param fmtString: a C{%}-format string

    @param fmtDict: string formatting arguments for C{fmtString}

    @return: A native string, formatted from C{fmtString} and C{fmtDict}.
    @rtype: L{str}
    """
    # There's a way we could make this if not safer at least more
    # informative: perhaps some sort of str/repr wrapper objects
    # could be wrapped around the things inside of C{fmtDict}. That way
    # if the event dict contains an object with a bad __repr__, we
    # can only cry about that individual object instead of the
    # entire event dict.
    try:
        text = fmtString % fmtDict
    except KeyboardInterrupt:
        raise
    except:
        try:
            text = ('Invalid format string or unformattable object in '
                    'log message: %r, %s' % (fmtString, fmtDict))
        except:
            try:
                text = ('UNFORMATTABLE OBJECT WRITTEN TO LOG with fmt %r, '
                        'MESSAGE LOST' % (fmtString,))
            except:
                text = ('PATHOLOGICAL ERROR IN BOTH FORMAT STRING AND '
                        'MESSAGE DETAILS, MESSAGE LOST')

    # Return a native string
    if _PY3:
        if isinstance(text, bytes):
            text = text.decode("utf-8")
    else:
        if isinstance(text, unicode):
            text = text.encode("utf-8")

    return text



def textFromEventDict(eventDict):
    """
    Extract text from an event dict passed to a log observer. If it cannot
    handle the dict, it returns None.

    The possible keys of eventDict are:
     - C{message}: by default, it holds the final text. It's required, but can
       be empty if either C{isError} or C{format} is provided (the first
       having the priority).
     - C{isError}: boolean indicating the nature of the event.
     - C{failure}: L{failure.Failure} instance, required if the event is an
       error.
     - C{why}: if defined, used as header of the traceback in case of errors.
     - C{format}: string format used in place of C{message} to customize
       the event. It uses all keys present in C{eventDict} to format
       the text.
    Other keys will be used when applying the C{format}, or ignored.
    """
    edm = eventDict['message']
    if not edm:
        if eventDict['isError'] and 'failure' in eventDict:
            why = eventDict.get('why')
            if why:
                why = reflect.safe_str(why)
            else:
                why = 'Unhandled Error'
            try:
                traceback = eventDict['failure'].getTraceback()
            except Exception as e:
                traceback = '(unable to obtain traceback): ' + str(e)
            text = (why + '\n' + traceback)
        elif 'format' in eventDict:
            text = _safeFormat(eventDict['format'], eventDict)
        else:
            # We don't know how to log this
            return None
    else:
        text = ' '.join(map(reflect.safe_str, edm))
    return text



class _GlobalStartStopMixIn:
    """
    Mix-in for global log observers that can start and stop.
    """

    def start(self):
        """
        Start observing log events.
        """
        addObserver(self.emit)


    def stop(self):
        """
        Stop observing log events.
        """
        removeObserver(self.emit)



class FileLogObserver(_GlobalStartStopMixIn):
    """
    Log observer that writes to a file-like object.

    @type timeFormat: C{str} or L{None}
    @ivar timeFormat: If not L{None}, the format string passed to strftime().
    """

    timeFormat = None

    def __init__(self, f):
        # Compatibility
        self.write = f.write
        self.flush = f.flush


    def getTimezoneOffset(self, when):
        """
        Return the current local timezone offset from UTC.

        @type when: C{int}
        @param when: POSIX (ie, UTC) timestamp for which to find the offset.

        @rtype: C{int}
        @return: The number of seconds offset from UTC.  West is positive,
        east is negative.
        """
        offset = datetime.utcfromtimestamp(when) - datetime.fromtimestamp(when)
        return offset.days * (60 * 60 * 24) + offset.seconds


    def formatTime(self, when):
        """
        Format the given UTC value as a string representing that time in the
        local timezone.

        By default it's formatted as an ISO8601-like string (ISO8601 date and
        ISO8601 time separated by a space). It can be customized using the
        C{timeFormat} attribute, which will be used as input for the underlying
        L{datetime.datetime.strftime} call.

        @type when: C{int}
        @param when: POSIX (ie, UTC) timestamp for which to find the offset.

        @rtype: C{str}
        """
        if self.timeFormat is not None:
            return datetime.fromtimestamp(when).strftime(self.timeFormat)

        tzOffset = -self.getTimezoneOffset(when)
        when = datetime.utcfromtimestamp(when + tzOffset)
        tzHour = abs(int(tzOffset / 60 / 60))
        tzMin = abs(int(tzOffset / 60 % 60))
        if tzOffset < 0:
            tzSign = '-'
        else:
            tzSign = '+'
        return '%d-%02d-%02d %02d:%02d:%02d%s%02d%02d' % (
            when.year, when.month, when.day,
            when.hour, when.minute, when.second,
            tzSign, tzHour, tzMin)


    def emit(self, eventDict):
        """
        Format the given log event as text and write it to the output file.

        @param eventDict: a log event
        @type eventDict: L{dict} mapping L{str} (native string) to L{object}
        """
        text = textFromEventDict(eventDict)
        if text is None:
            return

        timeStr = self.formatTime(eventDict["time"])
        fmtDict = {
            "system": eventDict["system"],
            "text": text.replace("\n", "\n\t")
        }
        msgStr = _safeFormat("[%(system)s] %(text)s\n", fmtDict)

        util.untilConcludes(self.write, timeStr + " " + msgStr)
        util.untilConcludes(self.flush)  # Hoorj!



class PythonLoggingObserver(_GlobalStartStopMixIn, object):
    """
    Output twisted messages to Python standard library L{logging} module.

    WARNING: specific logging configurations (example: network) can lead to
    a blocking system. Nothing is done here to prevent that, so be sure to not
    use this: code within Twisted, such as twisted.web, assumes that logging
    does not block.
    """

    def __init__(self, loggerName="twisted"):
        """
        @param loggerName: identifier used for getting logger.
        @type loggerName: C{str}
        """
        self._newObserver = NewSTDLibLogObserver(loggerName)


    def emit(self, eventDict):
        """
        Receive a twisted log entry, format it and bridge it to python.

        By default the logging level used is info; log.err produces error
        level, and you can customize the level by using the C{logLevel} key::

            >>> log.msg('debugging', logLevel=logging.DEBUG)
        """
        if 'log_format' in eventDict:
            _publishNew(self._newObserver, eventDict, textFromEventDict)



class StdioOnnaStick:
    """
    Class that pretends to be stdout/err, and turns writes into log messages.

    @ivar isError: boolean indicating whether this is stderr, in which cases
                   log messages will be logged as errors.

    @ivar encoding: unicode encoding used to encode any unicode strings
                    written to this object.
    """

    closed = 0
    softspace = 0
    mode = 'wb'
    name = '<stdio (log)>'

    def __init__(self, isError=0, encoding=None):
        self.isError = isError
        if encoding is None:
            encoding = sys.getdefaultencoding()
        self.encoding = encoding
        self.buf = ''


    def close(self):
        pass


    def fileno(self):
        return -1


    def flush(self):
        pass


    def read(self):
        raise IOError("can't read from the log!")

    readline = read
    readlines = read
    seek = read
    tell = read


    def write(self, data):
        if not _PY3 and isinstance(data, unicode):
            data = data.encode(self.encoding)
        d = (self.buf + data).split('\n')
        self.buf = d[-1]
        messages = d[0:-1]
        for message in messages:
            msg(message, printed=1, isError=self.isError)


    def writelines(self, lines):
        for line in lines:
            if not _PY3 and isinstance(line, unicode):
                line = line.encode(self.encoding)
            msg(line, printed=1, isError=self.isError)



def startLogging(file, *a, **kw):
    """
    Initialize logging to a specified file.

    @return: A L{FileLogObserver} if a new observer is added, None otherwise.
    """
    if isinstance(file, LoggingFile):
        return
    flo = FileLogObserver(file)
    startLoggingWithObserver(flo.emit, *a, **kw)
    return flo



def startLoggingWithObserver(observer, setStdout=1):
    """
    Initialize logging to a specified observer. If setStdout is true
    (defaults to yes), also redirect sys.stdout and sys.stderr
    to the specified file.
    """
    theLogPublisher._startLogging(observer, setStdout)
    msg("Log opened.")



class NullFile:
    """
    A file-like object that discards everything.
    """
    softspace = 0

    def read(self):
        """
        Do nothing.
        """


    def write(self, bytes):
        """
        Do nothing.

        @param bytes: data
        @type bytes: L{bytes}
        """


    def flush(self):
        """
        Do nothing.
        """


    def close(self):
        """
        Do nothing.
        """



def discardLogs():
    """
    Discard messages logged via the global C{logfile} object.
    """
    global logfile
    logfile = NullFile()



# Prevent logfile from being erased on reload.  This only works in cpython.
if 'logfile' not in globals():
    logfile = LoggingFile(logger=NewLogger(),
                          level=NewLogLevel.info,
                          encoding=getattr(sys.stdout, "encoding", None))
    logerr = LoggingFile(logger=NewLogger(),
                         level=NewLogLevel.error,
                         encoding=getattr(sys.stderr, "encoding", None))



class DefaultObserver(_GlobalStartStopMixIn):
    """
    Default observer.

    Will ignore all non-error messages and send error messages to sys.stderr.
    Will be removed when startLogging() is called for the first time.
    """
    stderr = sys.stderr

    def emit(self, eventDict):
        """
        Emit an event dict.

        @param eventDict: an event dict
        @type eventDict: dict
        """
        if eventDict["isError"]:
            text = textFromEventDict(eventDict)
            self.stderr.write(text)
            self.stderr.flush()



if 'defaultObserver' not in globals():
    defaultObserver = DefaultObserver()
