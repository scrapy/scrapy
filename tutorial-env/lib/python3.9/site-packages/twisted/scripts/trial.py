# -*- test-case-name: twisted.trial.test.test_script -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


import gc
import inspect
import os
import pdb
import random
import sys
import time
import trace
import warnings
from typing import NoReturn, Optional, Type

from twisted import plugin
from twisted.application import app
from twisted.internet import defer
from twisted.python import failure, reflect, usage
from twisted.python.filepath import FilePath
from twisted.python.reflect import namedModule
from twisted.trial import itrial, runner
from twisted.trial._dist.disttrial import DistTrialRunner
from twisted.trial.unittest import TestSuite

# Yea, this is stupid.  Leave it for command-line compatibility for a
# while, though.
TBFORMAT_MAP = {
    "plain": "default",
    "default": "default",
    "emacs": "brief",
    "brief": "brief",
    "cgitb": "verbose",
    "verbose": "verbose",
}


def _parseLocalVariables(line):
    """
    Accepts a single line in Emacs local variable declaration format and
    returns a dict of all the variables {name: value}.
    Raises ValueError if 'line' is in the wrong format.

    See http://www.gnu.org/software/emacs/manual/html_node/File-Variables.html
    """
    paren = "-*-"
    start = line.find(paren) + len(paren)
    end = line.rfind(paren)
    if start == -1 or end == -1:
        raise ValueError(f"{line!r} not a valid local variable declaration")
    items = line[start:end].split(";")
    localVars = {}
    for item in items:
        if len(item.strip()) == 0:
            continue
        split = item.split(":")
        if len(split) != 2:
            raise ValueError(f"{line!r} contains invalid declaration {item!r}")
        localVars[split[0].strip()] = split[1].strip()
    return localVars


def loadLocalVariables(filename):
    """
    Accepts a filename and attempts to load the Emacs variable declarations
    from that file, simulating what Emacs does.

    See http://www.gnu.org/software/emacs/manual/html_node/File-Variables.html
    """
    with open(filename) as f:
        lines = [f.readline(), f.readline()]
    for line in lines:
        try:
            return _parseLocalVariables(line)
        except ValueError:
            pass
    return {}


def getTestModules(filename):
    testCaseVar = loadLocalVariables(filename).get("test-case-name", None)
    if testCaseVar is None:
        return []
    return testCaseVar.split(",")


def isTestFile(filename):
    """
    Returns true if 'filename' looks like a file containing unit tests.
    False otherwise.  Doesn't care whether filename exists.
    """
    basename = os.path.basename(filename)
    return basename.startswith("test_") and os.path.splitext(basename)[1] == (".py")


def _reporterAction():
    return usage.CompleteList([p.longOpt for p in plugin.getPlugins(itrial.IReporter)])


def _maybeFindSourceLine(testThing):
    """
    Try to find the source line of the given test thing.

    @param testThing: the test item to attempt to inspect
    @type testThing: an L{TestCase}, test method, or module, though only the
        former two have a chance to succeed
    @rtype: int
    @return: the starting source line, or -1 if one couldn't be found
    """

    # an instance of L{TestCase} -- locate the test it will run
    method = getattr(testThing, "_testMethodName", None)
    if method is not None:
        testThing = getattr(testThing, method)

    # If it's a function, we can get the line number even if the source file no
    # longer exists
    code = getattr(testThing, "__code__", None)
    if code is not None:
        return code.co_firstlineno

    try:
        return inspect.getsourcelines(testThing)[1]
    except (OSError, TypeError):
        # either testThing is a module, which raised a TypeError, or the file
        # couldn't be read
        return -1


# orders which can be passed to trial --order
_runOrders = {
    "alphabetical": (
        "alphabetical order for test methods, arbitrary order for test cases",
        runner.name,
    ),
    "toptobottom": (
        "attempt to run test cases and methods in the order they were defined",
        _maybeFindSourceLine,
    ),
}


def _checkKnownRunOrder(order):
    """
    Check that the given order is a known test running order.

    Does nothing else, since looking up the appropriate callable to sort the
    tests should be done when it actually will be used, as the default argument
    will not be coerced by this function.

    @param order: one of the known orders in C{_runOrders}
    @return: the order unmodified
    """
    if order not in _runOrders:
        raise usage.UsageError(
            "--order must be one of: %s. See --help-orders for details"
            % (", ".join(repr(order) for order in _runOrders),)
        )
    return order


