# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.internet.asyncioreactor}.
"""
import gc
import sys
from asyncio import (
    DefaultEventLoopPolicy,
    Future,
    SelectorEventLoop,
    set_event_loop,
    set_event_loop_policy,
)
from unittest import skipIf

from twisted.internet.asyncioreactor import AsyncioSelectorReactor
from twisted.python.runtime import platform
from twisted.trial.unittest import SynchronousTestCase
from .reactormixins import ReactorBuilder

hasWindowsProactorEventLoopPolicy = False
hasWindowsSelectorEventLoopPolicy = False

try:
    if sys.platform.startswith("win32"):
        from asyncio import (
            WindowsProactorEventLoopPolicy,
            WindowsSelectorEventLoopPolicy,
        )

        hasWindowsProactorEventLoopPolicy = True
        hasWindowsSelectorEventLoopPolicy = True
except ImportError:
    pass


class AsyncioSelectorReactorTests(ReactorBuilder, SynchronousTestCase):
    """
    L{AsyncioSelectorReactor} tests.
    """

    _defaultEventLoop = DefaultEventLoopPolicy().new_event_loop()
    _defaultEventLoopIsSelector = isinstance(_defaultEventLoop, SelectorEventLoop)

    def assertReactorWorksWithAsyncioFuture(self, reactor):
        """
        Ensure that C{reactor} has an event loop that works
        properly with L{asyncio.Future}.
        """
        future = Future()
        result = []

        def completed(future):
            result.append(future.result())
            reactor.stop()

        future.add_done_callback(completed)
        future.set_result(True)

        self.assertEqual(result, [])
        self.runReactor(reactor, timeout=1)
        self.assertEqual(result, [True])

    @skipIf(
        not _defaultEventLoopIsSelector,
        "default event loop: {}\nis not of type SelectorEventLoop "
        "on Python {}.{} ({})".format(
            type(_defaultEventLoop),
            sys.version_info.major,
            sys.version_info.minor,
            platform.getType(),
        ),
    )
    def test_defaultSelectorEventLoopFromGlobalPolicy(self):
        """
        L{AsyncioSelectorReactor} wraps the global policy's event loop
        by default.  This ensures that L{asyncio.Future}s and
        coroutines created by library code that uses
        L{asyncio.get_event_loop} are bound to the same loop.
        """
        reactor = AsyncioSelectorReactor()
        self.assertReactorWorksWithAsyncioFuture(reactor)

    @skipIf(
        not _defaultEventLoopIsSelector,
        "default event loop: {}\nis not of type SelectorEventLoop "
        "on Python {}.{} ({})".format(
            type(_defaultEventLoop),
            sys.version_info.major,
            sys.version_info.minor,
            platform.getType(),
        ),
    )
    def test_newSelectorEventLoopFromDefaultEventLoopPolicy(self):
        """
        If we use the L{asyncio.DefaultLoopPolicy} to create a new event loop,
        and then pass that event loop to a new L{AsyncioSelectorReactor},
        this reactor should work properly with L{asyncio.Future}.
        """
        event_loop = DefaultEventLoopPolicy().new_event_loop()
        reactor = AsyncioSelectorReactor(event_loop)
        set_event_loop(event_loop)
        self.assertReactorWorksWithAsyncioFuture(reactor)
        set_event_loop_policy(None)

    @skipIf(
        _defaultEventLoopIsSelector,
        "default event loop: {}\nis of type SelectorEventLoop "
        "on Python {}.{} ({})".format(
            type(_defaultEventLoop),
            sys.version_info.major,
            sys.version_info.minor,
            platform.getType(),
        ),
    )
    def test_defaultNotASelectorEventLoopFromGlobalPolicy(self):
        """
        On Windows Python 3.5 to 3.7, L{get_event_loop()} returns a
        L{WindowsSelectorEventLoop} by default.
        On Windows Python 3.8+, L{get_event_loop()} returns a
        L{WindowsProactorEventLoop} by default.
        L{AsyncioSelectorReactor} should raise a
        L{TypeError} if the default event loop is not a
        L{WindowsSelectorEventLoop}.
        """
        self.assertRaises(TypeError, AsyncioSelectorReactor)

    @skipIf(
        not hasWindowsProactorEventLoopPolicy, "WindowsProactorEventLoop not available"
    )
    def test_WindowsProactorEventLoop(self):
        """
        L{AsyncioSelectorReactor} will raise a L{TypeError}
        if instantiated with a L{asyncio.WindowsProactorEventLoop}
        """
        event_loop = WindowsProactorEventLoopPolicy().new_event_loop()
        self.assertRaises(TypeError, AsyncioSelectorReactor, event_loop)

    @skipIf(
        not hasWindowsSelectorEventLoopPolicy,
        "WindowsSelectorEventLoop only on Windows",
    )
    def test_WindowsSelectorEventLoop(self):
        """
        L{WindowsSelectorEventLoop} works with L{AsyncioSelectorReactor}
        """
        event_loop = WindowsSelectorEventLoopPolicy().new_event_loop()
        reactor = AsyncioSelectorReactor(event_loop)
        set_event_loop(event_loop)
        self.assertReactorWorksWithAsyncioFuture(reactor)
        set_event_loop_policy(None)

    @skipIf(
        not hasWindowsProactorEventLoopPolicy,
        "WindowsProactorEventLoopPolicy only on Windows",
    )
    def test_WindowsProactorEventLoopPolicy(self):
        """
        L{AsyncioSelectorReactor} will raise a L{TypeError}
        if L{asyncio.WindowsProactorEventLoopPolicy} is default.
        """
        set_event_loop_policy(WindowsProactorEventLoopPolicy())
        with self.assertRaises(TypeError):
            AsyncioSelectorReactor()
        set_event_loop_policy(None)

    @skipIf(
        not hasWindowsSelectorEventLoopPolicy,
        "WindowsSelectorEventLoopPolicy only on Windows",
    )
    def test_WindowsSelectorEventLoopPolicy(self):
        """
        L{AsyncioSelectorReactor} will work if
        if L{asyncio.WindowsSelectorEventLoopPolicy} is default.
        """
        set_event_loop_policy(WindowsSelectorEventLoopPolicy())
        reactor = AsyncioSelectorReactor()
        self.assertReactorWorksWithAsyncioFuture(reactor)
        set_event_loop_policy(None)

    def test_seconds(self):
        """L{seconds} should return a plausible epoch time."""
        if hasWindowsSelectorEventLoopPolicy:
            set_event_loop_policy(WindowsSelectorEventLoopPolicy())
        reactor = AsyncioSelectorReactor()
        result = reactor.seconds()

        # greater than 2020-01-01
        self.assertGreater(result, 1577836800)

        # less than 2120-01-01
        self.assertLess(result, 4733510400)
        if hasWindowsSelectorEventLoopPolicy:
            set_event_loop_policy(None)

    def test_delayedCallResetToLater(self):
        """
        L{DelayedCall.reset()} properly reschedules timer to later time
        """
        if hasWindowsSelectorEventLoopPolicy:
            set_event_loop_policy(WindowsSelectorEventLoopPolicy())

        reactor = AsyncioSelectorReactor()

        timer_called_at = [None]

        def on_timer():
            timer_called_at[0] = reactor.seconds()

        start_time = reactor.seconds()
        dc = reactor.callLater(0, on_timer)
        dc.reset(0.5)
        reactor.callLater(1, reactor.stop)
        reactor.run()

        self.assertIsNotNone(timer_called_at[0])
        self.assertGreater(timer_called_at[0] - start_time, 0.4)
        if hasWindowsSelectorEventLoopPolicy:
            set_event_loop_policy(None)

    def test_delayedCallResetToEarlier(self):
        """
        L{DelayedCall.reset()} properly reschedules timer to earlier time
        """
        if hasWindowsSelectorEventLoopPolicy:
            set_event_loop_policy(WindowsSelectorEventLoopPolicy())
        reactor = AsyncioSelectorReactor()

        timer_called_at = [None]

        def on_timer():
            timer_called_at[0] = reactor.seconds()

        start_time = reactor.seconds()
        dc = reactor.callLater(0.5, on_timer)
        dc.reset(0)
        reactor.callLater(1, reactor.stop)

        import io
        from contextlib import redirect_stderr

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            reactor.run()

        self.assertEqual(stderr.getvalue(), "")
        self.assertIsNotNone(timer_called_at[0])
        self.assertLess(timer_called_at[0] - start_time, 0.4)
        if hasWindowsSelectorEventLoopPolicy:
            set_event_loop_policy(None)

    def test_noCycleReferencesInCallLater(self):
        """
        L{AsyncioSelectorReactor.callLater()} doesn't leave cyclic references
        """
        if hasWindowsSelectorEventLoopPolicy:
            set_event_loop_policy(WindowsSelectorEventLoopPolicy())
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            objects_before = len(gc.get_objects())
            timer_count = 1000

            reactor = AsyncioSelectorReactor()
            for _ in range(timer_count):
                reactor.callLater(0, lambda: None)
            reactor.runUntilCurrent()

            objects_after = len(gc.get_objects())
            self.assertLess((objects_after - objects_before) / timer_count, 1)
        finally:
            if gc_was_enabled:
                gc.enable()
        if hasWindowsSelectorEventLoopPolicy:
            set_event_loop_policy(None)
