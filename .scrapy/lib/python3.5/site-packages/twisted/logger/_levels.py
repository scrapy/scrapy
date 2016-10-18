# -*- test-case-name: twisted.logger.test.test_levels -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Log levels.
"""

from twisted.python.constants import NamedConstant, Names



class InvalidLogLevelError(Exception):
    """
    Someone tried to use a L{LogLevel} that is unknown to the logging system.
    """
    def __init__(self, level):
        """
        @param level: A log level.
        @type level: L{LogLevel}
        """
        super(InvalidLogLevelError, self).__init__(str(level))
        self.level = level



class LogLevel(Names):
    """
    Constants describing log levels.

    @cvar debug: Debugging events: Information of use to a developer of the
        software, not generally of interest to someone running the software
        unless they are attempting to diagnose a software issue.

    @cvar info: Informational events: Routine information about the status of
        an application, such as incoming connections, startup of a subsystem,
        etc.

    @cvar warn: Warning events: Events that may require greater attention than
        informational events but are not a systemic failure condition, such as
        authorization failures, bad data from a network client, etc.  Such
        events are of potential interest to system administrators, and should
        ideally be phrased in such a way, or documented, so as to indicate an
        action that an administrator might take to mitigate the warning.

    @cvar error: Error conditions: Events indicating a systemic failure, such
        as programming errors in the form of unhandled exceptions, loss of
        connectivity to an external system without which no useful work can
        proceed, such as a database or API endpoint, or resource exhaustion.
        Similarly to warnings, errors that are related to operational
        parameters may be actionable to system administrators and should
        provide references to resources which an administrator might use to
        resolve them.

    @cvar critical: Critical failures: Errors indicating systemic failure (ie.
        service outage), data corruption, imminent data loss, etc. which must
        be handled immediately.  This includes errors unanticipated by the
        software, such as unhandled exceptions, wherein the cause and
        consequences are unknown.
    """

    debug = NamedConstant()
    info = NamedConstant()
    warn = NamedConstant()
    error = NamedConstant()
    critical = NamedConstant()


    @classmethod
    def levelWithName(cls, name):
        """
        Get the log level with the given name.

        @param name: The name of a log level.
        @type name: L{str} (native string)

        @return: The L{LogLevel} with the specified C{name}.
        @rtype: L{LogLevel}

        @raise InvalidLogLevelError: if the C{name} does not name a valid log
            level.
        """
        try:
            return cls.lookupByName(name)
        except ValueError:
            raise InvalidLogLevelError(name)


    @classmethod
    def _priorityForLevel(cls, level):
        """
        We want log levels to have defined ordering - the order of definition -
        but they aren't value constants (the only value is the name).  This is
        arguably a bug in Twisted, so this is just a workaround for U{until
        this is fixed in some way
        <https://twistedmatrix.com/trac/ticket/6523>}.

        @param level: A log level.
        @type level: L{LogLevel}

        @return: A numeric index indicating priority (lower is higher level).
        @rtype: L{int}
        """
        return cls._levelPriorities[level]


LogLevel._levelPriorities = dict(
    (level, index) for (index, level) in
    (enumerate(LogLevel.iterconstants()))
)
