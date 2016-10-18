# -*- test-case-name: twisted.application.twist.test.test_options -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Command line options for C{twist}.
"""

from sys import stdout, stderr
from textwrap import dedent

from twisted.copyright import version
from twisted.python.usage import Options, UsageError
from twisted.logger import (
    LogLevel, InvalidLogLevelError,
    textFileLogObserver, jsonFileLogObserver,
)
from twisted.plugin import getPlugins

from ..reactors import installReactor, NoSuchReactor, getReactorTypes
from ..runner._exit import exit, ExitStatus
from ..service import IServiceMaker

openFile = open



class TwistOptions(Options):
    """
    Command line options for C{twist}.
    """

    defaultLogLevel = LogLevel.info


    def __init__(self):
        Options.__init__(self)

        self["reactorName"] = "default"
        self["logLevel"] = self.defaultLogLevel
        self["logFile"] = stdout


    def getSynopsis(self):
        return "{} plugin [plugin_options]".format(
            Options.getSynopsis(self)
        )


    def opt_version(self):
        """
        Print version and exit.
        """
        exit(ExitStatus.EX_OK, "{}".format(version))


    def opt_reactor(self, name):
        """
        The name of the reactor to use.
        (options: {options})
        """
        self["reactorName"] = name

    opt_reactor.__doc__ = dedent(opt_reactor.__doc__).format(
        options=", ".join(
            '"{}"'.format(rt.shortName) for rt in getReactorTypes()
        ),
    )


    def installReactor(self):
        """
        Install the reactor.
        """
        name = self["reactorName"]
        try:
            self["reactor"] = installReactor(name)
        except NoSuchReactor:
            raise UsageError("Unknown reactor: {}".format(name))


    def opt_log_level(self, levelName):
        """
        Set default log level.
        (options: {options}; default: "{default}")
        """
        try:
            self["logLevel"] = LogLevel.levelWithName(levelName)
        except InvalidLogLevelError:
            raise UsageError("Invalid log level: {}".format(levelName))

    opt_log_level.__doc__ = dedent(opt_log_level.__doc__).format(
        options=", ".join(
            '"{}"'.format(l.name) for l in LogLevel.iterconstants()
        ),
        default=defaultLogLevel.name,
    )


    def opt_log_file(self, fileName):
        """
        Log to file. ("-" for stdout, "+" for stderr; default: "-")
        """
        if fileName == "-":
            self["logFile"] = stdout
            return

        if fileName == "+":
            self["logFile"] = stderr
            return

        try:
            self["logFile"] = openFile(fileName, "a")
        except EnvironmentError as e:
            exit(
                ExitStatus.EX_IOERR,
                "Unable to open log file {!r}: {}".format(fileName, e)
            )


    def opt_log_format(self, format):
        """
        Log file format.
        (options: "text", "json"; default: "text" if the log file is a tty,
        otherwise "json")
        """
        format = format.lower()

        if format == "text":
            self["fileLogObserverFactory"] = textFileLogObserver
        elif format == "json":
            self["fileLogObserverFactory"] = jsonFileLogObserver
        else:
            raise UsageError("Invalid log format: {}".format(format))
        self["logFormat"] = format

    opt_log_format.__doc__ = dedent(opt_log_format.__doc__)


    def selectDefaultLogObserver(self):
        """
        Set C{fileLogObserverFactory} to the default appropriate for the
        chosen C{logFile}.
        """
        if "fileLogObserverFactory" not in self:
            logFile = self["logFile"]

            if hasattr(logFile, "isatty") and logFile.isatty():
                self["fileLogObserverFactory"] = textFileLogObserver
                self["logFormat"] = "text"
            else:
                self["fileLogObserverFactory"] = jsonFileLogObserver
                self["logFormat"] = "json"


    def parseOptions(self, options=None):
        self.installReactor()
        self.selectDefaultLogObserver()

        Options.parseOptions(self, options=options)


    @property
    def plugins(self):
        if "plugins" not in self:
            plugins = {}
            for plugin in getPlugins(IServiceMaker):
                plugins[plugin.tapname] = plugin
            self["plugins"] = plugins

        return self["plugins"]


    @property
    def subCommands(self):
        plugins = self.plugins
        for name in sorted(plugins):
            plugin = plugins[name]
            yield (
                plugin.tapname,
                None,
                # Avoid resolving the options attribute right away, in case
                # it's a property with a non-trivial getter (eg, one which
                # imports modules).
                lambda plugin=plugin: plugin.options(),
                plugin.description,
            )


    def postOptions(self):
        Options.postOptions(self)

        if self.subCommand is None:
            raise UsageError("No plugin specified.")
