# -*- test-case-name: twisted.conch.test.test_conch -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#
# $Id: conch.py,v 1.65 2004/03/11 00:29:14 z3p Exp $

# Implementation module for the `conch` command.
#

import fcntl
import getpass
import os
import signal
import struct
import sys
import tty
from typing import List, Tuple

from twisted.conch.client import connect, default
from twisted.conch.client.options import ConchOptions
from twisted.conch.error import ConchError
from twisted.conch.ssh import channel, common, connection, forwarding, session
from twisted.internet import reactor, stdio, task
from twisted.python import log, usage
from twisted.python.compat import ioType, networkString


class ClientOptions(ConchOptions):

    synopsis = """Usage:   conch [options] host [command]
"""
    longdesc = (
        "conch is a SSHv2 client that allows logging into a remote "
        "machine and executing commands."
    )

    optParameters = [
        ["escape", "e", "~"],
        [
            "localforward",
            "L",
            None,
            "listen-port:host:port   Forward local port to remote address",
        ],
        [
            "remoteforward",
            "R",
            None,
            "listen-port:host:port   Forward remote port to local address",
        ],
    ]

    optFlags = [
        ["null", "n", "Redirect input from /dev/null."],
        ["fork", "f", "Fork to background after authentication."],
        ["tty", "t", "Tty; allocate a tty even if command is given."],
        ["notty", "T", "Do not allocate a tty."],
        ["noshell", "N", "Do not execute a shell or command."],
        ["subsystem", "s", "Invoke command (mandatory) as SSH2 subsystem."],
    ]

    compData = usage.Completions(
        mutuallyExclusive=[("tty", "notty")],
        optActions={
            "localforward": usage.Completer(descr="listen-port:host:port"),
            "remoteforward": usage.Completer(descr="listen-port:host:port"),
        },
        extraActions=[
            usage.CompleteUserAtHost(),
            usage.Completer(descr="command"),
            usage.Completer(descr="argument", repeat=True),
        ],
    )

    localForwards: List[Tuple[int, Tuple[int, int]]] = []
    remoteForwards: List[Tuple[int, Tuple[int, int]]] = []

    def opt_escape(self, esc):
        """
        Set escape character; ``none'' = disable
        """
        if esc == "none":
            self["escape"] = None
        elif esc[0] == "^" and len(esc) == 2:
            self["escape"] = chr(ord(esc[1]) - 64)
        elif len(esc) == 1:
            self["escape"] = esc
        else:
            sys.exit(f"Bad escape character '{esc}'.")

    def opt_localforward(self, f):
        """
        Forward local port to remote address (lport:host:port)
        """
        localPort, remoteHost, remotePort = f.split(":")  # Doesn't do v6 yet
        localPort = int(localPort)
        remotePort = int(remotePort)
        self.localForwards.append((localPort, (remoteHost, remotePort)))

    def opt_remoteforward(self, f):
        """
        Forward remote port to local address (rport:host:port)
        """
        remotePort, connHost, connPort = f.split(":")  # Doesn't do v6 yet
        remotePort = int(remotePort)
        connPort = int(connPort)
        self.remoteForwards.append((remotePort, (connHost, connPort)))

    def parseArgs(self, host, *command):
        self["host"] = host
        self["command"] = " ".join(command)


# Rest of code in "run"
options = None
conn = None
exitStatus = 0
old = None
_inRawMode = 0
_savedRawMode = None


def run():
    global options, old
    args = sys.argv[1:]
    if "-l" in args:  # CVS is an idiot
        i = args.index("-l")
        args = args[i : i + 2] + args
        del args[i + 2 : i + 4]
    for arg in args[:]:
        try:
            i = args.index(arg)
            if arg[:2] == "-o" and args[i + 1][0] != "-":
                args[i : i + 2] = []  # Suck on it scp
        except ValueError:
            pass
    options = ClientOptions()
    try:
        options.parseOptions(args)
    except usage.UsageError as u:
        print(f"ERROR: {u}")
        options.opt_help()
        sys.exit(1)
    if options["log"]:
        if options["logfile"]:
            if options["logfile"] == "-":
                f = sys.stdout
            else:
                f = open(options["logfile"], "a+")
        else:
            f = sys.stderr
        realout = sys.stdout
        log.startLogging(f)
        sys.stdout = realout
    else:
        log.discardLogs()
    doConnect()
    fd = sys.stdin.fileno()
    try:
        old = tty.tcgetattr(fd)
    except BaseException:
        old = None
    try:
        oldUSR1 = signal.signal(
            signal.SIGUSR1, lambda *a: reactor.callLater(0, reConnect)
        )
    except BaseException:
        oldUSR1 = None
    try:
        reactor.run()
    finally:
        if old:
            tty.tcsetattr(fd, tty.TCSANOW, old)
        if oldUSR1:
            signal.signal(signal.SIGUSR1, oldUSR1)
        if (options["command"] and options["tty"]) or not options["notty"]:
            signal.signal(signal.SIGWINCH, signal.SIG_DFL)
    if sys.stdout.isatty() and not options["command"]:
        print("Connection to {} closed.".format(options["host"]))
    sys.exit(exitStatus)


