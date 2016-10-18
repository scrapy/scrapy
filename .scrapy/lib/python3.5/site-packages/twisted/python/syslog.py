# -*- test-case-name: twisted.python.test.test_syslog -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Classes and utility functions for integrating Twisted and syslog.

You probably want to call L{startLogging}.
"""

syslog = __import__('syslog')

from twisted.python import log

# These defaults come from the Python syslog docs.
DEFAULT_OPTIONS = 0
DEFAULT_FACILITY = syslog.LOG_USER



class SyslogObserver:
    """
    A log observer for logging to syslog.

    See L{twisted.python.log} for context.

    This logObserver will automatically use LOG_ALERT priority for logged
    failures (such as from C{log.err()}), but you can use any priority and
    facility by setting the 'C{syslogPriority}' and 'C{syslogFacility}' keys in
    the event dict.
    """
    openlog = syslog.openlog
    syslog = syslog.syslog

    def __init__(self, prefix, options=DEFAULT_OPTIONS,
                 facility=DEFAULT_FACILITY):
        """
        @type prefix: C{str}
        @param prefix: The syslog prefix to use.

        @type options: C{int}
        @param options: A bitvector represented as an integer of the syslog
            options to use.

        @type facility: C{int}
        @param facility: An indication to the syslog daemon of what sort of
            program this is (essentially, an additional arbitrary metadata
            classification for messages sent to syslog by this observer).
        """
        self.openlog(prefix, options, facility)


    def emit(self, eventDict):
        """
        Send a message event to the I{syslog}.

        @param eventDict: The event to send.  If it has no C{'message'} key, it
            will be ignored.  Otherwise, if it has C{'syslogPriority'} and/or
            C{'syslogFacility'} keys, these will be used as the syslog priority
            and facility.  If it has no C{'syslogPriority'} key but a true
            value for the C{'isError'} key, the B{LOG_ALERT} priority will be
            used; if it has a false value for C{'isError'}, B{LOG_INFO} will be
            used.  If the C{'message'} key is multiline, each line will be sent
            to the syslog separately.
        """
        # Figure out what the message-text is.
        text = log.textFromEventDict(eventDict)
        if text is None:
            return

        # Figure out what syslog parameters we might need to use.
        priority = syslog.LOG_INFO
        facility = 0
        if eventDict['isError']:
            priority = syslog.LOG_ALERT
        if 'syslogPriority' in eventDict:
            priority = int(eventDict['syslogPriority'])
        if 'syslogFacility' in eventDict:
            facility = int(eventDict['syslogFacility'])

        # Break the message up into lines and send them.
        lines = text.split('\n')
        while lines[-1:] == ['']:
            lines.pop()

        firstLine = True
        for line in lines:
            if firstLine:
                firstLine = False
            else:
                line = '\t' + line
            self.syslog(priority | facility,
                        '[%s] %s' % (eventDict['system'], line))



def startLogging(prefix='Twisted', options=DEFAULT_OPTIONS,
                 facility=DEFAULT_FACILITY, setStdout=1):
    """
    Send all Twisted logging output to syslog from now on.

    The prefix, options and facility arguments are passed to
    C{syslog.openlog()}, see the Python syslog documentation for details. For
    other parameters, see L{twisted.python.log.startLoggingWithObserver}.
    """
    obs = SyslogObserver(prefix, options, facility)
    log.startLoggingWithObserver(obs.emit, setStdout=setStdout)