class _BasicOptions:
    """
    Basic options shared between trial and its local workers.
    """

    longdesc = (
        "trial loads and executes a suite of unit tests, obtained "
        "from modules, packages and files listed on the command line."
    )

    optFlags = [
        ["help", "h"],
        ["no-recurse", "N", "Don't recurse into packages"],
        ["help-orders", None, "Help on available test running orders"],
        ["help-reporters", None, "Help on available output plugins (reporters)"],
        [
            "rterrors",
            "e",
            "realtime errors, print out tracebacks as " "soon as they occur",
        ],
        ["unclean-warnings", None, "Turn dirty reactor errors into warnings"],
        [
            "force-gc",
            None,
            "Have Trial run gc.collect() before and " "after each test case.",
        ],
        [
            "exitfirst",
            "x",
            "Exit after the first non-successful result (cannot be "
            "specified along with --jobs).",
        ],
    ]

    optParameters = [
        [
            "order",
            "o",
            None,
            "Specify what order to run test cases and methods. "
            "See --help-orders for more info.",
            _checkKnownRunOrder,
        ],
        ["random", "z", None, "Run tests in random order using the specified seed"],
        [
            "temp-directory",
            None,
            "_trial_temp",
            "Path to use as working directory for tests.",
        ],
        [
            "reporter",
            None,
            "verbose",
            "The reporter to use for this test run.  See --help-reporters for "
            "more info.",
        ],
    ]

    compData = usage.Completions(
        optActions={
            "order": usage.CompleteList(_runOrders),
            "reporter": _reporterAction,
            "logfile": usage.CompleteFiles(descr="log file name"),
            "random": usage.Completer(descr="random seed"),
        },
        extraActions=[
            usage.CompleteFiles(
                "*.py",
                descr="file | module | package | TestCase | testMethod",
                repeat=True,
            )
        ],
    )

    tracer: Optional[trace.Trace] = None

    def __init__(self):
        self["tests"] = []
        usage.Options.__init__(self)

    def getSynopsis(self):
        executableName = reflect.filenameToModuleName(sys.argv[0])

        if executableName.endswith(".__main__"):
            executableName = "{} -m {}".format(
                os.path.basename(sys.executable),
                executableName.replace(".__main__", ""),
            )

        return """{} [options] [[file|package|module|TestCase|testmethod]...]
        """.format(
            executableName,
        )

    def coverdir(self):
        """
        Return a L{FilePath} representing the directory into which coverage
        results should be written.
        """
        coverdir = "coverage"
        result = FilePath(self["temp-directory"]).child(coverdir)
        print(f"Setting coverage directory to {result.path}.")
        return result

    # TODO: Some of the opt_* methods on this class have docstrings and some do
    #       not. This is mostly because usage.Options's currently will replace
    #       any intended output in optFlags and optParameters with the
    #       docstring. See #6427. When that is fixed, all methods should be
    #       given docstrings (and it should be verified that those with
    #       docstrings already have content suitable for printing as usage
    #       information).

    def opt_coverage(self):
        """
        Generate coverage information in the coverage file in the
        directory specified by the temp-directory option.
        """
        self.tracer = trace.Trace(count=1, trace=0)
        sys.settrace(self.tracer.globaltrace)
        self["coverage"] = True

    def opt_testmodule(self, filename):
        """
        Filename to grep for test cases (-*- test-case-name).
        """
        # If the filename passed to this parameter looks like a test module
        # we just add that to the test suite.
        #
        # If not, we inspect it for an Emacs buffer local variable called
        # 'test-case-name'.  If that variable is declared, we try to add its
        # value to the test suite as a module.
        #
        # This parameter allows automated processes (like Buildbot) to pass
        # a list of files to Trial with the general expectation of "these files,
        # whatever they are, will get tested"
        if not os.path.isfile(filename):
            sys.stderr.write(f"File {filename!r} doesn't exist\n")
            return
        filename = os.path.abspath(filename)
        if isTestFile(filename):
            self["tests"].append(filename)
        else:
            self["tests"].extend(getTestModules(filename))

    def opt_spew(self):
        """
        Print an insanely verbose log of everything that happens.  Useful
        when debugging freezes or locks in complex code.
        """
        from twisted.python.util import spewer

        sys.settrace(spewer)

    def opt_help_orders(self):
        synopsis = (
            "Trial can attempt to run test cases and their methods in "
            "a few different orders. You can select any of the "
            "following options using --order=<foo>.\n"
        )

        print(synopsis)
        for name, (description, _) in sorted(_runOrders.items()):
            print("   ", name, "\t", description)
        sys.exit(0)

    def opt_help_reporters(self):
        synopsis = (
            "Trial's output can be customized using plugins called "
            "Reporters. You can\nselect any of the following "
            "reporters using --reporter=<foo>\n"
        )
        print(synopsis)
        for p in plugin.getPlugins(itrial.IReporter):
            print("   ", p.longOpt, "\t", p.description)
        sys.exit(0)

    def opt_disablegc(self):
        """
        Disable the garbage collector
        """
        self["disablegc"] = True
        gc.disable()

    def opt_tbformat(self, opt):
        """
        Specify the format to display tracebacks with. Valid formats are
        'plain', 'emacs', and 'cgitb' which uses the nicely verbose stdlib
        cgitb.text function
        """
        try:
            self["tbformat"] = TBFORMAT_MAP[opt]
        except KeyError:
            raise usage.UsageError("tbformat must be 'plain', 'emacs', or 'cgitb'.")

    def opt_recursionlimit(self, arg):
        """
        see sys.setrecursionlimit()
        """
        try:
            sys.setrecursionlimit(int(arg))
        except (TypeError, ValueError):
            raise usage.UsageError("argument to recursionlimit must be an integer")
        else:
            self["recursionlimit"] = int(arg)

    def opt_random(self, option):
        try:
            self["random"] = int(option)
        except ValueError:
            raise usage.UsageError("Argument to --random must be a positive integer")
        else:
            if self["random"] < 0:
                raise usage.UsageError(
                    "Argument to --random must be a positive integer"
                )
            elif self["random"] == 0:
                self["random"] = int(time.time() * 100)

    def opt_without_module(self, option):
        """
        Fake the lack of the specified modules, separated with commas.
        """
        self["without-module"] = option
        for module in option.split(","):
            if module in sys.modules:
                warnings.warn(
                    "Module '%s' already imported, " "disabling anyway." % (module,),
                    category=RuntimeWarning,
                )
            sys.modules[module] = None

    def parseArgs(self, *args):
        self["tests"].extend(args)

    def _loadReporterByName(self, name):
        for p in plugin.getPlugins(itrial.IReporter):
            qual = f"{p.module}.{p.klass}"
            if p.longOpt == name:
                return reflect.namedAny(qual)
        raise usage.UsageError(
            "Only pass names of Reporter plugins to "
            "--reporter. See --help-reporters for "
            "more info."
        )

    def postOptions(self):
        # Only load reporters now, as opposed to any earlier, to avoid letting
        # application-defined plugins muck up reactor selecting by importing
        # t.i.reactor and causing the default to be installed.
        self["reporter"] = self._loadReporterByName(self["reporter"])
        if "tbformat" not in self:
            self["tbformat"] = "default"
        if self["order"] is not None and self["random"] is not None:
            raise usage.UsageError("You can't specify --random when using --order")


