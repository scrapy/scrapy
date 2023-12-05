# -*- test-case-name: twisted.test.test_twistd -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


import errno
import os
import pwd
import sys
import traceback

from twisted import copyright, logger
from twisted.application import app, service
from twisted.internet.interfaces import IReactorDaemonize
from twisted.python import log, logfile, usage
from twisted.python.runtime import platformType
from twisted.python.util import gidFromString, switchUID, uidFromString, untilConcludes

if platformType == "win32":
    raise ImportError("_twistd_unix doesn't work on Windows.")


def _umask(value):
    return int(value, 8)


class ServerOptions(app.ServerOptions):
    synopsis = "Usage: twistd [options]"

    optFlags = [
        ["nodaemon", "n", "don't daemonize, don't use default umask of 0077"],
        ["originalname", None, "Don't try to change the process name"],
        ["syslog", None, "Log to syslog, not to file"],
        [
            "euid",
            "",
            "Set only effective user-id rather than real user-id. "
            "(This option has no effect unless the server is running as "
            "root, in which case it means not to shed all privileges "
            "after binding ports, retaining the option to regain "
            "privileges in cases such as spawning processes. "
            "Use with caution.)",
        ],
    ]

    optParameters = [
        ["prefix", None, "twisted", "use the given prefix when syslogging"],
        ["pidfile", "", "twistd.pid", "Name of the pidfile"],
        ["chroot", None, None, "Chroot to a supplied directory before running"],
        ["uid", "u", None, "The uid to run as.", uidFromString],
        [
            "gid",
            "g",
            None,
            "The gid to run as.  If not specified, the default gid "
            "associated with the specified --uid is used.",
            gidFromString,
        ],
        ["umask", None, None, "The (octal) file creation mask to apply.", _umask],
    ]

    compData = usage.Completions(
        optActions={
            "pidfile": usage.CompleteFiles("*.pid"),
            "chroot": usage.CompleteDirs(descr="chroot directory"),
            "gid": usage.CompleteGroups(descr="gid to run as"),
            "uid": usage.CompleteUsernames(descr="uid to run as"),
            "prefix": usage.Completer(descr="syslog prefix"),
        },
    )

    def opt_version(self):
        """
        Print version information and exit.
        """
        print(f"twistd (the Twisted daemon) {copyright.version}", file=self.stdout)
        print(copyright.copyright, file=self.stdout)
        sys.exit()

    def postOptions(self):
        app.ServerOptions.postOptions(self)
        if self["pidfile"]:
            self["pidfile"] = os.path.abspath(self["pidfile"])


def checkPID(pidfile):
    if not pidfile:
        return
    if os.path.exists(pidfile):
        try:
            with open(pidfile) as f:
                pid = int(f.read())
        except ValueError:
            sys.exit(f"Pidfile {pidfile} contains non-numeric value")
        try:
            os.kill(pid, 0)
        except OSError as why:
            if why.errno == errno.ESRCH:
                # The pid doesn't exist.
                log.msg(f"Removing stale pidfile {pidfile}", isError=True)
                os.remove(pidfile)
            else:
                sys.exit(
                    "Can't check status of PID {} from pidfile {}: {}".format(
                        pid, pidfile, why
                    )
                )
        else:
            sys.exit(
                """\
Another twistd server is running, PID {}\n
This could either be a previously started instance of your application or a
different application entirely. To start a new one, either run it in some other
directory, or use the --pidfile and --logfile parameters to avoid clashes.
""".format(
                    pid
                )
            )


class UnixAppLogger(app.AppLogger):
    """
    A logger able to log to syslog, to files, and to stdout.

    @ivar _syslog: A flag indicating whether to use syslog instead of file
        logging.
    @type _syslog: C{bool}

    @ivar _syslogPrefix: If C{sysLog} is C{True}, the string prefix to use for
        syslog messages.
    @type _syslogPrefix: C{str}

    @ivar _nodaemon: A flag indicating the process will not be daemonizing.
    @type _nodaemon: C{bool}
    """

    def __init__(self, options):
        app.AppLogger.__init__(self, options)
        self._syslog = options.get("syslog", False)
        self._syslogPrefix = options.get("prefix", "")
        self._nodaemon = options.get("nodaemon", False)

    def _getLogObserver(self):
        """
        Create and return a suitable log observer for the given configuration.

        The observer will go to syslog using the prefix C{_syslogPrefix} if
        C{_syslog} is true.  Otherwise, it will go to the file named
        C{_logfilename} or, if C{_nodaemon} is true and C{_logfilename} is
        C{"-"}, to stdout.

        @return: An object suitable to be passed to C{log.addObserver}.
        """
        if self._syslog:
            from twisted.python import syslog

            return syslog.SyslogObserver(self._syslogPrefix).emit

        if self._logfilename == "-":
            if not self._nodaemon:
                sys.exit("Daemons cannot log to stdout, exiting!")
            logFile = sys.stdout
        elif self._nodaemon and not self._logfilename:
            logFile = sys.stdout
        else:
            if not self._logfilename:
                self._logfilename = "twistd.log"
            logFile = logfile.LogFile.fromFullPath(self._logfilename)
            try:
                import signal
            except ImportError:
                pass
            else:
                # Override if signal is set to None or SIG_DFL (0)
                if not signal.getsignal(signal.SIGUSR1):

                    def rotateLog(signal, frame):
                        from twisted.internet import reactor

                        reactor.callFromThread(logFile.rotate)

                    signal.signal(signal.SIGUSR1, rotateLog)
        return logger.textFileLogObserver(logFile)


