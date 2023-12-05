# -*- test-case-name: twisted.trial.test.test_util -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
#

"""
A collection of utility functions and classes, used internally by Trial.

This code is for Trial's internal use.  Do NOT use this code if you are writing
tests.  It is subject to change at the Trial maintainer's whim.  There is
nothing here in this module for you to use unless you are maintaining Trial.

Any non-Trial Twisted code that uses this module will be shot.

Maintainer: Jonathan Lange

@var DEFAULT_TIMEOUT_DURATION: The default timeout which will be applied to
    asynchronous (ie, Deferred-returning) test methods, in seconds.
"""
from random import randrange
from typing import Callable, TextIO, TypeVar

from typing_extensions import ParamSpec

from twisted.internet import interfaces, utils
from twisted.python.failure import Failure
from twisted.python.filepath import FilePath
from twisted.python.lockfile import FilesystemLock

__all__ = [
    "DEFAULT_TIMEOUT_DURATION",
    "excInfoOrFailureToExcInfo",
    "suppress",
    "acquireAttribute",
]

DEFAULT_TIMEOUT = object()
DEFAULT_TIMEOUT_DURATION = 120.0


class DirtyReactorAggregateError(Exception):
    """
    Passed to L{twisted.trial.itrial.IReporter.addError} when the reactor is
    left in an unclean state after a test.

    @ivar delayedCalls: The L{DelayedCall<twisted.internet.base.DelayedCall>}
        objects which weren't cleaned up.
    @ivar selectables: The selectables which weren't cleaned up.
    """

    def __init__(self, delayedCalls, selectables=None):
        self.delayedCalls = delayedCalls
        self.selectables = selectables

    def __str__(self) -> str:
        """
        Return a multi-line message describing all of the unclean state.
        """
        msg = "Reactor was unclean."
        if self.delayedCalls:
            msg += (
                "\nDelayedCalls: (set "
                "twisted.internet.base.DelayedCall.debug = True to "
                "debug)\n"
            )
            msg += "\n".join(map(str, self.delayedCalls))
        if self.selectables:
            msg += "\nSelectables:\n"
            msg += "\n".join(map(str, self.selectables))
        return msg


class _Janitor:
    """
    The guy that cleans up after you.

    @ivar test: The L{TestCase} to report errors about.
    @ivar result: The L{IReporter} to report errors to.
    @ivar reactor: The reactor to use. If None, the global reactor
        will be used.
    """

    def __init__(self, test, result, reactor=None):
        """
        @param test: See L{_Janitor.test}.
        @param result: See L{_Janitor.result}.
        @param reactor: See L{_Janitor.reactor}.
        """
        self.test = test
        self.result = result
        self.reactor = reactor

    def postCaseCleanup(self):
        """
        Called by L{unittest.TestCase} after a test to catch any logged errors
        or pending L{DelayedCall<twisted.internet.base.DelayedCall>}s.
        """
        calls = self._cleanPending()
        if calls:
            aggregate = DirtyReactorAggregateError(calls)
            self.result.addError(self.test, Failure(aggregate))
            return False
        return True

    def postClassCleanup(self):
        """
        Called by L{unittest.TestCase} after the last test in a C{TestCase}
        subclass. Ensures the reactor is clean by murdering the threadpool,
        catching any pending
        L{DelayedCall<twisted.internet.base.DelayedCall>}s, open sockets etc.
        """
        selectables = self._cleanReactor()
        calls = self._cleanPending()
        if selectables or calls:
            aggregate = DirtyReactorAggregateError(calls, selectables)
            self.result.addError(self.test, Failure(aggregate))
        self._cleanThreads()

    def _getReactor(self):
        """
        Get either the passed-in reactor or the global reactor.
        """
        if self.reactor is not None:
            reactor = self.reactor
        else:
            from twisted.internet import reactor
        return reactor

    def _cleanPending(self):
        """
        Cancel all pending calls and return their string representations.
        """
        reactor = self._getReactor()

        # flush short-range timers
        reactor.iterate(0)
        reactor.iterate(0)

        delayedCallStrings = []
        for p in reactor.getDelayedCalls():
            if p.active():
                delayedString = str(p)
                p.cancel()
            else:
                print("WEIRDNESS! pending timed call not active!")
            delayedCallStrings.append(delayedString)
        return delayedCallStrings

    _cleanPending = utils.suppressWarnings(
        _cleanPending,
        (
            ("ignore",),
            {
                "category": DeprecationWarning,
                "message": r"reactor\.iterate cannot be used.*",
            },
        ),
    )

    def _cleanThreads(self):
        reactor = self._getReactor()
        if interfaces.IReactorThreads.providedBy(reactor):
            if reactor.threadpool is not None:
                # Stop the threadpool now so that a new one is created.
                # This improves test isolation somewhat (although this is a
                # post class cleanup hook, so it's only isolating classes
                # from each other, not methods from each other).
                reactor._stopThreadPool()

    def _cleanReactor(self):
        """
        Remove all selectables from the reactor, kill any of them that were
        processes, and return their string representation.
        """
        reactor = self._getReactor()
        selectableStrings = []
        for sel in reactor.removeAll():
            if interfaces.IProcessTransport.providedBy(sel):
                sel.signalProcess("KILL")
            selectableStrings.append(repr(sel))
        return selectableStrings


