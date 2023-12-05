# -*- test-case-name: twisted.application.twist.test.test_options -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Command line options for C{twist}.
"""

import typing
from sys import stderr, stdout
from textwrap import dedent
from typing import Callable, Iterable, Mapping, Optional, Sequence, Tuple, cast

from twisted.copyright import version
from twisted.internet.interfaces import IReactorCore
from twisted.logger import (
    InvalidLogLevelError,
    LogLevel,
    jsonFileLogObserver,
    textFileLogObserver,
)
from twisted.plugin import getPlugins
from twisted.python.usage import Options, UsageError
from ..reactors import NoSuchReactor, getReactorTypes, installReactor
from ..runner._exit import ExitStatus, exit
from ..service import IServiceMaker

openFile = open


def _update_doc(opt: Callable[["TwistOptions", str], None], **kwargs: str) -> None:
    """
    Update the docstring of a method that implements an option.
    The string is dedented and the given keyword arguments are substituted.
    """
    opt.__doc__ = dedent(opt.__doc__ or "").format(**kwargs)


class TwistOptions(Options):
    """
    Command line options for C{twist}.
    """

    defaultReactorName = "default"
    defaultLogLevel = LogLevel.info

    def __init__(self) -> None:
        Options.__init__(self)

        self["reactorName"] = self.defaultReactorName
        self["logLevel"] = self.defaultLogLevel
        self["logFile"] = stdout
        # An empty long description is explicitly set here as otherwise
        # when executing from distributed trial twisted.python.usage will
        # pull the description from `__main__` which is another entry point.
        self.longdesc = ""

    def getSynopsis(self) -> str:
        return f"{Options.getSynopsis(self)} plugin [plugin_options]"

    def opt_version(self) -> "typing.NoReturn":
        """
        Print version and exit.
        """
        exit(ExitStatus.EX_OK, f"{version}")

    def opt_reactor(self, name: str) -> None:
        """
        The name of the reactor to use.
        (options: {options})
        """
        # Actually actually actually install the reactor right at this very
        # moment, before any other code (for example, a sub-command plugin)
        # runs and accidentally imports and installs the default reactor.
        try:
            self["reactor"] = self.installReactor(name)
        except NoSuchReactor:
            raise UsageError(f"Unknown reactor: {name}")
        else:
            self["reactorName"] = name

    _update_doc(
        opt_reactor,
        options=", ".join(f'"{rt.shortName}"' for rt in getReactorTypes()),
    )

    def installReactor(self, name: str) -> IReactorCore:
        """
        Install the reactor.
        """
        if name == self.defaultReactorName:
            from twisted.internet import reactor

            return cast(IReactorCore, reactor)
        else:
            return installReactor(name)

    def opt_log_level(self, levelName: str) -> None:
        """
        Set default log level.
        (options: {options}; default: "{default}")
        """
        try:
            self["logLevel"] = LogLevel.levelWithName(levelName)
        except InvalidLogLevelError:
            raise UsageError(f"Invalid log level: {levelName}")

    _update_doc(
        opt_log_level,
        options=", ".join(
            f'"{constant.name}"' for constant in LogLevel.iterconstants()
        ),
        default=defaultLogLevel.name,
    )

    def opt_log_file(self, fileName: str) -> None:
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
        except OSError as e:
            exit(
                ExitStatus.EX_IOERR,
                f"Unable to open log file {fileName!r}: {e}",
            )

    def opt_log_format(self, format: str) -> None:
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
            raise UsageError(f"Invalid log format: {format}")
        self["logFormat"] = format

    _update_doc(opt_log_format)

    def selectDefaultLogObserver(self) -> None:
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

    def parseOptions(self, options: Optional[Sequence[str]] = None) -> None:
        self.selectDefaultLogObserver()

        Options.parseOptions(self, options=options)

        if "reactor" not in self:
            self["reactor"] = self.installReactor(self["reactorName"])

    @property
    def plugins(self) -> Mapping[str, IServiceMaker]:
        if "plugins" not in self:
            plugins = {}
            for plugin in getPlugins(IServiceMaker):
                plugins[plugin.tapname] = plugin
            self["plugins"] = plugins

        return cast(Mapping[str, IServiceMaker], self["plugins"])

    @property
    def subCommands(
        self,
    ) -> Iterable[Tuple[str, None, Callable[[IServiceMaker], Options], str]]:
        plugins = self.plugins
        for name in sorted(plugins):
            plugin = plugins[name]

            # Don't pass plugin.options along in order to avoid resolving the
            # options attribute right away, in case it's a property with a
            # non-trivial getter (eg, one which imports modules).
            def options(plugin: IServiceMaker = plugin) -> Options:
                return cast(Options, plugin.options())

            yield (plugin.tapname, None, options, plugin.description)

    def postOptions(self) -> None:
        Options.postOptions(self)

        if self.subCommand is None:
            raise UsageError("No plugin specified.")
