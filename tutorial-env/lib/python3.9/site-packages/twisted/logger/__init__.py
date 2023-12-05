# -*- test-case-name: twisted.logger.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted Logger: Classes and functions to do granular logging.

Example usage in a module C{some.module}::

    from twisted.logger import Logger
    log = Logger()

    def handleData(data):
        log.debug("Got data: {data!r}.", data=data)

Or in a class::

    from twisted.logger import Logger

    class Foo:
        log = Logger()

        def oops(self, data):
            self.log.error("Oops! Invalid data from server: {data!r}",
                           data=data)

C{Logger}s have namespaces, for which logging can be configured independently.
Namespaces may be specified by passing in a C{namespace} argument to L{Logger}
when instantiating it, but if none is given, the logger will derive its own
namespace by using the module name of the callable that instantiated it, or, in
the case of a class, by using the fully qualified name of the class.

In the first example above, the namespace would be C{some.module}, and in the
second example, it would be C{some.module.Foo}.

@var globalLogPublisher: The L{LogPublisher} that all L{Logger} instances that
    are not otherwise parameterized will publish events to by default.
@var globalLogBeginner: The L{LogBeginner} used to activate the main log
    observer, whether it's a log file, or an observer pointing at stderr.
"""

__all__ = [
    # From ._levels
    "InvalidLogLevelError",
    "LogLevel",
    # From ._format
    "formatEvent",
    "formatEventAsClassicLogText",
    "formatTime",
    "timeFormatRFC3339",
    "eventAsText",
    # From ._flatten
    "extractField",
    # From ._interfaces
    "ILogObserver",
    "LogEvent",
    # From ._logger
    "Logger",
    "_loggerFor",
    # From ._observer
    "LogPublisher",
    # From ._buffer
    "LimitedHistoryLogObserver",
    # From ._file
    "FileLogObserver",
    "textFileLogObserver",
    # From ._filter
    "PredicateResult",
    "ILogFilterPredicate",
    "FilteringLogObserver",
    "LogLevelFilterPredicate",
    # From ._stdlib
    "STDLibLogObserver",
    # From ._io
    "LoggingFile",
    # From ._legacy
    "LegacyLogObserverWrapper",
    # From ._global
    "globalLogPublisher",
    "globalLogBeginner",
    "LogBeginner",
    # From ._json
    "eventAsJSON",
    "eventFromJSON",
    "jsonFileLogObserver",
    "eventsFromJSONLogFile",
    # From ._capture
    "capturedLogs",
]

from ._levels import InvalidLogLevelError, LogLevel

from ._flatten import extractField

from ._format import (
    formatEvent,
    formatEventAsClassicLogText,
    formatTime,
    timeFormatRFC3339,
    eventAsText,
)

from ._interfaces import ILogObserver, LogEvent

from ._logger import Logger, _loggerFor

from ._observer import LogPublisher

from ._buffer import LimitedHistoryLogObserver

from ._file import FileLogObserver, textFileLogObserver

from ._filter import (
    PredicateResult,
    ILogFilterPredicate,
    FilteringLogObserver,
    LogLevelFilterPredicate,
)

from ._stdlib import STDLibLogObserver

from ._io import LoggingFile

from ._legacy import LegacyLogObserverWrapper

from ._global import globalLogPublisher, globalLogBeginner, LogBeginner

from ._json import (
    eventAsJSON,
    eventFromJSON,
    jsonFileLogObserver,
    eventsFromJSONLogFile,
)

from ._capture import capturedLogs
