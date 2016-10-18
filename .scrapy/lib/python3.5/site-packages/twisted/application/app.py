# -*- test-case-name: twisted.test.test_application,twisted.test.test_twistd -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import absolute_import, division, print_function

import sys
import os
import pdb
import getpass
import traceback
import signal
import warnings

from operator import attrgetter

from twisted import copyright, plugin, logger
from twisted.application import service, reactors
from twisted.internet import defer
from twisted.persisted import sob
from twisted.python import runtime, log, usage, failure, util, logfile
from twisted.python.reflect import qual, namedAny

# Expose the new implementation of installReactor at the old location.
from twisted.application.reactors import installReactor
from twisted.application.reactors import NoSuchReactor


class _BasicProfiler(object):
    """
    @ivar saveStats: if C{True}, save the stats information instead of the
        human readable format
    @type saveStats: C{bool}

    @ivar profileOutput: the name of the file use to print profile data.
    @type profileOutput: C{str}
    """

    def __init__(self, profileOutput, saveStats):
        self.profileOutput = profileOutput
        self.saveStats = saveStats


    def _reportImportError(self, module, e):
        """
        Helper method to report an import error with a profile module. This
        has to be explicit because some of these modules are removed by
        distributions due to them being non-free.
        """
        s = "Failed to import module %s: %s" % (module, e)
        s += """
This is most likely caused by your operating system not including
the module due to it being non-free. Either do not use the option
--profile, or install the module; your operating system vendor
may provide it in a separate package.
"""
        raise SystemExit(s)



class ProfileRunner(_BasicProfiler):
    """
    Runner for the standard profile module.
    """

    def run(self, reactor):
        """
        Run reactor under the standard profiler.
        """
        try:
            import profile
        except ImportError as e:
            self._reportImportError("profile", e)

        p = profile.Profile()
        p.runcall(reactor.run)
        if self.saveStats:
            p.dump_stats(self.profileOutput)
        else:
            tmp, sys.stdout = sys.stdout, open(self.profileOutput, 'a')
            try:
                p.print_stats()
            finally:
                sys.stdout, tmp = tmp, sys.stdout
                tmp.close()



class CProfileRunner(_BasicProfiler):
    """
    Runner for the cProfile module.
    """

    def run(self, reactor):
        """
        Run reactor under the cProfile profiler.
        """
        try:
            import cProfile
            import pstats
        except ImportError as e:
            self._reportImportError("cProfile", e)

        p = cProfile.Profile()
        p.runcall(reactor.run)
        if self.saveStats:
            p.dump_stats(self.profileOutput)
        else:
            with open(self.profileOutput, 'w') as stream:
                s = pstats.Stats(p, stream=stream)
                s.strip_dirs()
                s.sort_stats(-1)
                s.print_stats()



class AppProfiler(object):
    """
    Class which selects a specific profile runner based on configuration
    options.

    @ivar profiler: the name of the selected profiler.
    @type profiler: C{str}
    """
    profilers = {"profile": ProfileRunner, "cprofile": CProfileRunner}

    def __init__(self, options):
        saveStats = options.get("savestats", False)
        profileOutput = options.get("profile", None)
        self.profiler = options.get("profiler", "cprofile").lower()
        if self.profiler in self.profilers:
            profiler = self.profilers[self.profiler](profileOutput, saveStats)
            self.run = profiler.run
        else:
            raise SystemExit("Unsupported profiler name: %s" %
                             (self.profiler,))



