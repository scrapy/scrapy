# -*- test-case-name: twisted.runner.test.test_inetdconf -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Parser for inetd.conf files
"""

from twisted.python.deprecate import deprecatedModuleAttribute
from twisted.python.versions import Version


# Various exceptions
class InvalidConfError(Exception):
    """
    Invalid configuration file
    """



class InvalidInetdConfError(InvalidConfError):
    """
    Invalid inetd.conf file
    """



class InvalidServicesConfError(InvalidConfError):
    """
    Invalid services file
    """



class InvalidRPCServicesConfError(InvalidConfError):
    """
    DEPRECATED. Invalid rpc services file
    """
    deprecatedModuleAttribute(
        Version("Twisted", 16, 2, 0),
        "The RPC service configuration is no longer maintained.",
        __name__, "InvalidRPCServicesConfError")



class UnknownService(Exception):
    """
    Unknown service name
    """



class SimpleConfFile:
    """
    Simple configuration file parser superclass.

    Filters out comments and empty lines (which includes lines that only
    contain comments).

    To use this class, override parseLine or parseFields.
    """

    commentChar = '#'
    defaultFilename = None

    def parseFile(self, file=None):
        """
        Parse a configuration file

        If file is None and self.defaultFilename is set, it will open
        defaultFilename and use it.
        """
        close = False
        if file is None and self.defaultFilename:
            file = open(self.defaultFilename,'r')
            close = True

        try:
            for line in file.readlines():
                # Strip out comments
                comment = line.find(self.commentChar)
                if comment != -1:
                    line = line[:comment]

                # Strip whitespace
                line = line.strip()

                # Skip empty lines (and lines which only contain comments)
                if not line:
                    continue

                self.parseLine(line)
        finally:
            if close:
                file.close()


    def parseLine(self, line):
        """
        Override this.

        By default, this will split the line on whitespace and call
        self.parseFields (catching any errors).
        """
        try:
            self.parseFields(*line.split())
        except ValueError:
            raise InvalidInetdConfError('Invalid line: ' + repr(line))


    def parseFields(self, *fields):
        """
        Override this.
        """



class InetdService:
    """
    A simple description of an inetd service.
    """
    name = None
    port = None
    socketType = None
    protocol = None
    wait = None
    user = None
    group = None
    program = None
    programArgs = None

    def __init__(self, name, port, socketType, protocol, wait, user, group,
                 program, programArgs):
        self.name = name
        self.port = port
        self.socketType = socketType
        self.protocol = protocol
        self.wait = wait
        self.user = user
        self.group = group
        self.program = program
        self.programArgs = programArgs



class InetdConf(SimpleConfFile):
    """
    Configuration parser for a traditional UNIX inetd(8)
    """

    defaultFilename = '/etc/inetd.conf'

    def __init__(self, knownServices=None):
        self.services = []

        if knownServices is None:
            knownServices = ServicesConf()
            knownServices.parseFile()
        self.knownServices = knownServices


    def parseFields(self, serviceName, socketType, protocol, wait, user,
                    program, *programArgs):
        """
        Parse an inetd.conf file.

        Implemented from the description in the Debian inetd.conf man page.
        """
        # Extract user (and optional group)
        user, group = (user.split('.') + [None])[:2]

        # Find the port for a service
        port = self.knownServices.services.get((serviceName, protocol), None)
        if not port and not protocol.startswith('rpc/'):
            # FIXME: Should this be discarded/ignored, rather than throwing
            #        an exception?
            try:
                port = int(serviceName)
                serviceName = 'unknown'
            except:
                raise UnknownService("Unknown service: %s (%s)" % (
                    serviceName, protocol))

        self.services.append(InetdService(serviceName, port, socketType,
                                          protocol, wait, user, group, program,
                                          programArgs))



class ServicesConf(SimpleConfFile):
    """
    /etc/services parser

    @ivar services: dict mapping service names to (port, protocol) tuples.
    """

    defaultFilename = '/etc/services'

    def __init__(self):
        self.services = {}


    def parseFields(self, name, portAndProtocol, *aliases):
        try:
            port, protocol = portAndProtocol.split('/')
            port = int(port)
        except:
            raise InvalidServicesConfError(
                'Invalid port/protocol: %s' % (repr(portAndProtocol),))

        self.services[(name, protocol)] = port
        for alias in aliases:
            self.services[(alias, protocol)] = port



class RPCServicesConf(SimpleConfFile):
    """
    DEPRECATED. /etc/rpc parser

    @ivar self.services: dict mapping rpc service names to rpc ports.
    """
    deprecatedModuleAttribute(
        Version("Twisted", 16, 2, 0),
        "The RPC service configuration is no longer maintained.",
        __name__, "RPCServicesConf")

    defaultFilename = '/etc/rpc'

    def __init__(self):
        self.services = {}


    def parseFields(self, name, port, *aliases):
        try:
            port = int(port)
        except:
            raise InvalidRPCServicesConfError(
                'Invalid port: %s' % (repr(port),))

        self.services[name] = port
        for alias in aliases:
            self.services[alias] = port