class Options(_BasicOptions, usage.Options, app.ReactorSelectionMixin):
    """
    Options to the trial command line tool.

    @ivar _workerFlags: List of flags which are accepted by trial distributed
        workers. This is used by C{_getWorkerArguments} to build the command
        line arguments.
    @type _workerFlags: C{list}

    @ivar _workerParameters: List of parameter which are accepted by trial
        distributed workers. This is used by C{_getWorkerArguments} to build
        the command line arguments.
    @type _workerParameters: C{list}
    """

    optFlags = [
        [
            "debug",
            "b",
            "Run tests in a debugger. If that debugger is "
            "pdb, will load '.pdbrc' from current directory if it exists.",
        ],
        [
            "debug-stacktraces",
            "B",
            "Report Deferred creation and " "callback stack traces",
        ],
        [
            "nopm",
            None,
            "don't automatically jump into debugger for " "postmorteming of exceptions",
        ],
        ["dry-run", "n", "do everything but run the tests"],
        ["profile", None, "Run tests under the Python profiler"],
        ["until-failure", "u", "Repeat test until it fails"],
    ]

    optParameters = [
        [
            "debugger",
            None,
            "pdb",
            "the fully qualified name of a debugger to " "use if --debug is passed",
        ],
        ["logfile", "l", "test.log", "log file name"],
        ["jobs", "j", None, "Number of local workers to run"],
    ]

    compData = usage.Completions(
        optActions={
            "tbformat": usage.CompleteList(["plain", "emacs", "cgitb"]),
            "reporter": _reporterAction,
        },
    )

    _workerFlags = ["disablegc", "force-gc", "coverage"]
    _workerParameters = ["recursionlimit", "reactor", "without-module"]

    def opt_jobs(self, number):
        """
        Number of local workers to run, a strictly positive integer.
        """
        try:
            number = int(number)
        except ValueError:
            raise usage.UsageError(
                "Expecting integer argument to jobs, got '%s'" % number
            )
        if number <= 0:
            raise usage.UsageError(
                "Argument to jobs must be a strictly positive integer"
            )
        self["jobs"] = number

    def _getWorkerArguments(self):
        """
        Return a list of options to pass to distributed workers.
        """
        args = []
        for option in self._workerFlags:
            if self.get(option) is not None:
                if self[option]:
                    args.append(f"--{option}")
        for option in self._workerParameters:
            if self.get(option) is not None:
                args.extend([f"--{option}", str(self[option])])
        return args

    def postOptions(self):
        _BasicOptions.postOptions(self)
        if self["jobs"]:
            conflicts = ["debug", "profile", "debug-stacktraces"]
            for option in conflicts:
                if self[option]:
                    raise usage.UsageError(
                        "You can't specify --%s when using --jobs" % option
                    )
        if self["nopm"]:
            if not self["debug"]:
                raise usage.UsageError("You must specify --debug when using " "--nopm ")
            failure.DO_POST_MORTEM = False