def launchWithName(name):
    if name and name != sys.argv[0]:
        exe = os.path.realpath(sys.executable)
        log.msg("Changing process name to " + name)
        os.execv(exe, [name, sys.argv[0], "--originalname"] + sys.argv[1:])


class UnixApplicationRunner(app.ApplicationRunner):
    """
    An ApplicationRunner which does Unix-specific things, like fork,
    shed privileges, and maintain a PID file.
    """

    loggerFactory = UnixAppLogger

    def preApplication(self):
        """
        Do pre-application-creation setup.
        """
        checkPID(self.config["pidfile"])
        self.config["nodaemon"] = self.config["nodaemon"] or self.config["debug"]
        self.oldstdout = sys.stdout
        self.oldstderr = sys.stderr

    def _formatChildException(self, exception):
        """
        Format the C{exception} in preparation for writing to the
        status pipe.  This does the right thing on Python 2 if the
        exception's message is Unicode, and in all cases limits the
        length of the message afte* encoding to 100 bytes.

        This means the returned message may be truncated in the middle
        of a unicode escape.

        @type exception: L{Exception}
        @param exception: The exception to format.

        @return: The formatted message, suitable for writing to the
            status pipe.
        @rtype: L{bytes}
        """
        # On Python 2 this will encode Unicode messages with the ascii
        # codec and the backslashreplace error handler.
        exceptionLine = traceback.format_exception_only(exception.__class__, exception)[
            -1
        ]
        # remove the trailing newline
        formattedMessage = f"1 {exceptionLine.strip()}"
        # On Python 3, encode the message the same way Python 2's
        # format_exception_only does
        formattedMessage = formattedMessage.encode("ascii", "backslashreplace")
        # By this point, the message has been encoded, if appropriate,
        # with backslashreplace on both Python 2 and Python 3.
        # Truncating the encoded message won't make it completely
        # unreadable, and the reader should print out the repr of the
        # message it receives anyway.  What it will do, however, is
        # ensure that only 100 bytes are written to the status pipe,
        # ensuring that the child doesn't block because the pipe's
        # full.  This assumes PIPE_BUF > 100!
        return formattedMessage[:100]

    def postApplication(self):
        """
        To be called after the application is created: start the application
        and run the reactor. After the reactor stops, clean up PID files and
        such.
        """
        try:
            self.startApplication(self.application)
        except Exception as ex:
            statusPipe = self.config.get("statusPipe", None)
            if statusPipe is not None:
                message = self._formatChildException(ex)
                untilConcludes(os.write, statusPipe, message)
                untilConcludes(os.close, statusPipe)
            self.removePID(self.config["pidfile"])
            raise
        else:
            statusPipe = self.config.get("statusPipe", None)
            if statusPipe is not None:
                untilConcludes(os.write, statusPipe, b"0")
                untilConcludes(os.close, statusPipe)
        self.startReactor(None, self.oldstdout, self.oldstderr)
        self.removePID(self.config["pidfile"])

    def removePID(self, pidfile):
        """
        Remove the specified PID file, if possible.  Errors are logged, not
        raised.

        @type pidfile: C{str}
        @param pidfile: The path to the PID tracking file.
        """
        if not pidfile:
            return
        try:
            os.unlink(pidfile)
        except OSError as e:
            if e.errno == errno.EACCES or e.errno == errno.EPERM:
                log.msg("Warning: No permission to delete pid file")
            else:
                log.err(e, "Failed to unlink PID file:")
        except BaseException:
            log.err(None, "Failed to unlink PID file:")

    def setupEnvironment(self, chroot, rundir, nodaemon, umask, pidfile):
        """
        Set the filesystem root, the working directory, and daemonize.

        @type chroot: C{str} or L{None}
        @param chroot: If not None, a path to use as the filesystem root (using
            L{os.chroot}).

        @type rundir: C{str}
        @param rundir: The path to set as the working directory.

        @type nodaemon: C{bool}
        @param nodaemon: A flag which, if set, indicates that daemonization
            should not be done.

        @type umask: C{int} or L{None}
        @param umask: The value to which to change the process umask.

        @type pidfile: C{str} or L{None}
        @param pidfile: If not L{None}, the path to a file into which to put
            the PID of this process.
        """
        daemon = not nodaemon

        if chroot is not None:
            os.chroot(chroot)
            if rundir == ".":
                rundir = "/"
        os.chdir(rundir)
        if daemon and umask is None:
            umask = 0o077
        if umask is not None:
            os.umask(umask)
        if daemon:
            from twisted.internet import reactor

            self.config["statusPipe"] = self.daemonize(reactor)
        if pidfile:
            with open(pidfile, "wb") as f:
                f.write(b"%d" % (os.getpid(),))

    def daemonize(self, reactor):
        """
        Daemonizes the application on Unix. This is done by the usual double
        forking approach.

        @see: U{http://code.activestate.com/recipes/278731/}
        @see: W. Richard Stevens,
            "Advanced Programming in the Unix Environment",
            1992, Addison-Wesley, ISBN 0-201-56317-7

        @param reactor: The reactor in use.  If it provides
            L{IReactorDaemonize}, its daemonization-related callbacks will be
            invoked.

        @return: A writable pipe to be used to report errors.
        @rtype: C{int}
        """
        # If the reactor requires hooks to be called for daemonization, call
        # them. Currently the only reactor which provides/needs that is
        # KQueueReactor.
        if IReactorDaemonize.providedBy(reactor):
            reactor.beforeDaemonize()
        r, w = os.pipe()
        if os.fork():  # launch child and...
            code = self._waitForStart(r)
            os.close(r)
            os._exit(code)  # kill off parent
        os.setsid()
        if os.fork():  # launch child and...
            os._exit(0)  # kill off parent again.
        null = os.open("/dev/null", os.O_RDWR)
        for i in range(3):
            try:
                os.dup2(null, i)
            except OSError as e:
                if e.errno != errno.EBADF:
                    raise
        os.close(null)

        if IReactorDaemonize.providedBy(reactor):
            reactor.afterDaemonize()

        return w

    def _waitForStart(self, readPipe: int) -> int:
        """
        Wait for the daemonization success.

        @param readPipe: file descriptor to read start information from.
        @type readPipe: C{int}

        @return: code to be passed to C{os._exit}: 0 for success, 1 for error.
        @rtype: C{int}
        """
        data = untilConcludes(os.read, readPipe, 100)
        dataRepr = repr(data[2:])
        if data != b"0":
            msg = (
                "An error has occurred: {}\nPlease look at log "
                "file for more information.\n".format(dataRepr)
            )
            untilConcludes(sys.__stderr__.write, msg)
            return 1
        return 0

    def shedPrivileges(self, euid, uid, gid):
        """
        Change the UID and GID or the EUID and EGID of this process.

        @type euid: C{bool}
        @param euid: A flag which, if set, indicates that only the I{effective}
            UID and GID should be set.

        @type uid: C{int} or L{None}
        @param uid: If not L{None}, the UID to which to switch.

        @type gid: C{int} or L{None}
        @param gid: If not L{None}, the GID to which to switch.
        """
        if uid is not None or gid is not None:
            extra = euid and "e" or ""
            desc = f"{extra}uid/{extra}gid {uid}/{gid}"
            try:
                switchUID(uid, gid, euid)
            except OSError as e:
                log.msg(
                    "failed to set {}: {} (are you root?) -- "
                    "exiting.".format(desc, e)
                )
                sys.exit(1)
            else:
                log.msg(f"set {desc}")

    def startApplication(self, application):
        """
        Configure global process state based on the given application and run
        the application.

        @param application: An object which can be adapted to
            L{service.IProcess} and L{service.IService}.
        """
        process = service.IProcess(application)
        if not self.config["originalname"]:
            launchWithName(process.processName)
        self.setupEnvironment(
            self.config["chroot"],
            self.config["rundir"],
            self.config["nodaemon"],
            self.config["umask"],
            self.config["pidfile"],
        )

        service.IService(application).privilegedStartService()

        uid, gid = self.config["uid"], self.config["gid"]
        if uid is None:
            uid = process.uid
        if gid is None:
            gid = process.gid
        if uid is not None and gid is None:
            gid = pwd.getpwuid(uid).pw_gid

        self.shedPrivileges(self.config["euid"], uid, gid)
        app.startApplication(application, not self.config["no_save"])
