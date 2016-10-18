# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for implementations of L{IReactorTime}.
"""

__metaclass__ = type

from twisted.python.log import msg
from twisted.python.runtime import platform

from twisted.trial.unittest import SkipTest
from twisted.internet.test.reactormixins import ReactorBuilder
from twisted.internet.interfaces import IReactorTime, IReactorThreads


class TimeTestsBuilder(ReactorBuilder):
    """
    Builder for defining tests relating to L{IReactorTime}.
    """
    requiredInterfaces = (IReactorTime,)

    def test_delayedCallStopsReactor(self):
        """
        The reactor can be stopped by a delayed call.
        """
        reactor = self.buildReactor()
        reactor.callLater(0, reactor.stop)
        reactor.run()


    def test_distantDelayedCall(self):
        """
        Scheduling a delayed call at a point in the extreme future does not
        prevent normal reactor operation.
        """
        reactor = self.buildReactor()
        if IReactorThreads.providedBy(reactor):
            def eventSource(reactor, event):
                msg(format="Thread-based event-source scheduling %(event)r",
                    event=event)
                reactor.callFromThread(event)
        else:
            raise SkipTest("Do not know how to synthesize non-time event to "
                           "stop the test")

        # Pick a pretty big delay.
        delayedCall = reactor.callLater(2 ** 128 + 1, lambda: None)

        def stop():
            msg("Stopping the reactor")
            reactor.stop()

        # Use repeated invocation of the event source to set up the call to stop
        # the reactor.  This makes it more likely at least one normal iteration
        # will take place with the delayed call in place before the slightly
        # different reactor shutdown logic alters things.
        eventSource(reactor, lambda: eventSource(reactor, stop))

        # Run the reactor directly, without a timeout.  A timeout would
        # interfere with the purpose of this test, which is to have the timeout
        # passed to the reactor's doIterate implementation (potentially) be
        # very, very large.  Hopefully the event source defined above will work
        # and cause the reactor to stop.
        reactor.run()

        # The reactor almost surely stopped before the delayed call
        # fired... right?
        self.assertTrue(delayedCall.active())
        self.assertIn(delayedCall, reactor.getDelayedCalls())



class GlibTimeTestsBuilder(ReactorBuilder):
    """
    Builder for defining tests relating to L{IReactorTime} for reactors based
    off glib.
    """
    requiredInterfaces = (IReactorTime,)

    if platform.isWindows():
        _reactors = ["twisted.internet.gtk2reactor.PortableGtkReactor"]
    else:
        _reactors = ["twisted.internet.glib2reactor.Glib2Reactor",
                     "twisted.internet.gtk2reactor.Gtk2Reactor"]

    def test_timeout_add(self):
        """
        A
        L{reactor.callLater<twisted.internet.interfaces.IReactorTime.callLater>}
        call scheduled from a C{gobject.timeout_add}
        call is run on time.
        """
        import gobject
        reactor = self.buildReactor()

        result = []
        def gschedule():
            reactor.callLater(0, callback)
            return 0
        def callback():
            result.append(True)
            reactor.stop()

        reactor.callWhenRunning(gobject.timeout_add, 10, gschedule)
        self.runReactor(reactor, 5)
        self.assertEqual(result, [True])


globals().update(TimeTestsBuilder.makeTestCaseClasses())
globals().update(GlibTimeTestsBuilder.makeTestCaseClasses())
