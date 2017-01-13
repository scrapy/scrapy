# -*- test-case-name: twisted.logger.test.test_logger -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Logger class.
"""

from time import time

from twisted.python.compat import currentframe
from twisted.python.failure import Failure
from ._levels import InvalidLogLevelError, LogLevel



class Logger(object):
    """
    A L{Logger} emits log messages to an observer.  You should instantiate it
    as a class or module attribute, as documented in L{this module's
    documentation <twisted.logger>}.
    """

    @staticmethod
    def _namespaceFromCallingContext():
        """
        Derive a namespace from the module containing the caller's caller.

        @return: the fully qualified python name of a module.
        @rtype: L{str} (native string)
        """
        return currentframe(2).f_globals["__name__"]


    def __init__(self, namespace=None, source=None, observer=None):
        """
        @param namespace: The namespace for this logger.  Uses a dotted
            notation, as used by python modules.  If not L{None}, then the name
            of the module of the caller is used.
        @type namespace: L{str} (native string)

        @param source: The object which is emitting events via this
            logger; this is automatically set on instances of a class
            if this L{Logger} is an attribute of that class.
        @type source: L{object}

        @param observer: The observer that this logger will send events to.
            If L{None}, use the L{global log publisher <globalLogPublisher>}.
        @type observer: L{ILogObserver}
        """
        if namespace is None:
            namespace = self._namespaceFromCallingContext()

        self.namespace = namespace
        self.source = source

        if observer is None:
            from ._global import globalLogPublisher
            self.observer = globalLogPublisher
        else:
            self.observer = observer


    def __get__(self, oself, type=None):
        """
        When used as a descriptor, i.e.::

            # File: athing.py
            class Something(object):
                log = Logger()
                def hello(self):
                    self.log.info("Hello")

        a L{Logger}'s namespace will be set to the name of the class it is
        declared on.  In the above example, the namespace would be
        C{athing.Something}.

        Additionally, its source will be set to the actual object referring to
        the L{Logger}.  In the above example, C{Something.log.source} would be
        C{Something}, and C{Something().log.source} would be an instance of
        C{Something}.
        """
        if oself is None:
            source = type
        else:
            source = oself

        return self.__class__(
            ".".join([type.__module__, type.__name__]),
            source,
            observer=self.observer,
        )


    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.namespace)


    def emit(self, level, format=None, **kwargs):
        """
        Emit a log event to all log observers at the given level.

        @param level: a L{LogLevel}

        @param format: a message format using new-style (PEP 3101)
            formatting.  The logging event (which is a L{dict}) is
            used to render this format string.

        @param kwargs: additional key/value pairs to include in the event.
            Note that values which are later mutated may result in
            non-deterministic behavior from observers that schedule work for
            later execution.
        """
        if level not in LogLevel.iterconstants():
            self.failure(
                "Got invalid log level {invalidLevel!r} in {logger}.emit().",
                Failure(InvalidLogLevelError(level)),
                invalidLevel=level,
                logger=self,
            )
            return

        event = kwargs
        event.update(
            log_logger=self, log_level=level, log_namespace=self.namespace,
            log_source=self.source, log_format=format, log_time=time(),
        )

        if "log_trace" in event:
            event["log_trace"].append((self, self.observer))

        self.observer(event)


    def failure(self, format, failure=None, level=LogLevel.critical, **kwargs):
        """
        Log a failure and emit a traceback.

        For example::

            try:
                frob(knob)
            except Exception:
                log.failure("While frobbing {knob}", knob=knob)

        or::

            d = deferredFrob(knob)
            d.addErrback(lambda f: log.failure, "While frobbing {knob}",
                         f, knob=knob)

        This method is generally meant to capture unexpected exceptions in
        code; an exception that is caught and handled somehow should be logged,
        if appropriate, via L{Logger.error} instead.  If some unknown exception
        occurs and your code doesn't know how to handle it, as in the above
        example, then this method provides a means to describe the failure in
        nerd-speak.  This is done at L{LogLevel.critical} by default, since no
        corrective guidance can be offered to an user/administrator, and the
        impact of the condition is unknown.

        @param format: a message format using new-style (PEP 3101) formatting.
            The logging event (which is a L{dict}) is used to render this
            format string.

        @param failure: a L{Failure} to log.  If L{None}, a L{Failure} is
            created from the exception in flight.

        @param level: a L{LogLevel} to use.

        @param kwargs: additional key/value pairs to include in the event.
            Note that values which are later mutated may result in
            non-deterministic behavior from observers that schedule work for
            later execution.
        """
        if failure is None:
            failure = Failure()

        self.emit(level, format, log_failure=failure, **kwargs)


    def debug(self, format=None, **kwargs):
        """
        Emit a log event at log level L{LogLevel.debug}.

        @param format: a message format using new-style (PEP 3101) formatting.
            The logging event (which is a L{dict}) is used to render this
            format string.

        @param kwargs: additional key/value pairs to include in the event.
            Note that values which are later mutated may result in
            non-deterministic behavior from observers that schedule work for
            later execution.
        """
        self.emit(LogLevel.debug, format, **kwargs)


    def info(self, format=None, **kwargs):
        """
        Emit a log event at log level L{LogLevel.info}.

        @param format: a message format using new-style (PEP 3101) formatting.
            The logging event (which is a L{dict}) is used to render this
            format string.

        @param kwargs: additional key/value pairs to include in the event.
            Note that values which are later mutated may result in
            non-deterministic behavior from observers that schedule work for
            later execution.
        """
        self.emit(LogLevel.info, format, **kwargs)


    def warn(self, format=None, **kwargs):
        """
        Emit a log event at log level L{LogLevel.warn}.

        @param format: a message format using new-style (PEP 3101) formatting.
            The logging event (which is a L{dict}) is used to render this
            format string.

        @param kwargs: additional key/value pairs to include in the event.
            Note that values which are later mutated may result in
            non-deterministic behavior from observers that schedule work for
            later execution.
        """
        self.emit(LogLevel.warn, format, **kwargs)


    def error(self, format=None, **kwargs):
        """
        Emit a log event at log level L{LogLevel.error}.

        @param format: a message format using new-style (PEP 3101) formatting.
            The logging event (which is a L{dict}) is used to render this
            format string.

        @param kwargs: additional key/value pairs to include in the event.
            Note that values which are later mutated may result in
            non-deterministic behavior from observers that schedule work for
            later execution.
        """
        self.emit(LogLevel.error, format, **kwargs)


    def critical(self, format=None, **kwargs):
        """
        Emit a log event at log level L{LogLevel.critical}.

        @param format: a message format using new-style (PEP 3101) formatting.
            The logging event (which is a L{dict}) is used to render this
            format string.

        @param kwargs: additional key/value pairs to include in the event.
            Note that values which are later mutated may result in
            non-deterministic behavior from observers that schedule work for
            later execution.
        """
        self.emit(LogLevel.critical, format, **kwargs)



_log = Logger()
_loggerFor = lambda obj:_log.__get__(obj, obj.__class__)
