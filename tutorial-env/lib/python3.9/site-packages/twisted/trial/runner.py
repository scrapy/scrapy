# -*- test-case-name: twisted.trial.test.test_runner -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A miscellany of code used to run Trial tests.

Maintainer: Jonathan Lange
"""


__all__ = [
    "TestSuite",
    "DestructiveTestSuite",
    "ErrorHolder",
    "LoggedSuite",
    "TestHolder",
    "TestLoader",
    "TrialRunner",
    "TrialSuite",
    "filenameToModule",
    "isPackage",
    "isPackageDirectory",
    "isTestCase",
    "name",
    "samefile",
    "NOT_IN_TEST",
]

import doctest
import importlib
import inspect
import os
import sys
import types
import unittest as pyunit
import warnings
from contextlib import contextmanager
from importlib.machinery import SourceFileLoader
from typing import Callable, Generator, List, Optional, TextIO, Type, Union

from zope.interface import implementer

from attrs import define
from typing_extensions import ParamSpec, Protocol, TypeAlias, TypeGuard

from twisted.internet import defer
from twisted.python import failure, filepath, log, modules, reflect
from twisted.trial import unittest, util
from twisted.trial._asyncrunner import _ForceGarbageCollectionDecorator, _iterateTests
from twisted.trial._synctest import _logObserver
from twisted.trial.itrial import ITestCase
from twisted.trial.reporter import UncleanWarningsReporterWrapper, _ExitWrapper

# These are imported so that they remain in the public API for t.trial.runner
from twisted.trial.unittest import TestSuite
from . import itrial

_P = ParamSpec("_P")


class _Debugger(Protocol):
    def runcall(
        self, f: Callable[_P, object], *args: _P.args, **kwargs: _P.kwargs
    ) -> object:
        ...


def isPackage(module):
    """Given an object return True if the object looks like a package"""
    if not isinstance(module, types.ModuleType):
        return False
    basename = os.path.splitext(os.path.basename(module.__file__))[0]
    return basename == "__init__"


def isPackageDirectory(dirname):
    """
    Is the directory at path 'dirname' a Python package directory?
    Returns the name of the __init__ file (it may have a weird extension)
    if dirname is a package directory.  Otherwise, returns False
    """

    def _getSuffixes():
        return importlib.machinery.all_suffixes()

    for ext in _getSuffixes():
        initFile = "__init__" + ext
        if os.path.exists(os.path.join(dirname, initFile)):
            return initFile
    return False


def samefile(filename1, filename2):
    """
    A hacky implementation of C{os.path.samefile}. Used by L{filenameToModule}
    when the platform doesn't provide C{os.path.samefile}. Do not use this.
    """
    return os.path.abspath(filename1) == os.path.abspath(filename2)


def filenameToModule(fn):
    """
    Given a filename, do whatever possible to return a module object matching
    that file.

    If the file in question is a module in Python path, properly import and
    return that module. Otherwise, load the source manually.

    @param fn: A filename.
    @return: A module object.
    @raise ValueError: If C{fn} does not exist.
    """
    oldFn = fn

    if (3, 8) <= sys.version_info < (3, 10) and not os.path.isabs(fn):
        # module.__spec__.__file__ is supposed to be absolute in py3.8+
        # importlib.util.spec_from_file_location does this automatically from
        # 3.10+
        # This was backported to 3.8 and 3.9, but then reverted in 3.8.11 and
        # 3.9.6
        # See https://twistedmatrix.com/trac/ticket/10230
        # and https://bugs.python.org/issue44070
        fn = os.path.join(os.getcwd(), fn)

    if not os.path.exists(fn):
        raise ValueError(f"{oldFn!r} doesn't exist")

    moduleName = reflect.filenameToModuleName(fn)
    try:
        ret = reflect.namedAny(moduleName)
    except (ValueError, AttributeError):
        # Couldn't find module.  The file 'fn' is not in PYTHONPATH
        return _importFromFile(fn, moduleName=moduleName)

    # >=3.7 has __file__ attribute as None, previously __file__ was not present
    if getattr(ret, "__file__", None) is None:
        # This isn't a Python module in a package, so import it from a file
        return _importFromFile(fn, moduleName=moduleName)

    # ensure that the loaded module matches the file
    retFile = os.path.splitext(ret.__file__)[0] + ".py"
    # not all platforms (e.g. win32) have os.path.samefile
    same = getattr(os.path, "samefile", samefile)
    if os.path.isfile(fn) and not same(fn, retFile):
        del sys.modules[ret.__name__]
        ret = _importFromFile(fn, moduleName=moduleName)
    return ret


def _importFromFile(fn, *, moduleName):
    fn = _resolveDirectory(fn)
    if not moduleName:
        moduleName = os.path.splitext(os.path.split(fn)[-1])[0]
    if moduleName in sys.modules:
        return sys.modules[moduleName]

    spec = importlib.util.spec_from_file_location(moduleName, fn)
    if not spec:
        raise SyntaxError(fn)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[moduleName] = module
    return module


def _resolveDirectory(fn):
    if os.path.isdir(fn):
        initFile = isPackageDirectory(fn)
        if initFile:
            fn = os.path.join(fn, initFile)
        else:
            raise ValueError(f"{fn!r} is not a package directory")
    return fn


def _getMethodNameInClass(method):
    """
    Find the attribute name on the method's class which refers to the method.

    For some methods, notably decorators which have not had __name__ set correctly:

    getattr(method.im_class, method.__name__) != method
    """
    if getattr(method.im_class, method.__name__, object()) != method:
        for alias in dir(method.im_class):
            if getattr(method.im_class, alias, object()) == method:
                return alias
    return method.__name__


class DestructiveTestSuite(TestSuite):
    """
    A test suite which remove the tests once run, to minimize memory usage.
    """

    def run(self, result):
        """
        Almost the same as L{TestSuite.run}, but with C{self._tests} being
        empty at the end.
        """
        while self._tests:
            if result.shouldStop:
                break
            test = self._tests.pop(0)
            test(result)
        return result


# When an error occurs outside of any test, the user will see this string
# in place of a test's name.
NOT_IN_TEST = "<not in test>"


class LoggedSuite(TestSuite):
    """
    Any errors logged in this suite will be reported to the L{TestResult}
    object.
    """

    def run(self, result):
        """
        Run the suite, storing all errors in C{result}. If an error is logged
        while no tests are running, then it will be added as an error to
        C{result}.

        @param result: A L{TestResult} object.
        """
        observer = _logObserver
        observer._add()
        super().run(result)
        observer._remove()
        for error in observer.getErrors():
            result.addError(TestHolder(NOT_IN_TEST), error)
        observer.flushErrors()


class TrialSuite(TestSuite):
    """
    Suite to wrap around every single test in a C{trial} run. Used internally
    by Trial to set up things necessary for Trial tests to work, regardless of
    what context they are run in.
    """

    def __init__(self, tests=(), forceGarbageCollection=False):
        if forceGarbageCollection:
            newTests = []
            for test in tests:
                test = unittest.decorate(test, _ForceGarbageCollectionDecorator)
                newTests.append(test)
            tests = newTests
        suite = LoggedSuite(tests)
        super().__init__([suite])

    def _bail(self):
        from twisted.internet import reactor

        d = defer.Deferred()
        reactor.addSystemEventTrigger("after", "shutdown", lambda: d.callback(None))
        reactor.fireSystemEvent("shutdown")  # radix's suggestion
        # As long as TestCase does crap stuff with the reactor we need to
        # manually shutdown the reactor here, and that requires util.wait
        # :(
        # so that the shutdown event completes
        unittest.TestCase("mktemp")._wait(d)

    def run(self, result):
        try:
            TestSuite.run(self, result)
        finally:
            self._bail()


_Loadable: TypeAlias = Union[
    modules.PythonAttribute,
    modules.PythonModule,
    pyunit.TestCase,
    Type[pyunit.TestCase],
]


def name(thing: _Loadable) -> str:
    """
    @param thing: an object from modules (instance of PythonModule,
        PythonAttribute), a TestCase subclass, or an instance of a TestCase.
    """
    if isinstance(thing, pyunit.TestCase):
        return thing.id()

    if isinstance(thing, (modules.PythonAttribute, modules.PythonModule)):
        return thing.name

    if isTestCase(thing):
        # TestCase subclass
        return reflect.qual(thing)

    # Based on the type of thing, this is unreachable.  Maybe someone calls
    # this from un-type-checked code though.  Also, even with the type
    # information, mypy fails to determine this is unreachable and complains
    # about a missing return without _something_ here.
    raise TypeError(f"Cannot name {thing!r}")


def isTestCase(obj: type) -> TypeGuard[Type[pyunit.TestCase]]:
    """
    @return: C{True} if C{obj} is a class that contains test cases, C{False}
        otherwise. Used to find all the tests in a module.
    """
    try:
        return issubclass(obj, pyunit.TestCase)
    except TypeError:
        return False


@implementer(ITestCase)
class TestHolder:
    """
    Placeholder for a L{TestCase} inside a reporter. As far as a L{TestResult}
    is concerned, this looks exactly like a unit test.
    """

    failureException = None

    def __init__(self, description):
        """
        @param description: A string to be displayed L{TestResult}.
        """
        self.description = description

    def __call__(self, result):
        return self.run(result)

    def id(self):
        return self.description

    def countTestCases(self):
        return 0

    def run(self, result):
        """
        This test is just a placeholder. Run the test successfully.

        @param result: The C{TestResult} to store the results in.
        @type result: L{twisted.trial.itrial.IReporter}.
        """
        result.startTest(self)
        result.addSuccess(self)
        result.stopTest(self)

    def shortDescription(self):
        return self.description


class ErrorHolder(TestHolder):
    """
    Used to insert arbitrary errors into a test suite run. Provides enough
    methods to look like a C{TestCase}, however, when it is run, it simply adds
    an error to the C{TestResult}. The most common use-case is for when a
    module fails to import.
    """

    def __init__(self, description, error):
        """
        @param description: A string used by C{TestResult}s to identify this
        error. Generally, this is the name of a module that failed to import.

        @param error: The error to be added to the result. Can be an `exc_info`
        tuple or a L{twisted.python.failure.Failure}.
        """
        super().__init__(description)
        self.error = util.excInfoOrFailureToExcInfo(error)

    def __repr__(self) -> str:
        return "<ErrorHolder description={!r} error={!r}>".format(
            self.description,
            self.error[1],
        )

    def run(self, result):
        """
        Run the test, reporting the error.

        @param result: The C{TestResult} to store the results in.
        @type result: L{twisted.trial.itrial.IReporter}.
        """
        result.startTest(self)
        result.addError(self, self.error)
        result.stopTest(self)


@define
class TestLoader:
    """
    I find tests inside function, modules, files -- whatever -- then return
    them wrapped inside a Test (either a L{TestSuite} or a L{TestCase}).

    @ivar methodPrefix: A string prefix. C{TestLoader} will assume that all the
    methods in a class that begin with C{methodPrefix} are test cases.

    @ivar modulePrefix: A string prefix. Every module in a package that begins
    with C{modulePrefix} is considered a module full of tests.

    @ivar forceGarbageCollection: A flag applied to each C{TestCase} loaded.
    See L{unittest.TestCase} for more information.

    @ivar sorter: A key function used to sort C{TestCase}s, test classes,
    modules and packages.

    @ivar suiteFactory: A callable which is passed a list of tests (which
    themselves may be suites of tests). Must return a test suite.
    """

    methodPrefix = "test"
    modulePrefix = "test_"

    suiteFactory: Type[TestSuite] = TestSuite
    sorter: Callable[[_Loadable], object] = name

    def sort(self, xs):
        """
        Sort the given things using L{sorter}.

        @param xs: A list of test cases, class or modules.
        """
        return sorted(xs, key=self.sorter)

    def findTestClasses(self, module):
        """Given a module, return all Trial test classes"""
        classes = []
        for name, val in inspect.getmembers(module):
            if isTestCase(val):
                classes.append(val)
        return self.sort(classes)

    def findByName(self, _name, recurse=False):
        """
        Find and load tests, given C{name}.

        @param _name: The qualified name of the thing to load.
        @param recurse: A boolean. If True, inspect modules within packages
            within the given package (and so on), otherwise, only inspect
            modules in the package itself.

        @return: If C{name} is a filename, return the module. If C{name} is a
        fully-qualified Python name, return the object it refers to.
        """
        if os.sep in _name:
            # It's a file, try and get the module name for this file.
            name = reflect.filenameToModuleName(_name)

            try:
                # Try and import it, if it's on the path.
                # CAVEAT: If you have two twisteds, and you try and import the
                # one NOT on your path, it'll load the one on your path. But
                # that's silly, nobody should do that, and existing Trial does
                # that anyway.
                __import__(name)
            except ImportError:
                # If we can't import it, look for one NOT on the path.
                return self.loadFile(_name, recurse=recurse)

        else:
            name = _name

        obj = parent = remaining = None

        for searchName, remainingName in _qualNameWalker(name):
            # Walk down the qualified name, trying to import a module. For
            # example, `twisted.test.test_paths.FilePathTests` would try
            # the full qualified name, then just up to test_paths, and then
            # just up to test, and so forth.
            # This gets us the highest level thing which is a module.
            try:
                obj = reflect.namedModule(searchName)
                # If we reach here, we have successfully found a module.
                # obj will be the module, and remaining will be the remaining
                # part of the qualified name.
                remaining = remainingName
                break

            except ImportError:
                # Check to see where the ImportError happened. If it happened
                # in this file, ignore it.
                tb = sys.exc_info()[2]

                # Walk down to the deepest frame, where it actually happened.
                while tb.tb_next is not None:
                    tb = tb.tb_next

                # Get the filename that the ImportError originated in.
                filenameWhereHappened = tb.tb_frame.f_code.co_filename

                # If it originated in the reflect file, then it's because it
                # doesn't exist. If it originates elsewhere, it's because an
                # ImportError happened in a module that does exist.
                if filenameWhereHappened != reflect.__file__:
                    raise

                if remaining == "":
                    raise reflect.ModuleNotFound(f"The module {name} does not exist.")

        if obj is None:
            # If it's none here, we didn't get to import anything.
            # Try something drastic.
            obj = reflect.namedAny(name)
            remaining = name.split(".")[len(".".split(obj.__name__)) + 1 :]

        try:
            for part in remaining:
                # Walk down the remaining modules. Hold on to the parent for
                # methods, as on Python 3, you can no longer get the parent
                # class from just holding onto the method.
                parent, obj = obj, getattr(obj, part)
        except AttributeError:
            raise AttributeError(f"{name} does not exist.")

        return self.loadAnything(
            obj, parent=parent, qualName=remaining, recurse=recurse
        )

    def loadModule(self, module):
        """
        Return a test suite with all the tests from a module.

        Included are TestCase subclasses and doctests listed in the module's
        __doctests__ module. If that's not good for you, put a function named
        either C{testSuite} or C{test_suite} in your module that returns a
        TestSuite, and I'll use the results of that instead.

        If C{testSuite} and C{test_suite} are both present, then I'll use
        C{testSuite}.
        """
        ## XXX - should I add an optional parameter to disable the check for
        ## a custom suite.
        ## OR, should I add another method
        if not isinstance(module, types.ModuleType):
            raise TypeError(f"{module!r} is not a module")
        if hasattr(module, "testSuite"):
            return module.testSuite()
        elif hasattr(module, "test_suite"):
            return module.test_suite()
        suite = self.suiteFactory()
        for testClass in self.findTestClasses(module):
            suite.addTest(self.loadClass(testClass))
        if not hasattr(module, "__doctests__"):
            return suite
        docSuite = self.suiteFactory()
        for docTest in module.__doctests__:
            docSuite.addTest(self.loadDoctests(docTest))
        return self.suiteFactory([suite, docSuite])

    loadTestsFromModule = loadModule

    def loadClass(self, klass):
        """
        Given a class which contains test cases, return a list of L{TestCase}s.

        @param klass: The class to load tests from.
        """
        if not isinstance(klass, type):
            raise TypeError(f"{klass!r} is not a class")
        if not isTestCase(klass):
            raise ValueError(f"{klass!r} is not a test case")
        names = self.getTestCaseNames(klass)
        tests = self.sort(
            [self._makeCase(klass, self.methodPrefix + name) for name in names]
        )
        return self.suiteFactory(tests)

    loadTestsFromTestCase = loadClass

    def getTestCaseNames(self, klass):
        """
        Given a class that contains C{TestCase}s, return a list of names of
        methods that probably contain tests.
        """
        return reflect.prefixedMethodNames(klass, self.methodPrefix)

    def _makeCase(self, klass, methodName):
        return klass(methodName)

    def loadPackage(self, package, recurse=False):
        """
        Load tests from a module object representing a package, and return a
        TestSuite containing those tests.

        Tests are only loaded from modules whose name begins with 'test_'
        (or whatever C{modulePrefix} is set to).

        @param package: a types.ModuleType object (or reasonable facsimile
        obtained by importing) which may contain tests.

        @param recurse: A boolean.  If True, inspect modules within packages
        within the given package (and so on), otherwise, only inspect modules
        in the package itself.

        @raise TypeError: If C{package} is not a package.

        @return: a TestSuite created with my suiteFactory, containing all the
        tests.
        """
        if not isPackage(package):
            raise TypeError(f"{package!r} is not a package")
        pkgobj = modules.getModule(package.__name__)
        if recurse:
            discovery = pkgobj.walkModules()
        else:
            discovery = pkgobj.iterModules()
        discovered = []
        for disco in discovery:
            if disco.name.split(".")[-1].startswith(self.modulePrefix):
                discovered.append(disco)
        suite = self.suiteFactory()
        for modinfo in self.sort(discovered):
            try:
                module = modinfo.load()
            except BaseException:
                thingToAdd = ErrorHolder(modinfo.name, failure.Failure())
            else:
                thingToAdd = self.loadModule(module)
            suite.addTest(thingToAdd)
        return suite

    def loadDoctests(self, module):
        """
        Return a suite of tests for all the doctests defined in C{module}.

        @param module: A module object or a module name.
        """
        if isinstance(module, str):
            try:
                module = reflect.namedAny(module)
            except BaseException:
                return ErrorHolder(module, failure.Failure())
        if not inspect.ismodule(module):
            warnings.warn("trial only supports doctesting modules")
            return
        extraArgs = {}

        # Work around Python issue2604: DocTestCase.tearDown clobbers globs
        def saveGlobals(test):
            """
            Save C{test.globs} and replace it with a copy so that if
            necessary, the original will be available for the next test
            run.
            """
            test._savedGlobals = getattr(test, "_savedGlobals", test.globs)
            test.globs = test._savedGlobals.copy()

        extraArgs["setUp"] = saveGlobals
        return doctest.DocTestSuite(module, **extraArgs)

    def loadAnything(self, obj, recurse=False, parent=None, qualName=None):
        """
        Load absolutely anything (as long as that anything is a module,
        package, class, or method (with associated parent class and qualname).

        @param obj: The object to load.
        @param recurse: A boolean. If True, inspect modules within packages
            within the given package (and so on), otherwise, only inspect
            modules in the package itself.
        @param parent: If C{obj} is a method, this is the parent class of the
            method. C{qualName} is also required.
        @param qualName: If C{obj} is a method, this a list containing is the
            qualified name of the method. C{parent} is also required.

        @return: A C{TestCase} or C{TestSuite}.
        """
        if isinstance(obj, types.ModuleType):
            # It looks like a module
            if isPackage(obj):
                # It's a package, so recurse down it.
                return self.loadPackage(obj, recurse=recurse)
            # Otherwise get all the tests in the module.
            return self.loadTestsFromModule(obj)
        elif isinstance(obj, type) and issubclass(obj, pyunit.TestCase):
            # We've found a raw test case, get the tests from it.
            return self.loadTestsFromTestCase(obj)
        elif (
            isinstance(obj, types.FunctionType)
            and isinstance(parent, type)
            and issubclass(parent, pyunit.TestCase)
        ):
            # We've found a method, and its parent is a TestCase. Instantiate
            # it with the name of the method we want.
            name = qualName[-1]
            inst = parent(name)

            # Sanity check to make sure that the method we have got from the
            # test case is the same one as was passed in. This doesn't actually
            # use the function we passed in, because reasons.
            assert getattr(inst, inst._testMethodName).__func__ == obj

            return inst
        elif isinstance(obj, TestSuite):
            # We've found a test suite.
            return obj
        else:
            raise TypeError(f"don't know how to make test from: {obj}")

    def loadByName(self, name, recurse=False):
        """
        Load some tests by name.

        @param name: The qualified name for the test to load.
        @param recurse: A boolean. If True, inspect modules within packages
            within the given package (and so on), otherwise, only inspect
            modules in the package itself.
        """
        try:
            return self.suiteFactory([self.findByName(name, recurse=recurse)])
        except BaseException:
            return self.suiteFactory([ErrorHolder(name, failure.Failure())])

    loadTestsFromName = loadByName

    def loadByNames(self, names: List[str], recurse: bool = False) -> TestSuite:
        """
        Load some tests by a list of names.

        @param names: A L{list} of qualified names.
        @param recurse: A boolean. If True, inspect modules within packages
            within the given package (and so on), otherwise, only inspect
            modules in the package itself.
        """
        things = []
        errors = []
        for name in names:
            try:
                things.append(self.loadByName(name, recurse=recurse))
            except BaseException:
                errors.append(ErrorHolder(name, failure.Failure()))
        things.extend(errors)
        return self.suiteFactory(self._uniqueTests(things))

    def _uniqueTests(self, things):
        """
        Gather unique suite objects from loaded things. This will guarantee
        uniqueness of inherited methods on TestCases which would otherwise hash
        to same value and collapse to one test unexpectedly if using simpler
        means: e.g. set().
        """
        seen = set()
        for testthing in things:
            testthings = testthing._tests
            for thing in testthings:
                # This is horrible.
                if str(thing) not in seen:
                    yield thing
                    seen.add(str(thing))

    def loadFile(self, fileName, recurse=False):
        """
        Load a file, and then the tests in that file.

        @param fileName: The file name to load.
        @param recurse: A boolean. If True, inspect modules within packages
            within the given package (and so on), otherwise, only inspect
            modules in the package itself.
        """
        name = reflect.filenameToModuleName(fileName)
        try:
            module = SourceFileLoader(name, fileName).load_module()
            return self.loadAnything(module, recurse=recurse)
        except OSError:
            raise ValueError(f"{fileName} is not a Python file.")


def _qualNameWalker(qualName):
    """
    Given a Python qualified name, this function yields a 2-tuple of the most
    specific qualified name first, followed by the next-most-specific qualified
    name, and so on, paired with the remainder of the qualified name.

    @param qualName: A Python qualified name.
    @type qualName: L{str}
    """
    # Yield what we were just given
    yield (qualName, [])

    # If they want more, split the qualified name up
    qualParts = qualName.split(".")

    for index in range(1, len(qualParts)):
        # This code here will produce, from the example walker.texas.ranger:
        # (walker.texas, ["ranger"])
        # (walker, ["texas", "ranger"])
        yield (".".join(qualParts[:-index]), qualParts[-index:])


@contextmanager
def _testDirectory(workingDirectory: str) -> Generator[None, None, None]:
    """
    A context manager which obtains a lock on a trial working directory
    and enters (L{os.chdir}) it and then reverses these things.

    @param workingDirectory: A pattern for the basename of the working
        directory to acquire.
    """
    currentDir = os.getcwd()
    base = filepath.FilePath(workingDirectory)
    testdir, testDirLock = util._unusedTestDirectory(base)
    os.chdir(testdir.path)

    yield

    os.chdir(currentDir)
    testDirLock.unlock()


@contextmanager
def _logFile(logfile: str) -> Generator[None, None, None]:
    """
    A context manager which adds a log observer and then removes it.

    @param logfile: C{"-"} f or stdout logging, otherwise the path to a log
        file to which to write.
    """
    if logfile == "-":
        logFile = sys.stdout
    else:
        logFile = util.openTestLog(filepath.FilePath(logfile))

    logFileObserver = log.FileLogObserver(logFile)
    observerFunction = logFileObserver.emit
    log.startLoggingWithObserver(observerFunction, 0)

    yield

    log.removeObserver(observerFunction)
    logFile.close()


class _Runner(Protocol):
    stream: TextIO

    def run(self, test: Union[pyunit.TestCase, pyunit.TestSuite]) -> itrial.IReporter:
        ...

    def runUntilFailure(
        self, test: Union[pyunit.TestCase, pyunit.TestSuite]
    ) -> itrial.IReporter:
        ...


@define
class TrialRunner:
    """
    A specialised runner that the trial front end uses.

    @ivar reporterFactory: A callable to create a reporter to use.

    @ivar mode: Either C{None} for a normal test run, L{TrialRunner.DEBUG} for
        a run in the debugger, or L{TrialRunner.DRY_RUN} to collect and report
        the tests but not call any of them.

    @ivar logfile: The path to the file to write the test run log.

    @ivar stream: The file to report results to.

    @ivar profile: C{True} to run the tests with a profiler enabled.

    @ivar _tracebackFormat: A format name to use with L{Failure} for reporting
        failures.

    @ivar _realTimeErrors: C{True} if errors should be reported as they
        happen.  C{False} if they should only be reported at the end of the
        test run in the summary.

    @ivar uncleanWarnings: C{True} to report dirty reactor errors as warnings,
        C{False} to report them as test-failing errors.

    @ivar workingDirectory: A path template to a directory which will be the
        process's working directory while the tests are running.

    @ivar _forceGarbageCollection: C{True} to perform a full garbage
        collection at least after each test.  C{False} to let garbage
        collection run only when it normally would.

    @ivar debugger: In debug mode, an object to use to launch the debugger.

    @ivar _exitFirst: C{True} to stop after the first failed test.  C{False}
        to run the whole suite.

    @ivar log: An object to give to the reporter to use as a log publisher.
    """

    DEBUG = "debug"
    DRY_RUN = "dry-run"

    reporterFactory: Callable[[TextIO, str, bool, log.LogPublisher], itrial.IReporter]
    mode: Optional[str] = None
    logfile: str = "test.log"
    stream: TextIO = sys.stdout
    profile: bool = False
    _tracebackFormat: str = "default"
    _realTimeErrors: bool = False
    uncleanWarnings: bool = False
    workingDirectory: str = "_trial_temp"
    _forceGarbageCollection: bool = False
    debugger: Optional[_Debugger] = None
    _exitFirst: bool = False

    _log: log.LogPublisher = log  # type: ignore[assignment]

    def _makeResult(self) -> itrial.IReporter:
        reporter = self.reporterFactory(
            self.stream, self.tbformat, self.rterrors, self._log
        )
        if self._exitFirst:
            reporter = _ExitWrapper(reporter)
        if self.uncleanWarnings:
            reporter = UncleanWarningsReporterWrapper(reporter)
        return reporter

    @property
    def tbformat(self) -> str:
        return self._tracebackFormat

    @property
    def rterrors(self) -> bool:
        return self._realTimeErrors

    def run(self, test: Union[pyunit.TestCase, pyunit.TestSuite]) -> itrial.IReporter:
        """
        Run the test or suite and return a result object.
        """
        test = unittest.decorate(test, ITestCase)
        if self.profile:
            run = util.profiled(self._runWithoutDecoration, "profile.data")
        else:
            run = self._runWithoutDecoration
        return run(test, self._forceGarbageCollection)

    def _runWithoutDecoration(
        self,
        test: Union[pyunit.TestCase, pyunit.TestSuite],
        forceGarbageCollection: bool = False,
    ) -> itrial.IReporter:
        """
        Private helper that runs the given test but doesn't decorate it.
        """
        result = self._makeResult()
        # decorate the suite with reactor cleanup and log starting
        # This should move out of the runner and be presumed to be
        # present
        suite = TrialSuite([test], forceGarbageCollection)
        if self.mode == self.DRY_RUN:
            for single in _iterateTests(suite):
                result.startTest(single)
                result.addSuccess(single)
                result.stopTest(single)
        else:
            if self.mode == self.DEBUG:
                assert self.debugger is not None
                run = lambda: self.debugger.runcall(suite.run, result)
            else:
                run = lambda: suite.run(result)

            with _testDirectory(self.workingDirectory), _logFile(self.logfile):
                run()

        result.done()
        return result

    def runUntilFailure(
        self, test: Union[pyunit.TestCase, pyunit.TestSuite]
    ) -> itrial.IReporter:
        """
        Repeatedly run C{test} until it fails.
        """
        count = 0
        while True:
            count += 1
            self.stream.write("Test Pass %d\n" % (count,))
            if count == 1:
                # If test is a TestSuite, run *mutates it*.  So only follow
                # this code-path once!  Otherwise the decorations accumulate
                # forever.
                result = self.run(test)
            else:
                result = self._runWithoutDecoration(test)
            if result.testsRun == 0:
                break
            if not result.wasSuccessful():
                break
        return result
