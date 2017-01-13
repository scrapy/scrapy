# -*- test-case-name: twisted.test.test_socks -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementation of the SOCKSv4 protocol.
"""

# python imports
import struct
import string
import socket
import time

# twisted imports
from twisted.internet import reactor, protocol, defer
from twisted.python import log


class SOCKSv4Outgoing(protocol.Protocol):
    def __init__(self, socks):
        self.socks=socks


    def connectionMade(self):
        peer = self.transport.getPeer()
        self.socks.makeReply(90, 0, port=peer.port, ip=peer.host)
        self.socks.otherConn=self


    def connectionLost(self, reason):
        self.socks.transport.loseConnection()


    def dataReceived(self, data):
        self.socks.write(data)


    def write(self,data):
        self.socks.log(self,data)
        self.transport.write(data)



class SOCKSv4Incoming(protocol.Protocol):
    def __init__(self,socks):
        self.socks=socks
        self.socks.otherConn=self


    def connectionLost(self, reason):
        self.socks.transport.loseConnection()


    def dataReceived(self,data):
        self.socks.write(data)


    def write(self, data):
        self.socks.log(self,data)
        self.transport.write(data)



class SOCKSv4(protocol.Protocol):
    """
    An implementation of the SOCKSv4 protocol.

    @type logging: L{str} or L{None}
    @ivar logging: If not L{None}, the name of the logfile to which connection
        information will be written.

    @type reactor: object providing L{twisted.internet.interfaces.IReactorTCP}
    @ivar reactor: The reactor used to create connections.

    @type buf: L{str}
    @ivar buf: Part of a SOCKSv4 connection request.

    @type otherConn: C{SOCKSv4Incoming}, C{SOCKSv4Outgoing} or L{None}
    @ivar otherConn: Until the connection has been established, C{otherConn} is
        L{None}. After that, it is the proxy-to-destination protocol instance
        along which the client's connection is being forwarded.
    """
    def __init__(self, logging=None, reactor=reactor):
        self.logging = logging
        self.reactor = reactor


    def connectionMade(self):
        self.buf = b""
        self.otherConn = None


    def dataReceived(self, data):
        """
        Called whenever data is received.

        @type data: L{bytes}
        @param data: Part or all of a SOCKSv4 packet.
        """
        if self.otherConn:
            self.otherConn.write(data)
            return
        self.buf = self.buf + data
        completeBuffer = self.buf
        if b"\000" in self.buf[8:]:
            head, self.buf = self.buf[:8], self.buf[8:]
            version, code, port = struct.unpack("!BBH", head[:4])
            user, self.buf = self.buf.split(b"\000", 1)
            if head[4:7] == b"\000\000\000" and head[7:8] != b"\000":
                # An IP address of the form 0.0.0.X, where X is non-zero,
                # signifies that this is a SOCKSv4a packet.
                # If the complete packet hasn't been received, restore the
                # buffer and wait for it.
                if b"\000" not in self.buf:
                    self.buf = completeBuffer
                    return
                server, self.buf = self.buf.split(b"\000", 1)
                d = self.reactor.resolve(server)
                d.addCallback(self._dataReceived2, user,
                              version, code, port)
                d.addErrback(lambda result, self = self: self.makeReply(91))
                return
            else:
                server = socket.inet_ntoa(head[4:8])

            self._dataReceived2(server, user, version, code, port)


    def _dataReceived2(self, server, user, version, code, port):
        """
        The second half of the SOCKS connection setup. For a SOCKSv4 packet this
        is after the server address has been extracted from the header. For a
        SOCKSv4a packet this is after the host name has been resolved.

        @type server: L{str}
        @param server: The IP address of the destination, represented as a
            dotted quad.

        @type user: L{str}
        @param user: The username associated with the connection.

        @type version: L{int}
        @param version: The SOCKS protocol version number.

        @type code: L{int}
        @param code: The comand code. 1 means establish a TCP/IP stream
            connection, and 2 means establish a TCP/IP port binding.

        @type port: L{int}
        @param port: The port number associated with the connection.
        """
        assert version == 4, "Bad version code: %s" % version
        if not self.authorize(code, server, port, user):
            self.makeReply(91)
            return
        if code == 1: # CONNECT
            d = self.connectClass(server, port, SOCKSv4Outgoing, self)
            d.addErrback(lambda result, self = self: self.makeReply(91))
        elif code == 2: # BIND
            d = self.listenClass(0, SOCKSv4IncomingFactory, self, server)
            d.addCallback(lambda x,
                          self = self: self.makeReply(90, 0, x[1], x[0]))
        else:
            raise RuntimeError("Bad Connect Code: %s" % (code,))
        assert self.buf == b"", "hmm, still stuff in buffer... %s" % repr(
            self.buf)


    def connectionLost(self, reason):
        if self.otherConn:
            self.otherConn.transport.loseConnection()


    def authorize(self,code,server,port,user):
        log.msg("code %s connection to %s:%s (user %s) authorized" % (code,server,port,user))
        return 1


    def connectClass(self, host, port, klass, *args):
        return protocol.ClientCreator(reactor, klass, *args).connectTCP(host,port)


    def listenClass(self, port, klass, *args):
        serv = reactor.listenTCP(port, klass(*args))
        return defer.succeed(serv.getHost()[1:])


    def makeReply(self,reply,version=0,port=0,ip="0.0.0.0"):
        self.transport.write(struct.pack("!BBH",version,reply,port)+socket.inet_aton(ip))
        if reply!=90: self.transport.loseConnection()


    def write(self,data):
        self.log(self,data)
        self.transport.write(data)


    def log(self,proto,data):
        if not self.logging: return
        peer = self.transport.getPeer()
        their_peer = self.otherConn.transport.getPeer()
        f=open(self.logging,"a")
        f.write("%s\t%s:%d %s %s:%d\n"%(time.ctime(),
                                        peer.host,peer.port,
                                        ((proto==self and '<') or '>'),
                                        their_peer.host,their_peer.port))
        while data:
            p,data=data[:16],data[16:]
            f.write(string.join(map(lambda x:'%02X'%ord(x),p),' ')+' ')
            f.write((16-len(p))*3*' ')
            for c in p:
                if len(repr(c))>3: f.write('.')
                else: f.write(c)
            f.write('\n')
        f.write('\n')
        f.close()



class SOCKSv4Factory(protocol.Factory):
    """
    A factory for a SOCKSv4 proxy.

    Constructor accepts one argument, a log file name.
    """
    def __init__(self, log):
        self.logging = log


    def buildProtocol(self, addr):
        return SOCKSv4(self.logging, reactor)



class SOCKSv4IncomingFactory(protocol.Factory):
    """
    A utility class for building protocols for incoming connections.
    """
    def __init__(self, socks, ip):
        self.socks = socks
        self.ip = ip


    def buildProtocol(self, addr):
        if addr[0] == self.ip:
            self.ip = ""
            self.socks.makeReply(90, 0)
            return SOCKSv4Incoming(self.socks)
        elif self.ip == "":
            return None
        else:
            self.socks.makeReply(91, 0)
            self.ip = ""
            return None