class AppLogger(object):
    """
    An L{AppLogger} attaches the configured log observer specified on the
    commandline to a L{ServerOptions} object, a custom L{logger.ILogObserver},
    or a legacy custom {log.ILogObserver}.

    @ivar _logfilename: The name of the file to which to log, if other than the
        default.
    @type _logfilename: C{str}

    @ivar _observerFactory: Callable object that will create a log observer, or
        None.

    @ivar _observer: log observer added at C{start} and removed at C{stop}.
    @type _observer: a callable that implements L{logger.ILogObserver} or
        L{log.ILogObserver}.
    """
    _observer = None

    def __init__(self, options):
        """
        Initialize an L{AppLogger} with a L{ServerOptions}.
        """
        self._logfilename = options.get("logfile", "")
        self._observerFactory = options.get("logger") or None


    def start(self, application):
        """
        Initialize the global logging system for the given application.

        If a custom logger was specified on the command line it will be used.
        If not, and an L{logger.ILogObserver} or legacy L{log.ILogObserver}
        component has been set on C{application}, then it will be used as the
        log observer. Otherwise a log observer will be created based on the
        command line options for built-in loggers (e.g. C{--logfile}).

        @param application: The application on which to check for an
            L{logger.ILogObserver} or legacy L{log.ILogObserver}.
        @type application: L{twisted.python.components.Componentized}
        """
        if self._observerFactory is not None:
            observer = self._observerFactory()
        else:
            observer = application.getComponent(logger.ILogObserver, None)
            if observer is None:
                # If there's no new ILogObserver, try the legacy one
                observer = application.getComponent(log.ILogObserver, None)

        if observer is None:
            observer = self._getLogObserver()
        self._observer = observer

        if logger.ILogObserver.providedBy(self._observer):
            observers = [self._observer]
        elif log.ILogObserver.providedBy(self._observer):
            observers = [logger.LegacyLogObserverWrapper(self._observer)]
        else:
            warnings.warn(
                ("Passing a logger factory which makes log observers which do "
                 "not implement twisted.logger.ILogObserver or "
                 "twisted.python.log.ILogObserver to "
                 "twisted.application.app.AppLogger was deprecated in "
                 "Twisted 16.2. Please use a factory that produces "
                 "twisted.logger.ILogObserver (or the legacy "
                 "twisted.python.log.ILogObserver) implementing objects "
                 "instead."),
                DeprecationWarning,
                stacklevel=2)
            observers = [logger.LegacyLogObserverWrapper(self._observer)]

        logger.globalLogBeginner.beginLoggingTo(observers)
        self._initialLog()


    def _initialLog(self):
        """
        Print twistd start log message.
        """
        from twisted.internet import reactor
        logger._loggerFor(self).info(
            "twistd {version} ({exe} {pyVersion}) starting up.",
            version=copyright.version, exe=sys.executable,
            pyVersion=runtime.shortPythonVersion())
        logger._loggerFor(self).info('reactor class: {reactor}.',
                                     reactor=qual(reactor.__class__))


    def _getLogObserver(self):
        """
        Create a log observer to be added to the logging system before running
        this application.
        """
        if self._logfilename == '-' or not self._logfilename:
            logFile = sys.stdout
        else:
            logFile = logfile.LogFile.fromFullPath(self._logfilename)
        return logger.textFileLogObserver(logFile)


    def stop(self):
        """
        Remove all log observers previously set up by L{AppLogger.start}.
        """
        logger._loggerFor(self).info("Server Shut Down.")
        if self._observer is not None:
            logger.globalLogPublisher.removeObserver(self._observer)
            self._observer = None



def fixPdb():
    def do_stop(self, arg):
        self.clear_all_breaks()
        self.set_continue()
        from twisted.internet import reactor
        reactor.callLater(0, reactor.stop)
        return 1


    def help_stop(self):
        print("stop - Continue execution, then cleanly shutdown the twisted "
              "reactor.")


    def set_quit(self):
        os._exit(0)

    pdb.Pdb.set_quit = set_quit
    pdb.Pdb.do_stop = do_stop
    pdb.Pdb.help_stop = help_stop



def runReactorWithLogging(config, oldstdout, oldstderr, profiler=None,
                          reactor=None):
    """
    Start the reactor, using profiling if specified by the configuration, and
    log any error happening in the process.

    @param config: configuration of the twistd application.
    @type config: L{ServerOptions}

    @param oldstdout: initial value of C{sys.stdout}.
    @type oldstdout: C{file}

    @param oldstderr: initial value of C{sys.stderr}.
    @type oldstderr: C{file}

    @param profiler: object used to run the reactor with profiling.
    @type profiler: L{AppProfiler}

    @param reactor: The reactor to use.  If L{None}, the global reactor will
        be used.
    """
    if reactor is None:
        from twisted.internet import reactor
    try:
        if config['profile']:
            if profiler is not None:
                profiler.run(reactor)
        elif config['debug']:
            sys.stdout = oldstdout
            sys.stderr = oldstderr
            if runtime.platformType == 'posix':
                signal.signal(signal.SIGUSR2, lambda *args: pdb.set_trace())
                signal.signal(signal.SIGINT, lambda *args: pdb.set_trace())
            fixPdb()
            pdb.runcall(reactor.run)
        else:
            reactor.run()
    except:
        close = False
        if config['nodaemon']:
            file = oldstdout
        else:
            file = open("TWISTD-CRASH.log", "a")
            close = True
        try:
            traceback.print_exc(file=file)
            file.flush()
        finally:
            if close:
                file.close()



def getPassphrase(needed):
    if needed:
        return getpass.getpass('Passphrase: ')
    else:
        return None



def getSavePassphrase(needed):
    if needed:
        return util.getPassword("Encryption passphrase: ")
    else:
        return None