def handleError():
    from twisted.python import failure

    global exitStatus
    exitStatus = 2
    reactor.callLater(0.01, _stopReactor)
    log.err(failure.Failure())
    raise


def _stopReactor():
    try:
        reactor.stop()
    except BaseException:
        pass


def doConnect():
    if "@" in options["host"]:
        options["user"], options["host"] = options["host"].split("@", 1)
    if not options.identitys:
        options.identitys = ["~/.ssh/id_rsa", "~/.ssh/id_dsa"]
    host = options["host"]
    if not options["user"]:
        options["user"] = getpass.getuser()
    if not options["port"]:
        options["port"] = 22
    else:
        options["port"] = int(options["port"])
    host = options["host"]
    port = options["port"]
    vhk = default.verifyHostKey
    if not options["host-key-algorithms"]:
        options["host-key-algorithms"] = default.getHostKeyAlgorithms(host, options)
    uao = default.SSHUserAuthClient(options["user"], options, SSHConnection())
    connect.connect(host, port, options, vhk, uao).addErrback(_ebExit)


def _ebExit(f):
    global exitStatus
    exitStatus = f"conch: exiting with error {f}"
    reactor.callLater(0.1, _stopReactor)


def onConnect():
    #    if keyAgent and options['agent']:
    #        cc = protocol.ClientCreator(reactor, SSHAgentForwardingLocal, conn)
    #        cc.connectUNIX(os.environ['SSH_AUTH_SOCK'])
    if hasattr(conn.transport, "sendIgnore"):
        _KeepAlive(conn)
    if options.localForwards:
        for localPort, hostport in options.localForwards:
            s = reactor.listenTCP(
                localPort,
                forwarding.SSHListenForwardingFactory(
                    conn, hostport, SSHListenClientForwardingChannel
                ),
            )
            conn.localForwards.append(s)
    if options.remoteForwards:
        for remotePort, hostport in options.remoteForwards:
            log.msg(f"asking for remote forwarding for {remotePort}:{hostport}")
            conn.requestRemoteForwarding(remotePort, hostport)
        reactor.addSystemEventTrigger("before", "shutdown", beforeShutdown)
    if not options["noshell"] or options["agent"]:
        conn.openChannel(SSHSession())
    if options["fork"]:
        if os.fork():
            os._exit(0)
        os.setsid()
        for i in range(3):
            try:
                os.close(i)
            except OSError as e:
                import errno

                if e.errno != errno.EBADF:
                    raise


def reConnect():
    beforeShutdown()
    conn.transport.transport.loseConnection()


def beforeShutdown():
    remoteForwards = options.remoteForwards
    for remotePort, hostport in remoteForwards:
        log.msg(f"cancelling {remotePort}:{hostport}")
        conn.cancelRemoteForwarding(remotePort)


def stopConnection():
    if not options["reconnect"]:
        reactor.callLater(0.1, _stopReactor)


class _KeepAlive:
    def __init__(self, conn):
        self.conn = conn
        self.globalTimeout = None
        self.lc = task.LoopingCall(self.sendGlobal)
        self.lc.start(300)

    def sendGlobal(self):
        d = self.conn.sendGlobalRequest(
            b"conch-keep-alive@twistedmatrix.com", b"", wantReply=1
        )
        d.addBoth(self._cbGlobal)
        self.globalTimeout = reactor.callLater(30, self._ebGlobal)

    def _cbGlobal(self, res):
        if self.globalTimeout:
            self.globalTimeout.cancel()
            self.globalTimeout = None

    def _ebGlobal(self):
        if self.globalTimeout:
            self.globalTimeout = None
            self.conn.transport.loseConnection()