def _initialDebugSetup(config: Options) -> None:
    # do this part of debug setup first for easy debugging of import failures
    if config["debug"]:
        failure.startDebugMode()
    if config["debug"] or config["debug-stacktraces"]:
        defer.setDebugging(True)


def _getSuite(config: Options) -> TestSuite:
    loader = _getLoader(config)
    recurse = not config["no-recurse"]
    return loader.loadByNames(config["tests"], recurse=recurse)


def _getLoader(config: Options) -> runner.TestLoader:
    loader = runner.TestLoader()
    if config["random"]:
        randomer = random.Random()
        randomer.seed(config["random"])
        loader.sorter = lambda x: randomer.random()
        print("Running tests shuffled with seed %d\n" % config["random"])
    elif config["order"]:
        _, sorter = _runOrders[config["order"]]
        loader.sorter = sorter
    if not config["until-failure"]:
        loader.suiteFactory = runner.DestructiveTestSuite
    return loader


def _wrappedPdb():
    """
    Wrap an instance of C{pdb.Pdb} with readline support and load any .rcs.

    """

    dbg = pdb.Pdb()
    try:
        namedModule("readline")
    except ImportError:
        print("readline module not available")
    for path in (".pdbrc", "pdbrc"):
        if os.path.exists(path):
            try:
                rcFile = open(path)
            except OSError:
                pass
            else:
                with rcFile:
                    dbg.rcLines.extend(rcFile.readlines())
    return dbg


class _DebuggerNotFound(Exception):
    """
    A debugger import failed.

    Used to allow translating these errors into usage error messages.

    """


def _makeRunner(config: Options) -> runner._Runner:
    """
    Return a trial runner class set up with the parameters extracted from
    C{config}.

    @return: A trial runner instance.
    """
    cls: Type[runner._Runner] = runner.TrialRunner
    args = {
        "reporterFactory": config["reporter"],
        "tracebackFormat": config["tbformat"],
        "realTimeErrors": config["rterrors"],
        "uncleanWarnings": config["unclean-warnings"],
        "logfile": config["logfile"],
        "workingDirectory": config["temp-directory"],
        "exitFirst": config["exitfirst"],
    }
    if config["dry-run"]:
        args["mode"] = runner.TrialRunner.DRY_RUN
    elif config["jobs"]:
        cls = DistTrialRunner
        args["maxWorkers"] = config["jobs"]
        args["workerArguments"] = config._getWorkerArguments()
    else:
        if config["debug"]:
            args["mode"] = runner.TrialRunner.DEBUG
            debugger = config["debugger"]

            if debugger != "pdb":
                try:
                    args["debugger"] = reflect.namedAny(debugger)
                except reflect.ModuleNotFound:
                    raise _DebuggerNotFound(
                        f"{debugger!r} debugger could not be found."
                    )
            else:
                args["debugger"] = _wrappedPdb()

        args["profile"] = config["profile"]
        args["forceGarbageCollection"] = config["force-gc"]

    return cls(**args)


def run() -> NoReturn:
    if len(sys.argv) == 1:
        sys.argv.append("--help")
    config = Options()
    try:
        config.parseOptions()
    except usage.error as ue:
        raise SystemExit(f"{sys.argv[0]}: {ue}")
    _initialDebugSetup(config)

    try:
        trialRunner = _makeRunner(config)
    except _DebuggerNotFound as e:
        raise SystemExit(f"{sys.argv[0]}: {str(e)}")

    suite = _getSuite(config)
    if config["until-failure"]:
        testResult = trialRunner.runUntilFailure(suite)
    else:
        testResult = trialRunner.run(suite)
    if config.tracer:
        sys.settrace(None)
        results = config.tracer.results()
        results.write_results(
            show_missing=True, summary=False, coverdir=config.coverdir().path
        )
    sys.exit(not testResult.wasSuccessful())