class ApplicationRunner(object):
    """
    An object which helps running an application based on a config object.

    Subclass me and implement preApplication and postApplication
    methods. postApplication generally will want to run the reactor
    after starting the application.

    @ivar config: The config object, which provides a dict-like interface.

    @ivar application: Available in postApplication, but not
       preApplication. This is the application object.

    @ivar profilerFactory: Factory for creating a profiler object, able to
        profile the application if options are set accordingly.

    @ivar profiler: Instance provided by C{profilerFactory}.

    @ivar loggerFactory: Factory for creating object responsible for logging.

    @ivar logger: Instance provided by C{loggerFactory}.
    """
    profilerFactory = AppProfiler
    loggerFactory = AppLogger

    def __init__(self, config):
        self.config = config
        self.profiler = self.profilerFactory(config)
        self.logger = self.loggerFactory(config)


    def run(self):
        """
        Run the application.
        """
        self.preApplication()
        self.application = self.createOrGetApplication()

        self.logger.start(self.application)

        self.postApplication()
        self.logger.stop()


    def startReactor(self, reactor, oldstdout, oldstderr):
        """
        Run the reactor with the given configuration.  Subclasses should
        probably call this from C{postApplication}.

        @see: L{runReactorWithLogging}
        """
        runReactorWithLogging(
            self.config, oldstdout, oldstderr, self.profiler, reactor)


    def preApplication(self):
        """
        Override in subclass.

        This should set up any state necessary before loading and
        running the Application.
        """
        raise NotImplementedError()


    def postApplication(self):
        """
        Override in subclass.

        This will be called after the application has been loaded (so
        the C{application} attribute will be set). Generally this
        should start the application and run the reactor.
        """
        raise NotImplementedError()


    def createOrGetApplication(self):
        """
        Create or load an Application based on the parameters found in the
        given L{ServerOptions} instance.

        If a subcommand was used, the L{service.IServiceMaker} that it
        represents will be used to construct a service to be added to
        a newly-created Application.

        Otherwise, an application will be loaded based on parameters in
        the config.
        """
        if self.config.subCommand:
            # If a subcommand was given, it's our responsibility to create
            # the application, instead of load it from a file.

            # loadedPlugins is set up by the ServerOptions.subCommands
            # property, which is iterated somewhere in the bowels of
            # usage.Options.
            plg = self.config.loadedPlugins[self.config.subCommand]
            ser = plg.makeService(self.config.subOptions)
            application = service.Application(plg.tapname)
            ser.setServiceParent(application)
        else:
            passphrase = getPassphrase(self.config['encrypted'])
            application = getApplication(self.config, passphrase)
        return application



def getApplication(config, passphrase):
    s = [(config[t], t)
         for t in ['python', 'source', 'file'] if config[t]][0]
    filename, style = s[0], {'file': 'pickle'}.get(s[1], s[1])
    try:
        log.msg("Loading %s..." % filename)
        application = service.loadApplication(filename, style, passphrase)
        log.msg("Loaded.")
    except Exception as e:
        s = "Failed to load application: %s" % e
        if isinstance(e, KeyError) and e.args[0] == "application":
            s += """
Could not find 'application' in the file. To use 'twistd -y', your .tac
file must create a suitable object (e.g., by calling service.Application())
and store it in a variable named 'application'. twistd loads your .tac file
and scans the global variables for one of this name.

Please read the 'Using Application' HOWTO for details.
"""
        traceback.print_exc(file=log.logfile)
        log.msg(s)
        log.deferr()
        sys.exit('\n' + s + '\n')
    return application



def _reactorAction():
    return usage.CompleteList([r.shortName for r in
                               reactors.getReactorTypes()])



class ReactorSelectionMixin:
    """
    Provides options for selecting a reactor to install.

    If a reactor is installed, the short name which was used to locate it is
    saved as the value for the C{"reactor"} key.
    """
    compData = usage.Completions(
        optActions={"reactor": _reactorAction})

    messageOutput = sys.stdout
    _getReactorTypes = staticmethod(reactors.getReactorTypes)


    def opt_help_reactors(self):
        """
        Display a list of possibly available reactor names.
        """
        rcts = sorted(self._getReactorTypes(), key=attrgetter('shortName'))
        for r in rcts:
            self.messageOutput.write('    %-4s\t%s\n' %
                                     (r.shortName, r.description))
        raise SystemExit(0)


    def opt_reactor(self, shortName):
        """
        Which reactor to use (see --help-reactors for a list of possibilities)
        """
        # Actually actually actually install the reactor right at this very
        # moment, before any other code (for example, a sub-command plugin)
        # runs and accidentally imports and installs the default reactor.
        #
        # This could probably be improved somehow.
        try:
            installReactor(shortName)
        except NoSuchReactor:
            msg = ("The specified reactor does not exist: '%s'.\n"
                   "See the list of available reactors with "
                   "--help-reactors" % (shortName,))
            raise usage.UsageError(msg)
        except Exception as e:
            msg = ("The specified reactor cannot be used, failed with error: "
                   "%s.\nSee the list of available reactors with "
                   "--help-reactors" % (e,))
            raise usage.UsageError(msg)
        else:
            self["reactor"] = shortName
    opt_r = opt_reactor



