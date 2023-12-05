# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Logger interfaces.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from zope.interface import Interface

if TYPE_CHECKING:
    from ._logger import Logger


LogEvent = Dict[str, Any]
LogTrace = List[Tuple["Logger", "ILogObserver"]]


class ILogObserver(Interface):
    """
    An observer which can handle log events.

    Unlike most interfaces within Twisted, an L{ILogObserver} I{must be
    thread-safe}.  Log observers may be called indiscriminately from many
    different threads, as any thread may wish to log a message at any time.
    """

    def __call__(event: LogEvent) -> None:
        """
        Log an event.

        @param event: A dictionary with arbitrary keys as defined by the
            application emitting logging events, as well as keys added by the
            logging system.  The logging system reserves the right to set any
            key beginning with the prefix C{"log_"}; applications should not
            use any key so named.  Currently, the following keys are used by
            the logging system in some way, if they are present (they are all
            optional):

                - C{"log_format"}: a PEP-3101-style format string which draws
                  upon the keys in the event as its values, used to format the
                  event for human consumption.

                - C{"log_flattened"}: a dictionary mapping keys derived from
                  the names and format values used in the C{"log_format"}
                  string to their values.  This is used to preserve some
                  structured information for use with
                  L{twisted.logger.extractField}.

                - C{"log_trace"}: A L{list} designed to capture information
                  about which L{LogPublisher}s have observed the event.

                - C{"log_level"}: a L{log level
                  <twisted.logger.LogLevel>} constant, indicating the
                  importance of and audience for this event.

                - C{"log_namespace"}: a namespace for the emitter of the event,
                  given as a L{str}.

                - C{"log_system"}: a string indicating the network event or
                  method call which resulted in the message being logged.
        """