_DEFAULT = object()


def acquireAttribute(objects, attr, default=_DEFAULT):
    """
    Go through the list 'objects' sequentially until we find one which has
    attribute 'attr', then return the value of that attribute.  If not found,
    return 'default' if set, otherwise, raise AttributeError.
    """
    for obj in objects:
        if hasattr(obj, attr):
            return getattr(obj, attr)
    if default is not _DEFAULT:
        return default
    raise AttributeError(f"attribute {attr!r} not found in {objects!r}")


def excInfoOrFailureToExcInfo(err):
    """
    Coerce a Failure to an _exc_info, if err is a Failure.

    @param err: Either a tuple such as returned by L{sys.exc_info} or a
        L{Failure} object.
    @return: A tuple like the one returned by L{sys.exc_info}. e.g.
        C{exception_type, exception_object, traceback_object}.
    """
    if isinstance(err, Failure):
        # Unwrap the Failure into an exc_info tuple.
        err = (err.type, err.value, err.getTracebackObject())
    return err


def suppress(action="ignore", **kwarg):
    """
    Sets up the .suppress tuple properly, pass options to this method as you
    would the stdlib warnings.filterwarnings()

    So, to use this with a .suppress magic attribute you would do the
    following:

      >>> from twisted.trial import unittest, util
      >>> import warnings
      >>>
      >>> class TestFoo(unittest.TestCase):
      ...     def testFooBar(self):
      ...         warnings.warn("i am deprecated", DeprecationWarning)
      ...     testFooBar.suppress = [util.suppress(message='i am deprecated')]
      ...
      >>>

    Note that as with the todo and timeout attributes: the module level
    attribute acts as a default for the class attribute which acts as a default
    for the method attribute. The suppress attribute can be overridden at any
    level by specifying C{.suppress = []}
    """
    return ((action,), kwarg)


# This should be deleted, and replaced with twisted.application's code; see
# https://github.com/twisted/twisted/issues/6016:
_P = ParamSpec("_P")
_T = TypeVar("_T")