class ServerOptions(usage.Options, ReactorSelectionMixin):

    longdesc = ("twistd reads a twisted.application.service.Application out "
                "of a file and runs it.")

    optFlags = [['savestats', None,
                 "save the Stats object rather than the text output of "
                 "the profiler."],
                ['no_save', 'o', "do not save state on shutdown"],
                ['encrypted', 'e',
                 "The specified tap/aos file is encrypted."]]

    optParameters = [['logfile', 'l', None,
                      "log to a specified file, - for stdout"],
                     ['logger', None, None,
                      "A fully-qualified name to a log observer factory to "
                      "use for the initial log observer.  Takes precedence "
                      "over --logfile and --syslog (when available)."],
                     ['profile', 'p', None,
                      "Run in profile mode, dumping results to specified "
                      "file."],
                     ['profiler', None, "cprofile",
                      "Name of the profiler to use (%s)." %
                      ", ".join(AppProfiler.profilers)],
                     ['file', 'f', 'twistd.tap',
                      "read the given .tap file"],
                     ['python', 'y', None,
                      "read an application from within a Python file "
                      "(implies -o)"],
                     ['source', 's', None,
                      "Read an application from a .tas file (AOT format)."],
                     ['rundir', 'd', '.',
                      'Change to a supplied directory before running']]

    compData = usage.Completions(
        mutuallyExclusive=[("file", "python", "source")],
        optActions={"file": usage.CompleteFiles("*.tap"),
                    "python": usage.CompleteFiles("*.(tac|py)"),
                    "source": usage.CompleteFiles("*.tas"),
                    "rundir": usage.CompleteDirs()}
    )

    _getPlugins = staticmethod(plugin.getPlugins)

    def __init__(self, *a, **kw):
        self['debug'] = False
        usage.Options.__init__(self, *a, **kw)


    def opt_debug(self):
        """
        Run the application in the Python Debugger (implies nodaemon),
        sending SIGUSR2 will drop into debugger
        """
        defer.setDebugging(True)
        failure.startDebugMode()
        self['debug'] = True
    opt_b = opt_debug


    def opt_spew(self):
        """
        Print an insanely verbose log of everything that happens.
        Useful when debugging freezes or locks in complex code.
        """
        sys.settrace(util.spewer)
        try:
            import threading
        except ImportError:
            return
        threading.settrace(util.spewer)


    def parseOptions(self, options=None):
        if options is None:
            options = sys.argv[1:] or ["--help"]
        usage.Options.parseOptions(self, options)


    def postOptions(self):
        if self.subCommand or self['python']:
            self['no_save'] = True
        if self['logger'] is not None:
            try:
                self['logger'] = namedAny(self['logger'])
            except Exception as e:
                raise usage.UsageError("Logger '%s' could not be imported: %s"
                                       % (self['logger'], e))


    def subCommands(self):
        plugins = self._getPlugins(service.IServiceMaker)
        self.loadedPlugins = {}
        for plug in sorted(plugins, key=attrgetter('tapname')):
            self.loadedPlugins[plug.tapname] = plug
            yield (plug.tapname,
                   None,
                   # Avoid resolving the options attribute right away, in case
                   # it's a property with a non-trivial getter (eg, one which
                   # imports modules).
                   lambda plug=plug: plug.options(),
                   plug.description)
    subCommands = property(subCommands)



def run(runApp, ServerOptions):
    config = ServerOptions()
    try:
        config.parseOptions()
    except usage.error as ue:
        print(config)
        print("%s: %s" % (sys.argv[0], ue))
    else:
        runApp(config)



def convertStyle(filein, typein, passphrase, fileout, typeout, encrypt):
    application = service.loadApplication(filein, typein, passphrase)
    sob.IPersistable(application).setStyle(typeout)
    passphrase = getSavePassphrase(encrypt)
    if passphrase:
        fileout = None
    sob.IPersistable(application).save(filename=fileout, passphrase=passphrase)



def startApplication(application, save):
    from twisted.internet import reactor
    service.IService(application).startService()
    if save:
        p = sob.IPersistable(application)
        reactor.addSystemEventTrigger('after', 'shutdown', p.save, 'shutdown')
    reactor.addSystemEventTrigger('before', 'shutdown',
                                  service.IService(application).stopService)
