# -*- test-case-name: twisted.test.test_process -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Windows Process Management, used with reactor.spawnProcess
"""


import os
import sys

from zope.interface import implementer

import pywintypes  # type: ignore[import]

# Win32 imports
import win32api  # type: ignore[import]
import win32con  # type: ignore[import]
import win32event  # type: ignore[import]
import win32file  # type: ignore[import]
import win32pipe  # type: ignore[import]
import win32process  # type: ignore[import]
import win32security  # type: ignore[import]

from twisted.internet import _pollingfile, error
from twisted.internet._baseprocess import BaseProcess
from twisted.internet.interfaces import IConsumer, IProcessTransport, IProducer
from twisted.python.win32 import quoteArguments

# Security attributes for pipes
PIPE_ATTRS_INHERITABLE = win32security.SECURITY_ATTRIBUTES()
PIPE_ATTRS_INHERITABLE.bInheritHandle = 1


def debug(msg):
    print(msg)
    sys.stdout.flush()


class _Reaper(_pollingfile._PollableResource):
    def __init__(self, proc):
        self.proc = proc

    def checkWork(self):
        if (
            win32event.WaitForSingleObject(self.proc.hProcess, 0)
            != win32event.WAIT_OBJECT_0
        ):
            return 0
        exitCode = win32process.GetExitCodeProcess(self.proc.hProcess)
        self.deactivate()
        self.proc.processEnded(exitCode)
        return 0


def _findShebang(filename):
    """
    Look for a #! line, and return the value following the #! if one exists, or
    None if this file is not a script.

    I don't know if there are any conventions for quoting in Windows shebang
    lines, so this doesn't support any; therefore, you may not pass any
    arguments to scripts invoked as filters.  That's probably wrong, so if
    somebody knows more about the cultural expectations on Windows, please feel
    free to fix.

    This shebang line support was added in support of the CGI tests;
    appropriately enough, I determined that shebang lines are culturally
    accepted in the Windows world through this page::

        http://www.cgi101.com/learn/connect/winxp.html

    @param filename: str representing a filename

    @return: a str representing another filename.
    """
    with open(filename) as f:
        if f.read(2) == "#!":
            exe = f.readline(1024).strip("\n")
            return exe


def _invalidWin32App(pywinerr):
    """
    Determine if a pywintypes.error is telling us that the given process is
    'not a valid win32 application', i.e. not a PE format executable.

    @param pywinerr: a pywintypes.error instance raised by CreateProcess

    @return: a boolean
    """

    # Let's do this better in the future, but I have no idea what this error
    # is; MSDN doesn't mention it, and there is no symbolic constant in
    # win32process module that represents 193.

    return pywinerr.args[0] == 193


@implementer(IProcessTransport, IConsumer, IProducer)
class Process(_pollingfile._PollingTimer, BaseProcess):
    """
    A process that integrates with the Twisted event loop.

    If your subprocess is a python program, you need to:

     - Run python.exe with the '-u' command line option - this turns on
       unbuffered I/O. Buffering stdout/err/in can cause problems, see e.g.
       http://support.microsoft.com/default.aspx?scid=kb;EN-US;q1903

     - If you don't want Windows messing with data passed over
       stdin/out/err, set the pipes to be in binary mode::

        import os, sys, mscvrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stderr.fileno(), os.O_BINARY)

    """

    closedNotifies = 0

    def __init__(self, reactor, protocol, command, args, environment, path):
        """
        Create a new child process.
        """
        _pollingfile._PollingTimer.__init__(self, reactor)
        BaseProcess.__init__(self, protocol)

        # security attributes for pipes
        sAttrs = win32security.SECURITY_ATTRIBUTES()
        sAttrs.bInheritHandle = 1

        # create the pipes which will connect to the secondary process
        self.hStdoutR, hStdoutW = win32pipe.CreatePipe(sAttrs, 0)
        self.hStderrR, hStderrW = win32pipe.CreatePipe(sAttrs, 0)
        hStdinR, self.hStdinW = win32pipe.CreatePipe(sAttrs, 0)

        win32pipe.SetNamedPipeHandleState(
            self.hStdinW, win32pipe.PIPE_NOWAIT, None, None
        )

        # set the info structure for the new process.
        StartupInfo = win32process.STARTUPINFO()
        StartupInfo.hStdOutput = hStdoutW
        StartupInfo.hStdError = hStderrW
        StartupInfo.hStdInput = hStdinR
        StartupInfo.dwFlags = win32process.STARTF_USESTDHANDLES

        # Create new handles whose inheritance property is false
        currentPid = win32api.GetCurrentProcess()

        tmp = win32api.DuplicateHandle(
            currentPid, self.hStdoutR, currentPid, 0, 0, win32con.DUPLICATE_SAME_ACCESS
        )
        win32file.CloseHandle(self.hStdoutR)
        self.hStdoutR = tmp

        tmp = win32api.DuplicateHandle(
            currentPid, self.hStderrR, currentPid, 0, 0, win32con.DUPLICATE_SAME_ACCESS
        )
        win32file.CloseHandle(self.hStderrR)
        self.hStderrR = tmp

        tmp = win32api.DuplicateHandle(
            currentPid, self.hStdinW, currentPid, 0, 0, win32con.DUPLICATE_SAME_ACCESS
        )
        win32file.CloseHandle(self.hStdinW)
        self.hStdinW = tmp

        # Add the specified environment to the current environment - this is
        # necessary because certain operations are only supported on Windows
        # if certain environment variables are present.

        env = os.environ.copy()
        env.update(environment or {})
        env = {os.fsdecode(key): os.fsdecode(value) for key, value in env.items()}

        # Make sure all the arguments are Unicode.
        args = [os.fsdecode(x) for x in args]

        cmdline = quoteArguments(args)

        # The command, too, needs to be Unicode, if it is a value.
        command = os.fsdecode(command) if command else command
        path = os.fsdecode(path) if path else path

        # TODO: error detection here.  See #2787 and #4184.
        def doCreate():
            flags = win32con.CREATE_NO_WINDOW
            self.hProcess, self.hThread, self.pid, dwTid = win32process.CreateProcess(
                command, cmdline, None, None, 1, flags, env, path, StartupInfo
            )

        try:
            doCreate()
        except pywintypes.error as pwte:
            if not _invalidWin32App(pwte):
                # This behavior isn't _really_ documented, but let's make it
                # consistent with the behavior that is documented.
                raise OSError(pwte)
            else:
                # look for a shebang line.  Insert the original 'command'
                # (actually a script) into the new arguments list.
                sheb = _findShebang(command)
                if sheb is None:
                    raise OSError(
                        "%r is neither a Windows executable, "
                        "nor a script with a shebang line" % command
                    )
                else:
                    args = list(args)
                    args.insert(0, command)
                    cmdline = quoteArguments(args)
                    origcmd = command
                    command = sheb
                    try:
                        # Let's try again.
                        doCreate()
                    except pywintypes.error as pwte2:
                        # d'oh, failed again!
                        if _invalidWin32App(pwte2):
                            raise OSError(
                                "%r has an invalid shebang line: "
                                "%r is not a valid executable" % (origcmd, sheb)
                            )
                        raise OSError(pwte2)

        # close handles which only the child will use
        win32file.CloseHandle(hStderrW)
        win32file.CloseHandle(hStdoutW)
        win32file.CloseHandle(hStdinR)

        # set up everything
        self.stdout = _pollingfile._PollableReadPipe(
            self.hStdoutR,
            lambda data: self.proto.childDataReceived(1, data),
            self.outConnectionLost,
        )

        self.stderr = _pollingfile._PollableReadPipe(
            self.hStderrR,
            lambda data: self.proto.childDataReceived(2, data),
            self.errConnectionLost,
        )

        self.stdin = _pollingfile._PollableWritePipe(
            self.hStdinW, self.inConnectionLost
        )

        for pipewatcher in self.stdout, self.stderr, self.stdin:
            self._addPollableResource(pipewatcher)

        # notify protocol
        self.proto.makeConnection(self)

        self._addPollableResource(_Reaper(self))

    def signalProcess(self, signalID):
        if self.pid is None:
            raise error.ProcessExitedAlready()
        if signalID in ("INT", "TERM", "KILL"):
            win32process.TerminateProcess(self.hProcess, 1)

    def _getReason(self, status):
        if status == 0:
            return error.ProcessDone(status)
        return error.ProcessTerminated(status)

    def write(self, data):
        """
        Write data to the process' stdin.

        @type data: C{bytes}
        """
        self.stdin.write(data)

    def writeSequence(self, seq):
        """
        Write data to the process' stdin.

        @type seq: C{list} of C{bytes}
        """
        self.stdin.writeSequence(seq)

    def writeToChild(self, fd, data):
        """
        Similar to L{ITransport.write} but also allows the file descriptor in
        the child process which will receive the bytes to be specified.

        This implementation is limited to writing to the child's standard input.

        @param fd: The file descriptor to which to write.  Only stdin (C{0}) is
            supported.
        @type fd: C{int}

        @param data: The bytes to write.
        @type data: C{bytes}

        @return: L{None}

        @raise KeyError: If C{fd} is anything other than the stdin file
            descriptor (C{0}).
        """
        if fd == 0:
            self.stdin.write(data)
        else:
            raise KeyError(fd)

    def closeChildFD(self, fd):
        if fd == 0:
            self.closeStdin()
        elif fd == 1:
            self.closeStdout()
        elif fd == 2:
            self.closeStderr()
        else:
            raise NotImplementedError(
                "Only standard-IO file descriptors available on win32"
            )

    def closeStdin(self):
        """Close the process' stdin."""
        self.stdin.close()

    def closeStderr(self):
        self.stderr.close()

    def closeStdout(self):
        self.stdout.close()

    def loseConnection(self):
        """
        Close the process' stdout, in and err.
        """
        self.closeStdin()
        self.closeStdout()
        self.closeStderr()

    def outConnectionLost(self):
        self.proto.childConnectionLost(1)
        self.connectionLostNotify()

    def errConnectionLost(self):
        self.proto.childConnectionLost(2)
        self.connectionLostNotify()

    def inConnectionLost(self):
        self.proto.childConnectionLost(0)
        self.connectionLostNotify()

    def connectionLostNotify(self):
        """
        Will be called 3 times, by stdout/err threads and process handle.
        """
        self.closedNotifies += 1
        self.maybeCallProcessEnded()

    def maybeCallProcessEnded(self):
        if self.closedNotifies == 3 and self.lostProcess:
            win32file.CloseHandle(self.hProcess)
            win32file.CloseHandle(self.hThread)
            self.hProcess = None
            self.hThread = None
            BaseProcess.maybeCallProcessEnded(self)

    # IConsumer
    def registerProducer(self, producer, streaming):
        self.stdin.registerProducer(producer, streaming)

    def unregisterProducer(self):
        self.stdin.unregisterProducer()

    # IProducer
    def pauseProducing(self):
        self._pause()

    def resumeProducing(self):
        self._unpause()

    def stopProducing(self):
        self.loseConnection()

    def getHost(self):
        # ITransport.getHost
        raise NotImplementedError("Unimplemented: Process.getHost")

    def getPeer(self):
        # ITransport.getPeer
        raise NotImplementedError("Unimplemented: Process.getPeer")

    def __repr__(self) -> str:
        """
        Return a string representation of the process.
        """
        return f"<{self.__class__.__name__} pid={self.pid}>"
