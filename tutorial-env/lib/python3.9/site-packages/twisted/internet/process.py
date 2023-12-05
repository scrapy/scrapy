# -*- test-case-name: twisted.test.test_process -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
UNIX Process management.

Do NOT use this module directly - use reactor.spawnProcess() instead.

Maintainer: Itamar Shtull-Trauring
"""

import errno
import gc
import io
import os
import signal
import stat
import sys
import traceback
from typing import Callable, Dict, Optional

from zope.interface import implementer

from twisted.internet import abstract, error, fdesc
from twisted.internet._baseprocess import BaseProcess
from twisted.internet.interfaces import IProcessTransport
from twisted.internet.main import CONNECTION_DONE, CONNECTION_LOST
from twisted.python import failure, log
from twisted.python.runtime import platform
from twisted.python.util import switchUID

if platform.isWindows():
    raise ImportError(
        "twisted.internet.process does not work on Windows. "
        "Use the reactor.spawnProcess() API instead."
    )

try:
    import pty as _pty
except ImportError:
    pty = None
else:
    pty = _pty

try:
    import fcntl as _fcntl
    import termios
except ImportError:
    fcntl = None
else:
    fcntl = _fcntl

# Some people were importing this, which is incorrect, just keeping it
# here for backwards compatibility:
ProcessExitedAlready = error.ProcessExitedAlready

reapProcessHandlers: Dict[int, Callable] = {}


def reapAllProcesses():
    """
    Reap all registered processes.
    """
    # Coerce this to a list, as reaping the process changes the dictionary and
    # causes a "size changed during iteration" exception
    for process in list(reapProcessHandlers.values()):
        process.reapProcess()


def registerReapProcessHandler(pid, process):
    """
    Register a process handler for the given pid, in case L{reapAllProcesses}
    is called.

    @param pid: the pid of the process.
    @param process: a process handler.
    """
    if pid in reapProcessHandlers:
        raise RuntimeError("Try to register an already registered process.")
    try:
        auxPID, status = os.waitpid(pid, os.WNOHANG)
    except BaseException:
        log.msg(f"Failed to reap {pid}:")
        log.err()

        if pid is None:
            return

        auxPID = None
    if auxPID:
        process.processEnded(status)
    else:
        # if auxPID is 0, there are children but none have exited
        reapProcessHandlers[pid] = process


def unregisterReapProcessHandler(pid, process):
    """
    Unregister a process handler previously registered with
    L{registerReapProcessHandler}.
    """
    if not (pid in reapProcessHandlers and reapProcessHandlers[pid] == process):
        raise RuntimeError("Try to unregister a process not registered.")
    del reapProcessHandlers[pid]


class ProcessWriter(abstract.FileDescriptor):
    """
    (Internal) Helper class to write into a Process's input pipe.

    I am a helper which describes a selectable asynchronous writer to a
    process's input pipe, including stdin.

    @ivar enableReadHack: A flag which determines how readability on this
        write descriptor will be handled.  If C{True}, then readability may
        indicate the reader for this write descriptor has been closed (ie,
        the connection has been lost).  If C{False}, then readability events
        are ignored.
    """

    connected = 1
    ic = 0
    enableReadHack = False

    def __init__(self, reactor, proc, name, fileno, forceReadHack=False):
        """
        Initialize, specifying a Process instance to connect to.
        """
        abstract.FileDescriptor.__init__(self, reactor)
        fdesc.setNonBlocking(fileno)
        self.proc = proc
        self.name = name
        self.fd = fileno

        if not stat.S_ISFIFO(os.fstat(self.fileno()).st_mode):
            # If the fd is not a pipe, then the read hack is never
            # applicable.  This case arises when ProcessWriter is used by
            # StandardIO and stdout is redirected to a normal file.
            self.enableReadHack = False
        elif forceReadHack:
            self.enableReadHack = True
        else:
            # Detect if this fd is actually a write-only fd. If it's
            # valid to read, don't try to detect closing via read.
            # This really only means that we cannot detect a TTY's write
            # pipe being closed.
            try:
                os.read(self.fileno(), 0)
            except OSError:
                # It's a write-only pipe end, enable hack
                self.enableReadHack = True

        if self.enableReadHack:
            self.startReading()

    def fileno(self):
        """
        Return the fileno() of my process's stdin.
        """
        return self.fd

    def writeSomeData(self, data):
        """
        Write some data to the open process.
        """
        rv = fdesc.writeToFD(self.fd, data)
        if rv == len(data) and self.enableReadHack:
            # If the send buffer is now empty and it is necessary to monitor
            # this descriptor for readability to detect close, try detecting
            # readability now.
            self.startReading()
        return rv

    def write(self, data):
        self.stopReading()
        abstract.FileDescriptor.write(self, data)

    def doRead(self):
        """
        The only way a write pipe can become "readable" is at EOF, because the
        child has closed it, and we're using a reactor which doesn't
        distinguish between readable and closed (such as the select reactor).

        Except that's not true on linux < 2.6.11. It has the following
        characteristics: write pipe is completely empty => POLLOUT (writable in
        select), write pipe is not completely empty => POLLIN (readable in
        select), write pipe's reader closed => POLLIN|POLLERR (readable and
        writable in select)

        That's what this funky code is for. If linux was not broken, this
        function could be simply "return CONNECTION_LOST".
        """
        if self.enableReadHack:
            return CONNECTION_LOST
        else:
            self.stopReading()

    def connectionLost(self, reason):
        """
        See abstract.FileDescriptor.connectionLost.
        """
        # At least on macOS 10.4, exiting while stdout is non-blocking can
        # result in data loss.  For some reason putting the file descriptor
        # back into blocking mode seems to resolve this issue.
        fdesc.setBlocking(self.fd)

        abstract.FileDescriptor.connectionLost(self, reason)
        self.proc.childConnectionLost(self.name, reason)


class ProcessReader(abstract.FileDescriptor):
    """
    ProcessReader

    I am a selectable representation of a process's output pipe, such as
    stdout and stderr.
    """

    connected = True

    def __init__(self, reactor, proc, name, fileno):
        """
        Initialize, specifying a process to connect to.
        """
        abstract.FileDescriptor.__init__(self, reactor)
        fdesc.setNonBlocking(fileno)
        self.proc = proc
        self.name = name
        self.fd = fileno
        self.startReading()

    def fileno(self):
        """
        Return the fileno() of my process's stderr.
        """
        return self.fd

    def writeSomeData(self, data):
        # the only time this is actually called is after .loseConnection Any
        # actual write attempt would fail, so we must avoid that. This hack
        # allows us to use .loseConnection on both readers and writers.
        assert data == b""
        return CONNECTION_LOST

    def doRead(self):
        """
        This is called when the pipe becomes readable.
        """
        return fdesc.readFromFD(self.fd, self.dataReceived)

    def dataReceived(self, data):
        self.proc.childDataReceived(self.name, data)

    def loseConnection(self):
        if self.connected and not self.disconnecting:
            self.disconnecting = 1
            self.stopReading()
            self.reactor.callLater(
                0, self.connectionLost, failure.Failure(CONNECTION_DONE)
            )

    def connectionLost(self, reason):
        """
        Close my end of the pipe, signal the Process (which signals the
        ProcessProtocol).
        """
        abstract.FileDescriptor.connectionLost(self, reason)
        self.proc.childConnectionLost(self.name, reason)


class _BaseProcess(BaseProcess):
    """
    Base class for Process and PTYProcess.
    """

    status: Optional[int] = None
    pid = None

    def reapProcess(self):
        """
        Try to reap a process (without blocking) via waitpid.

        This is called when sigchild is caught or a Process object loses its
        "connection" (stdout is closed) This ought to result in reaping all
        zombie processes, since it will be called twice as often as it needs
        to be.

        (Unfortunately, this is a slightly experimental approach, since
        UNIX has no way to be really sure that your process is going to
        go away w/o blocking.  I don't want to block.)
        """
        try:
            try:
                pid, status = os.waitpid(self.pid, os.WNOHANG)
            except OSError as e:
                if e.errno == errno.ECHILD:
                    # no child process
                    pid = None
                else:
                    raise
        except BaseException:
            log.msg(f"Failed to reap {self.pid}:")
            log.err()
            pid = None
        if pid:
            unregisterReapProcessHandler(pid, self)
            self.processEnded(status)

    def _getReason(self, status):
        exitCode = sig = None
        if os.WIFEXITED(status):
            exitCode = os.WEXITSTATUS(status)
        else:
            sig = os.WTERMSIG(status)
        if exitCode or sig:
            return error.ProcessTerminated(exitCode, sig, status)
        return error.ProcessDone(status)

    def signalProcess(self, signalID):
        """
        Send the given signal C{signalID} to the process. It'll translate a
        few signals ('HUP', 'STOP', 'INT', 'KILL', 'TERM') from a string
        representation to its int value, otherwise it'll pass directly the
        value provided

        @type signalID: C{str} or C{int}
        """
        if signalID in ("HUP", "STOP", "INT", "KILL", "TERM"):
            signalID = getattr(signal, f"SIG{signalID}")
        if self.pid is None:
            raise ProcessExitedAlready()
        try:
            os.kill(self.pid, signalID)
        except OSError as e:
            if e.errno == errno.ESRCH:
                raise ProcessExitedAlready()
            else:
                raise

    def _resetSignalDisposition(self):
        # The Python interpreter ignores some signals, and our child
        # process will inherit that behaviour. To have a child process
        # that responds to signals normally, we need to reset our
        # child process's signal handling (just) after we fork and
        # before we execvpe.
        for signalnum in range(1, signal.NSIG):
            if signal.getsignal(signalnum) == signal.SIG_IGN:
                # Reset signal handling to the default
                signal.signal(signalnum, signal.SIG_DFL)

    def _fork(self, path, uid, gid, executable, args, environment, **kwargs):
        """
        Fork and then exec sub-process.

        @param path: the path where to run the new process.
        @type path: L{bytes} or L{unicode}
        @param uid: if defined, the uid used to run the new process.
        @type uid: L{int}
        @param gid: if defined, the gid used to run the new process.
        @type gid: L{int}
        @param executable: the executable to run in a new process.
        @type executable: L{str}
        @param args: arguments used to create the new process.
        @type args: L{list}.
        @param environment: environment used for the new process.
        @type environment: L{dict}.
        @param kwargs: keyword arguments to L{_setupChild} method.
        """
        collectorEnabled = gc.isenabled()
        gc.disable()
        try:
            self.pid = os.fork()
        except BaseException:
            # Still in the parent process
            if collectorEnabled:
                gc.enable()
            raise
        else:
            if self.pid == 0:
                # A return value of 0 from fork() indicates that we are now
                # executing in the child process.

                # Do not put *ANY* code outside the try block. The child
                # process must either exec or _exit. If it gets outside this
                # block (due to an exception that is not handled here, but
                # which might be handled higher up), there will be two copies
                # of the parent running in parallel, doing all kinds of damage.

                # After each change to this code, review it to make sure there
                # are no exit paths.

                try:
                    # Stop debugging. If I am, I don't care anymore.
                    sys.settrace(None)
                    self._setupChild(**kwargs)
                    self._execChild(path, uid, gid, executable, args, environment)
                except BaseException:
                    # If there are errors, try to write something descriptive
                    # to stderr before exiting.

                    # The parent's stderr isn't *necessarily* fd 2 anymore, or
                    # even still available; however, even libc assumes that
                    # write(2, err) is a useful thing to attempt.

                    try:
                        # On Python 3, print_exc takes a text stream, but
                        # on Python 2 it still takes a byte stream.  So on
                        # Python 3 we will wrap up the byte stream returned
                        # by os.fdopen using TextIOWrapper.

                        # We hard-code UTF-8 as the encoding here, rather
                        # than looking at something like
                        # getfilesystemencoding() or sys.stderr.encoding,
                        # because we want an encoding that will be able to
                        # encode the full range of code points.  We are
                        # (most likely) talking to the parent process on
                        # the other end of this pipe and not the filesystem
                        # or the original sys.stderr, so there's no point
                        # in trying to match the encoding of one of those
                        # objects.

                        stderr = io.TextIOWrapper(os.fdopen(2, "wb"), encoding="utf-8")
                        msg = ("Upon execvpe {} {} in environment id {}" "\n:").format(
                            executable, str(args), id(environment)
                        )
                        stderr.write(msg)
                        traceback.print_exc(file=stderr)
                        stderr.flush()

                        for fd in range(3):
                            os.close(fd)
                    except BaseException:
                        # Handle all errors during the error-reporting process
                        # silently to ensure that the child terminates.
                        pass

                # See comment above about making sure that we reach this line
                # of code.
                os._exit(1)

        # we are now in parent process
        if collectorEnabled:
            gc.enable()
        self.status = -1  # this records the exit status of the child

    def _setupChild(self, *args, **kwargs):
        """
        Setup the child process. Override in subclasses.
        """
        raise NotImplementedError()

    def _execChild(self, path, uid, gid, executable, args, environment):
        """
        The exec() which is done in the forked child.
        """
        if path:
            os.chdir(path)
        if uid is not None or gid is not None:
            if uid is None:
                uid = os.geteuid()
            if gid is None:
                gid = os.getegid()
            # set the UID before I actually exec the process
            os.setuid(0)
            os.setgid(0)
            switchUID(uid, gid)
        os.execvpe(executable, args, environment)

    def __repr__(self) -> str:
        """
        String representation of a process.
        """
        return "<{} pid={} status={}>".format(
            self.__class__.__name__,
            self.pid,
            self.status,
        )


class _FDDetector:
    """
    This class contains the logic necessary to decide which of the available
    system techniques should be used to detect the open file descriptors for
    the current process. The chosen technique gets monkey-patched into the
    _listOpenFDs method of this class so that the detection only needs to occur
    once.

    @ivar listdir: The implementation of listdir to use. This gets overwritten
        by the test cases.
    @ivar getpid: The implementation of getpid to use, returns the PID of the
        running process.
    @ivar openfile: The implementation of open() to use, by default the Python
        builtin.
    """

    # So that we can unit test this
    listdir = os.listdir
    getpid = os.getpid
    openfile = open

    def __init__(self):
        self._implementations = [
            self._procFDImplementation,
            self._devFDImplementation,
            self._fallbackFDImplementation,
        ]

    def _listOpenFDs(self):
        """
        Return an iterable of file descriptors which I{may} be open in this
        process.

        This will try to return the fewest possible descriptors without missing
        any.
        """
        self._listOpenFDs = self._getImplementation()
        return self._listOpenFDs()

    def _getImplementation(self):
        """
        Pick a method which gives correct results for C{_listOpenFDs} in this
        runtime environment.

        This involves a lot of very platform-specific checks, some of which may
        be relatively expensive.  Therefore the returned method should be saved
        and re-used, rather than always calling this method to determine what it
        is.

        See the implementation for the details of how a method is selected.
        """
        for impl in self._implementations:
            try:
                before = impl()
            except BaseException:
                continue
            with self.openfile("/dev/null", "r"):
                after = impl()
            if before != after:
                return impl
        # If no implementation can detect the newly opened file above, then just
        # return the last one.  The last one should therefore always be one
        # which makes a simple static guess which includes all possible open
        # file descriptors, but perhaps also many other values which do not
        # correspond to file descriptors.  For example, the scheme implemented
        # by _fallbackFDImplementation is suitable to be the last entry.
        return impl

    def _devFDImplementation(self):
        """
        Simple implementation for systems where /dev/fd actually works.
        See: http://www.freebsd.org/cgi/man.cgi?fdescfs
        """
        dname = "/dev/fd"
        result = [int(fd) for fd in self.listdir(dname)]
        return result

    def _procFDImplementation(self):
        """
        Simple implementation for systems where /proc/pid/fd exists (we assume
        it works).
        """
        dname = "/proc/%d/fd" % (self.getpid(),)
        return [int(fd) for fd in self.listdir(dname)]

    def _fallbackFDImplementation(self):
        """
        Fallback implementation where either the resource module can inform us
        about the upper bound of how many FDs to expect, or where we just guess
        a constant maximum if there is no resource module.

        All possible file descriptors from 0 to that upper bound are returned
        with no attempt to exclude invalid file descriptor values.
        """
        try:
            import resource
        except ImportError:
            maxfds = 1024
        else:
            # OS-X reports 9223372036854775808. That's a lot of fds to close.
            # OS-X should get the /dev/fd implementation instead, so mostly
            # this check probably isn't necessary.
            maxfds = min(1024, resource.getrlimit(resource.RLIMIT_NOFILE)[1])
        return range(maxfds)


detector = _FDDetector()


def _listOpenFDs():
    """
    Use the global detector object to figure out which FD implementation to
    use.
    """
    return detector._listOpenFDs()


@implementer(IProcessTransport)
class Process(_BaseProcess):
    """
    An operating-system Process.

    This represents an operating-system process with arbitrary input/output
    pipes connected to it. Those pipes may represent standard input,
    standard output, and standard error, or any other file descriptor.

    On UNIX, this is implemented using fork(), exec(), pipe()
    and fcntl(). These calls may not exist elsewhere so this
    code is not cross-platform. (also, windows can only select
    on sockets...)
    """

    debug = False
    debug_child = False

    status = -1
    pid = None

    processWriterFactory = ProcessWriter
    processReaderFactory = ProcessReader

    def __init__(
        self,
        reactor,
        executable,
        args,
        environment,
        path,
        proto,
        uid=None,
        gid=None,
        childFDs=None,
    ):
        """
        Spawn an operating-system process.

        This is where the hard work of disconnecting all currently open
        files / forking / executing the new process happens.  (This is
        executed automatically when a Process is instantiated.)

        This will also run the subprocess as a given user ID and group ID, if
        specified.  (Implementation Note: this doesn't support all the arcane
        nuances of setXXuid on UNIX: it will assume that either your effective
        or real UID is 0.)
        """
        if not proto:
            assert "r" not in childFDs.values()
            assert "w" not in childFDs.values()
        _BaseProcess.__init__(self, proto)

        self.pipes = {}
        # keys are childFDs, we can sense them closing
        # values are ProcessReader/ProcessWriters

        helpers = {}
        # keys are childFDs
        # values are parentFDs

        if childFDs is None:
            childFDs = {
                0: "w",  # we write to the child's stdin
                1: "r",  # we read from their stdout
                2: "r",  # and we read from their stderr
            }

        debug = self.debug
        if debug:
            print("childFDs", childFDs)

        _openedPipes = []

        def pipe():
            r, w = os.pipe()
            _openedPipes.extend([r, w])
            return r, w

        # fdmap.keys() are filenos of pipes that are used by the child.
        fdmap = {}  # maps childFD to parentFD
        try:
            for childFD, target in childFDs.items():
                if debug:
                    print("[%d]" % childFD, target)
                if target == "r":
                    # we need a pipe that the parent can read from
                    readFD, writeFD = pipe()
                    if debug:
                        print("readFD=%d, writeFD=%d" % (readFD, writeFD))
                    fdmap[childFD] = writeFD  # child writes to this
                    helpers[childFD] = readFD  # parent reads from this
                elif target == "w":
                    # we need a pipe that the parent can write to
                    readFD, writeFD = pipe()
                    if debug:
                        print("readFD=%d, writeFD=%d" % (readFD, writeFD))
                    fdmap[childFD] = readFD  # child reads from this
                    helpers[childFD] = writeFD  # parent writes to this
                else:
                    assert type(target) == int, f"{target!r} should be an int"
                    fdmap[childFD] = target  # parent ignores this
            if debug:
                print("fdmap", fdmap)
            if debug:
                print("helpers", helpers)
            # the child only cares about fdmap.values()

            self._fork(path, uid, gid, executable, args, environment, fdmap=fdmap)
        except BaseException:
            for pipe in _openedPipes:
                os.close(pipe)
            raise

        # we are the parent process:
        self.proto = proto

        # arrange for the parent-side pipes to be read and written
        for childFD, parentFD in helpers.items():
            os.close(fdmap[childFD])
            if childFDs[childFD] == "r":
                reader = self.processReaderFactory(reactor, self, childFD, parentFD)
                self.pipes[childFD] = reader

            if childFDs[childFD] == "w":
                writer = self.processWriterFactory(
                    reactor, self, childFD, parentFD, forceReadHack=True
                )
                self.pipes[childFD] = writer

        try:
            # the 'transport' is used for some compatibility methods
            if self.proto is not None:
                self.proto.makeConnection(self)
        except BaseException:
            log.err()

        # The reactor might not be running yet.  This might call back into
        # processEnded synchronously, triggering an application-visible
        # callback.  That's probably not ideal.  The replacement API for
        # spawnProcess should improve upon this situation.
        registerReapProcessHandler(self.pid, self)

    def _setupChild(self, fdmap):
        """
        fdmap[childFD] = parentFD

        The child wants to end up with 'childFD' attached to what used to be
        the parent's parentFD. As an example, a bash command run like
        'command 2>&1' would correspond to an fdmap of {0:0, 1:1, 2:1}.
        'command >foo.txt' would be {0:0, 1:os.open('foo.txt'), 2:2}.

        This is accomplished in two steps::

            1. close all file descriptors that aren't values of fdmap.  This
               means 0 .. maxfds (or just the open fds within that range, if
               the platform supports '/proc/<pid>/fd').

            2. for each childFD::

                 - if fdmap[childFD] == childFD, the descriptor is already in
                   place.  Make sure the CLOEXEC flag is not set, then delete
                   the entry from fdmap.

                 - if childFD is in fdmap.values(), then the target descriptor
                   is busy. Use os.dup() to move it elsewhere, update all
                   fdmap[childFD] items that point to it, then close the
                   original. Then fall through to the next case.

                 - now fdmap[childFD] is not in fdmap.values(), and is free.
                   Use os.dup2() to move it to the right place, then close the
                   original.
        """
        debug = self.debug_child
        if debug:
            errfd = sys.stderr
            errfd.write("starting _setupChild\n")

        destList = fdmap.values()
        for fd in _listOpenFDs():
            if fd in destList:
                continue
            if debug and fd == errfd.fileno():
                continue
            try:
                os.close(fd)
            except BaseException:
                pass

        # at this point, the only fds still open are the ones that need to
        # be moved to their appropriate positions in the child (the targets
        # of fdmap, i.e. fdmap.values() )

        if debug:
            print("fdmap", fdmap, file=errfd)
        for child in sorted(fdmap.keys()):
            target = fdmap[child]
            if target == child:
                # fd is already in place
                if debug:
                    print("%d already in place" % target, file=errfd)
                fdesc._unsetCloseOnExec(child)
            else:
                if child in fdmap.values():
                    # we can't replace child-fd yet, as some other mapping
                    # still needs the fd it wants to target. We must preserve
                    # that old fd by duping it to a new home.
                    newtarget = os.dup(child)  # give it a safe home
                    if debug:
                        print("os.dup(%d) -> %d" % (child, newtarget), file=errfd)
                    os.close(child)  # close the original
                    for c, p in list(fdmap.items()):
                        if p == child:
                            fdmap[c] = newtarget  # update all pointers
                # now it should be available
                if debug:
                    print("os.dup2(%d,%d)" % (target, child), file=errfd)
                os.dup2(target, child)

        # At this point, the child has everything it needs. We want to close
        # everything that isn't going to be used by the child, i.e.
        # everything not in fdmap.keys(). The only remaining fds open are
        # those in fdmap.values().

        # Any given fd may appear in fdmap.values() multiple times, so we
        # need to remove duplicates first.

        old = []
        for fd in fdmap.values():
            if fd not in old:
                if fd not in fdmap.keys():
                    old.append(fd)
        if debug:
            print("old", old, file=errfd)
        for fd in old:
            os.close(fd)

        self._resetSignalDisposition()

    def writeToChild(self, childFD, data):
        self.pipes[childFD].write(data)

    def closeChildFD(self, childFD):
        # for writer pipes, loseConnection tries to write the remaining data
        # out to the pipe before closing it
        # if childFD is not in the list of pipes, assume that it is already
        # closed
        if childFD in self.pipes:
            self.pipes[childFD].loseConnection()

    def pauseProducing(self):
        for p in self.pipes.values():
            if isinstance(p, ProcessReader):
                p.stopReading()

    def resumeProducing(self):
        for p in self.pipes.values():
            if isinstance(p, ProcessReader):
                p.startReading()

    # compatibility
    def closeStdin(self):
        """
        Call this to close standard input on this process.
        """
        self.closeChildFD(0)

    def closeStdout(self):
        self.closeChildFD(1)

    def closeStderr(self):
        self.closeChildFD(2)

    def loseConnection(self):
        self.closeStdin()
        self.closeStderr()
        self.closeStdout()

    def write(self, data):
        """
        Call this to write to standard input on this process.

        NOTE: This will silently lose data if there is no standard input.
        """
        if 0 in self.pipes:
            self.pipes[0].write(data)

    def registerProducer(self, producer, streaming):
        """
        Call this to register producer for standard input.

        If there is no standard input producer.stopProducing() will
        be called immediately.
        """
        if 0 in self.pipes:
            self.pipes[0].registerProducer(producer, streaming)
        else:
            producer.stopProducing()

    def unregisterProducer(self):
        """
        Call this to unregister producer for standard input."""
        if 0 in self.pipes:
            self.pipes[0].unregisterProducer()

    def writeSequence(self, seq):
        """
        Call this to write to standard input on this process.

        NOTE: This will silently lose data if there is no standard input.
        """
        if 0 in self.pipes:
            self.pipes[0].writeSequence(seq)

    def childDataReceived(self, name, data):
        self.proto.childDataReceived(name, data)

    def childConnectionLost(self, childFD, reason):
        # this is called when one of the helpers (ProcessReader or
        # ProcessWriter) notices their pipe has been closed
        os.close(self.pipes[childFD].fileno())
        del self.pipes[childFD]
        try:
            self.proto.childConnectionLost(childFD)
        except BaseException:
            log.err()
        self.maybeCallProcessEnded()

    def maybeCallProcessEnded(self):
        # we don't call ProcessProtocol.processEnded until:
        #  the child has terminated, AND
        #  all writers have indicated an error status, AND
        #  all readers have indicated EOF
        # This insures that we've gathered all output from the process.
        if self.pipes:
            return
        if not self.lostProcess:
            self.reapProcess()
            return
        _BaseProcess.maybeCallProcessEnded(self)

    def getHost(self):
        # ITransport.getHost
        raise NotImplementedError()

    def getPeer(self):
        # ITransport.getPeer
        raise NotImplementedError()


@implementer(IProcessTransport)
class PTYProcess(abstract.FileDescriptor, _BaseProcess):
    """
    An operating-system Process that uses PTY support.
    """

    status = -1
    pid = None

    def __init__(
        self,
        reactor,
        executable,
        args,
        environment,
        path,
        proto,
        uid=None,
        gid=None,
        usePTY=None,
    ):
        """
        Spawn an operating-system process.

        This is where the hard work of disconnecting all currently open
        files / forking / executing the new process happens.  (This is
        executed automatically when a Process is instantiated.)

        This will also run the subprocess as a given user ID and group ID, if
        specified.  (Implementation Note: this doesn't support all the arcane
        nuances of setXXuid on UNIX: it will assume that either your effective
        or real UID is 0.)
        """
        if pty is None and not isinstance(usePTY, (tuple, list)):
            # no pty module and we didn't get a pty to use
            raise NotImplementedError(
                "cannot use PTYProcess on platforms without the pty module."
            )
        abstract.FileDescriptor.__init__(self, reactor)
        _BaseProcess.__init__(self, proto)

        if isinstance(usePTY, (tuple, list)):
            masterfd, slavefd, _ = usePTY
        else:
            masterfd, slavefd = pty.openpty()

        try:
            self._fork(
                path,
                uid,
                gid,
                executable,
                args,
                environment,
                masterfd=masterfd,
                slavefd=slavefd,
            )
        except BaseException:
            if not isinstance(usePTY, (tuple, list)):
                os.close(masterfd)
                os.close(slavefd)
            raise

        # we are now in parent process:
        os.close(slavefd)
        fdesc.setNonBlocking(masterfd)
        self.fd = masterfd
        self.startReading()
        self.connected = 1
        self.status = -1
        try:
            self.proto.makeConnection(self)
        except BaseException:
            log.err()
        registerReapProcessHandler(self.pid, self)

    def _setupChild(self, masterfd, slavefd):
        """
        Set up child process after C{fork()} but before C{exec()}.

        This involves:

            - closing C{masterfd}, since it is not used in the subprocess

            - creating a new session with C{os.setsid}

            - changing the controlling terminal of the process (and the new
              session) to point at C{slavefd}

            - duplicating C{slavefd} to standard input, output, and error

            - closing all other open file descriptors (according to
              L{_listOpenFDs})

            - re-setting all signal handlers to C{SIG_DFL}

        @param masterfd: The master end of a PTY file descriptors opened with
            C{openpty}.
        @type masterfd: L{int}

        @param slavefd: The slave end of a PTY opened with C{openpty}.
        @type slavefd: L{int}
        """
        os.close(masterfd)
        os.setsid()
        fcntl.ioctl(slavefd, termios.TIOCSCTTY, "")

        for fd in range(3):
            if fd != slavefd:
                os.close(fd)

        os.dup2(slavefd, 0)  # stdin
        os.dup2(slavefd, 1)  # stdout
        os.dup2(slavefd, 2)  # stderr

        for fd in _listOpenFDs():
            if fd > 2:
                try:
                    os.close(fd)
                except BaseException:
                    pass

        self._resetSignalDisposition()

    def closeStdin(self):
        # PTYs do not have stdin/stdout/stderr. They only have in and out, just
        # like sockets. You cannot close one without closing off the entire PTY
        pass

    def closeStdout(self):
        pass

    def closeStderr(self):
        pass

    def doRead(self):
        """
        Called when my standard output stream is ready for reading.
        """
        return fdesc.readFromFD(
            self.fd, lambda data: self.proto.childDataReceived(1, data)
        )

    def fileno(self):
        """
        This returns the file number of standard output on this process.
        """
        return self.fd

    def maybeCallProcessEnded(self):
        # two things must happen before we call the ProcessProtocol's
        # processEnded method. 1: the child process must die and be reaped
        # (which calls our own processEnded method). 2: the child must close
        # their stdin/stdout/stderr fds, causing the pty to close, causing
        # our connectionLost method to be called. #2 can also be triggered
        # by calling .loseConnection().
        if self.lostProcess == 2:
            _BaseProcess.maybeCallProcessEnded(self)

    def connectionLost(self, reason):
        """
        I call this to clean up when one or all of my connections has died.
        """
        abstract.FileDescriptor.connectionLost(self, reason)
        os.close(self.fd)
        self.lostProcess += 1
        self.maybeCallProcessEnded()

    def writeSomeData(self, data):
        """
        Write some data to the open process.
        """
        return fdesc.writeToFD(self.fd, data)

    def closeChildFD(self, descriptor):
        # IProcessTransport
        raise NotImplementedError()

    def writeToChild(self, childFD, data):
        # IProcessTransport
        raise NotImplementedError()