class SSHConnection(connection.SSHConnection):
    def serviceStarted(self):
        global conn
        conn = self
        self.localForwards = []
        self.remoteForwards = {}
        onConnect()

    def serviceStopped(self):
        lf = self.localForwards
        self.localForwards = []
        for s in lf:
            s.loseConnection()
        stopConnection()

    def requestRemoteForwarding(self, remotePort, hostport):
        data = forwarding.packGlobal_tcpip_forward(("0.0.0.0", remotePort))
        d = self.sendGlobalRequest(b"tcpip-forward", data, wantReply=1)
        log.msg(f"requesting remote forwarding {remotePort}:{hostport}")
        d.addCallback(self._cbRemoteForwarding, remotePort, hostport)
        d.addErrback(self._ebRemoteForwarding, remotePort, hostport)

    def _cbRemoteForwarding(self, result, remotePort, hostport):
        log.msg(f"accepted remote forwarding {remotePort}:{hostport}")
        self.remoteForwards[remotePort] = hostport
        log.msg(repr(self.remoteForwards))

    def _ebRemoteForwarding(self, f, remotePort, hostport):
        log.msg(f"remote forwarding {remotePort}:{hostport} failed")
        log.msg(f)

    def cancelRemoteForwarding(self, remotePort):
        data = forwarding.packGlobal_tcpip_forward(("0.0.0.0", remotePort))
        self.sendGlobalRequest(b"cancel-tcpip-forward", data)
        log.msg(f"cancelling remote forwarding {remotePort}")
        try:
            del self.remoteForwards[remotePort]
        except Exception:
            pass
        log.msg(repr(self.remoteForwards))

    def channel_forwarded_tcpip(self, windowSize, maxPacket, data):
        log.msg(f"FTCP {data!r}")
        remoteHP, origHP = forwarding.unpackOpen_forwarded_tcpip(data)
        log.msg(self.remoteForwards)
        log.msg(remoteHP)
        if remoteHP[1] in self.remoteForwards:
            connectHP = self.remoteForwards[remoteHP[1]]
            log.msg(f"connect forwarding {connectHP}")
            return SSHConnectForwardingChannel(
                connectHP, remoteWindow=windowSize, remoteMaxPacket=maxPacket, conn=self
            )
        else:
            raise ConchError(
                connection.OPEN_CONNECT_FAILED, "don't know about that port"
            )

    def channelClosed(self, channel):
        log.msg(f"connection closing {channel}")
        log.msg(self.channels)
        if len(self.channels) == 1:  # Just us left
            log.msg("stopping connection")
            stopConnection()
        else:
            # Because of the unix thing
            self.__class__.__bases__[0].channelClosed(self, channel)