def profiled(f: Callable[_P, _T], outputFile: str) -> Callable[_P, _T]:
    def _(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        import profile

        prof = profile.Profile()
        try:
            result = prof.runcall(f, *args, **kwargs)
            prof.dump_stats(outputFile)
        except SystemExit:
            pass
        prof.print_stats()
        return result

    return _


class _NoTrialMarker(Exception):
    """
    No trial marker file could be found.

    Raised when trial attempts to remove a trial temporary working directory
    that does not contain a marker file.
    """


def _removeSafely(path):
    """
    Safely remove a path, recursively.

    If C{path} does not contain a node named C{_trial_marker}, a
    L{_NoTrialMarker} exception is raised and the path is not removed.
    """
    if not path.child(b"_trial_marker").exists():
        raise _NoTrialMarker(
            f"{path!r} is not a trial temporary path, refusing to remove it"
        )
    try:
        path.remove()
    except OSError as e:
        print(
            "could not remove %r, caught OSError [Errno %s]: %s"
            % (path, e.errno, e.strerror)
        )
        try:
            newPath = FilePath(
                b"_trial_temp_old" + str(randrange(10000000)).encode("utf-8")
            )
            path.moveTo(newPath)
        except OSError as e:
            print(
                "could not rename path, caught OSError [Errno %s]: %s"
                % (e.errno, e.strerror)
            )
            raise


class _WorkingDirectoryBusy(Exception):
    """
    A working directory was specified to the runner, but another test run is
    currently using that directory.
    """


def _unusedTestDirectory(base):
    """
    Find an unused directory named similarly to C{base}.

    Once a directory is found, it will be locked and a marker dropped into it
    to identify it as a trial temporary directory.

    @param base: A template path for the discovery process.  If this path
        exactly cannot be used, a path which varies only in a suffix of the
        basename will be used instead.
    @type base: L{FilePath}

    @return: A two-tuple.  The first element is a L{FilePath} representing the
        directory which was found and created.  The second element is a locked
        L{FilesystemLock<twisted.python.lockfile.FilesystemLock>}.  Another
        call to C{_unusedTestDirectory} will not be able to reused the
        same name until the lock is released, either explicitly or by this
        process exiting.
    """
    counter = 0
    while True:
        if counter:
            testdir = base.sibling("%s-%d" % (base.basename(), counter))
        else:
            testdir = base

        testdir.parent().makedirs(ignoreExistingDirectory=True)
        testDirLock = FilesystemLock(testdir.path + ".lock")
        if testDirLock.lock():
            # It is not in use
            if testdir.exists():
                # It exists though - delete it
                _removeSafely(testdir)

            # Create it anew and mark it as ours so the next _removeSafely on
            # it succeeds.
            testdir.makedirs()
            testdir.child(b"_trial_marker").setContent(b"")
            return testdir, testDirLock
        else:
            # It is in use
            if base.basename() == "_trial_temp":
                counter += 1
            else:
                raise _WorkingDirectoryBusy()


def _listToPhrase(things, finalDelimiter, delimiter=", "):
    """
    Produce a string containing each thing in C{things},
    separated by a C{delimiter}, with the last couple being separated
    by C{finalDelimiter}

    @param things: The elements of the resulting phrase
    @type things: L{list} or L{tuple}

    @param finalDelimiter: What to put between the last two things
        (typically 'and' or 'or')
    @type finalDelimiter: L{str}

    @param delimiter: The separator to use between each thing,
        not including the last two. Should typically include a trailing space.
    @type delimiter: L{str}

    @return: The resulting phrase
    @rtype: L{str}
    """
    if not isinstance(things, (list, tuple)):
        raise TypeError("Things must be a list or a tuple")
    if not things:
        return ""
    if len(things) == 1:
        return str(things[0])
    if len(things) == 2:
        return f"{str(things[0])} {finalDelimiter} {str(things[1])}"
    else:
        strThings = []
        for thing in things:
            strThings.append(str(thing))
        return "{}{}{} {}".format(
            delimiter.join(strThings[:-1]),
            delimiter,
            finalDelimiter,
            strThings[-1],
        )


def openTestLog(path: FilePath) -> TextIO:
    """
    Open the given path such that test log messages can be written to it.
    """
    path.parent().makedirs(ignoreExistingDirectory=True)
    # Always use UTF-8 because, considering all platforms, the system default
    # encoding can not reliably encode all code points.
    return open(path.path, "a", encoding="utf-8", errors="strict")