class SSHSession(channel.SSHChannel):

    name = b"session"

    def channelOpen(self, foo):
        log.msg(f"session {self.id} open")
        if options["agent"]:
            d = self.conn.sendRequest(
                self, b"auth-agent-req@openssh.com", b"", wantReply=1
            )
            d.addBoth(lambda x: log.msg(x))
        if options["noshell"]:
            return
        if (options["command"] and options["tty"]) or not options["notty"]:
            _enterRawMode()
        c = session.SSHSessionClient()
        if options["escape"] and not options["notty"]:
            self.escapeMode = 1
            c.dataReceived = self.handleInput
        else:
            c.dataReceived = self.write
        c.connectionLost = lambda x: self.sendEOF()
        self.stdio = stdio.StandardIO(c)
        fd = 0
        if options["subsystem"]:
            self.conn.sendRequest(self, b"subsystem", common.NS(options["command"]))
        elif options["command"]:
            if options["tty"]:
                term = os.environ["TERM"]
                winsz = fcntl.ioctl(fd, tty.TIOCGWINSZ, "12345678")
                winSize = struct.unpack("4H", winsz)
                ptyReqData = session.packRequest_pty_req(term, winSize, "")
                self.conn.sendRequest(self, b"pty-req", ptyReqData)
                signal.signal(signal.SIGWINCH, self._windowResized)
            self.conn.sendRequest(self, b"exec", common.NS(options["command"]))
        else:
            if not options["notty"]:
                term = os.environ["TERM"]
                winsz = fcntl.ioctl(fd, tty.TIOCGWINSZ, "12345678")
                winSize = struct.unpack("4H", winsz)
                ptyReqData = session.packRequest_pty_req(term, winSize, "")
                self.conn.sendRequest(self, b"pty-req", ptyReqData)
                signal.signal(signal.SIGWINCH, self._windowResized)
            self.conn.sendRequest(self, b"shell", b"")
            # if hasattr(conn.transport, 'transport'):
            #    conn.transport.transport.setTcpNoDelay(1)

    def handleInput(self, char):
        if char in (b"\n", b"\r"):
            self.escapeMode = 1
            self.write(char)
        elif self.escapeMode == 1 and char == options["escape"]:
            self.escapeMode = 2
        elif self.escapeMode == 2:
            self.escapeMode = 1  # So we can chain escapes together
            if char == b".":  # Disconnect
                log.msg("disconnecting from escape")
                stopConnection()
                return
            elif char == b"\x1a":  # ^Z, suspend

                def _():
                    _leaveRawMode()
                    sys.stdout.flush()
                    sys.stdin.flush()
                    os.kill(os.getpid(), signal.SIGTSTP)
                    _enterRawMode()

                reactor.callLater(0, _)
                return
            elif char == b"R":  # Rekey connection
                log.msg("rekeying connection")
                self.conn.transport.sendKexInit()
                return
            elif char == b"#":  # Display connections
                self.stdio.write(b"\r\nThe following connections are open:\r\n")
                channels = self.conn.channels.keys()
                channels.sort()
                for channelId in channels:
                    self.stdio.write(
                        networkString(
                            "  #{} {}\r\n".format(
                                channelId, self.conn.channels[channelId]
                            )
                        )
                    )
                return
            self.write(b"~" + char)
        else:
            self.escapeMode = 0
            self.write(char)

    def dataReceived(self, data):
        self.stdio.write(data)

    def extReceived(self, t, data):
        if t == connection.EXTENDED_DATA_STDERR:
            log.msg(f"got {len(data)} stderr data")
            if ioType(sys.stderr) == str:
                sys.stderr.buffer.write(data)
            else:
                sys.stderr.write(data)

    def eofReceived(self):
        log.msg("got eof")
        self.stdio.loseWriteConnection()

    def closeReceived(self):
        log.msg(f"remote side closed {self}")
        self.conn.sendClose(self)

    def closed(self):
        global old
        log.msg(f"closed {self}")
        log.msg(repr(self.conn.channels))

    def request_exit_status(self, data):
        global exitStatus
        exitStatus = int(struct.unpack(">L", data)[0])
        log.msg(f"exit status: {exitStatus}")

    def sendEOF(self):
        self.conn.sendEOF(self)

    def stopWriting(self):
        self.stdio.pauseProducing()

    def startWriting(self):
        self.stdio.resumeProducing()

    def _windowResized(self, *args):
        winsz = fcntl.ioctl(0, tty.TIOCGWINSZ, "12345678")
        winSize = struct.unpack("4H", winsz)
        newSize = winSize[1], winSize[0], winSize[2], winSize[3]
        self.conn.sendRequest(self, b"window-change", struct.pack("!4L", *newSize))


class SSHListenClientForwardingChannel(forwarding.SSHListenClientForwardingChannel):
    pass


class SSHConnectForwardingChannel(forwarding.SSHConnectForwardingChannel):
    pass


def _leaveRawMode():
    global _inRawMode
    if not _inRawMode:
        return
    fd = sys.stdin.fileno()
    tty.tcsetattr(fd, tty.TCSANOW, _savedRawMode)
    _inRawMode = 0


def _enterRawMode():
    global _inRawMode, _savedRawMode
    if _inRawMode:
        return
    fd = sys.stdin.fileno()
    try:
        old = tty.tcgetattr(fd)
        new = old[:]
    except BaseException:
        log.msg("not a typewriter!")
    else:
        # iflage
        new[0] = new[0] | tty.IGNPAR
        new[0] = new[0] & ~(
            tty.ISTRIP
            | tty.INLCR
            | tty.IGNCR
            | tty.ICRNL
            | tty.IXON
            | tty.IXANY
            | tty.IXOFF
        )
        if hasattr(tty, "IUCLC"):
            new[0] = new[0] & ~tty.IUCLC

        # lflag
        new[3] = new[3] & ~(
            tty.ISIG
            | tty.ICANON
            | tty.ECHO
            | tty.ECHO
            | tty.ECHOE
            | tty.ECHOK
            | tty.ECHONL
        )
        if hasattr(tty, "IEXTEN"):
            new[3] = new[3] & ~tty.IEXTEN

        # oflag
        new[1] = new[1] & ~tty.OPOST

        new[6][tty.VMIN] = 1
        new[6][tty.VTIME] = 0

        _savedRawMode = old
        tty.tcsetattr(fd, tty.TCSANOW, new)
        # tty.setraw(fd)
        _inRawMode = 1


if __name__ == "__main__":
    run()
