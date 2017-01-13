# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.systemd}.
"""

from __future__ import division, absolute_import

import os

from twisted.trial.unittest import TestCase
from twisted.python.systemd import ListenFDs


class InheritedDescriptorsMixin(object):
    """
    Mixin for a L{TestCase} subclass which defines test methods for some kind of
    systemd sd-daemon class.  In particular, it defines tests for a
    C{inheritedDescriptors} method.
    """
    def test_inheritedDescriptors(self):
        """
        C{inheritedDescriptors} returns a list of integers giving the file
        descriptors which were inherited from systemd.
        """
        sddaemon = self.getDaemon(7, 3)
        self.assertEqual([7, 8, 9], sddaemon.inheritedDescriptors())


    def test_repeated(self):
        """
        Any subsequent calls to C{inheritedDescriptors} return the same list.
        """
        sddaemon = self.getDaemon(7, 3)
        self.assertEqual(
            sddaemon.inheritedDescriptors(),
            sddaemon.inheritedDescriptors())



class MemoryOnlyMixin(object):
    """
    Mixin for a L{TestCase} subclass which creates creating a fake, in-memory
    implementation of C{inheritedDescriptors}.  This provides verification that
    the fake behaves in a compatible way with the real implementation.
    """
    def getDaemon(self, start, count):
        """
        Invent C{count} new I{file descriptors} (actually integers, attached to
        no real file description), starting at C{start}.  Construct and return a
        new L{ListenFDs} which will claim those integers represent inherited
        file descriptors.
        """
        return ListenFDs(range(start, start + count))



class EnvironmentMixin(object):
    """
    Mixin for a L{TestCase} subclass which creates a real implementation of
    C{inheritedDescriptors} which is based on the environment variables set by
    systemd.  To facilitate testing, this mixin will also create a fake
    environment dictionary and add keys to it to make it look as if some
    descriptors have been inherited.
    """
    def initializeEnvironment(self, count, pid):
        """
        Create a copy of the process environment and add I{LISTEN_FDS} and
        I{LISTEN_PID} (the environment variables set by systemd) to it.
        """
        result = os.environ.copy()
        result['LISTEN_FDS'] = str(count)
        result['LISTEN_PID'] = str(pid)
        return result


    def getDaemon(self, start, count):
        """
        Create a new L{ListenFDs} instance, initialized with a fake environment
        dictionary which will be set up as systemd would have set it up if
        C{count} descriptors were being inherited.  The descriptors will also
        start at C{start}.
        """
        fakeEnvironment = self.initializeEnvironment(count, os.getpid())
        return ListenFDs.fromEnvironment(environ=fakeEnvironment, start=start)



class MemoryOnlyTests(MemoryOnlyMixin, InheritedDescriptorsMixin, TestCase):
    """
    Apply tests to L{ListenFDs}, explicitly constructed with some fake file
    descriptors.
    """



class EnvironmentTests(EnvironmentMixin, InheritedDescriptorsMixin, TestCase):
    """
    Apply tests to L{ListenFDs}, constructed based on an environment dictionary.
    """
    def test_secondEnvironment(self):
        """
        Only a single L{Environment} can extract inherited file descriptors.
        """
        fakeEnvironment = self.initializeEnvironment(3, os.getpid())
        first = ListenFDs.fromEnvironment(environ=fakeEnvironment)
        second = ListenFDs.fromEnvironment(environ=fakeEnvironment)
        self.assertEqual(list(range(3, 6)), first.inheritedDescriptors())
        self.assertEqual([], second.inheritedDescriptors())


    def test_mismatchedPID(self):
        """
        If the current process PID does not match the PID in the environment, no
        inherited descriptors are reported.
        """
        fakeEnvironment = self.initializeEnvironment(3, os.getpid() + 1)
        sddaemon = ListenFDs.fromEnvironment(environ=fakeEnvironment)
        self.assertEqual([], sddaemon.inheritedDescriptors())


    def test_missingPIDVariable(self):
        """
        If the I{LISTEN_PID} environment variable is not present, no inherited
        descriptors are reported.
        """
        fakeEnvironment = self.initializeEnvironment(3, os.getpid())
        del fakeEnvironment['LISTEN_PID']
        sddaemon = ListenFDs.fromEnvironment(environ=fakeEnvironment)
        self.assertEqual([], sddaemon.inheritedDescriptors())


    def test_nonIntegerPIDVariable(self):
        """
        If the I{LISTEN_PID} environment variable is set to a string that cannot
        be parsed as an integer, no inherited descriptors are reported.
        """
        fakeEnvironment = self.initializeEnvironment(3, "hello, world")
        sddaemon = ListenFDs.fromEnvironment(environ=fakeEnvironment)
        self.assertEqual([], sddaemon.inheritedDescriptors())


    def test_missingFDSVariable(self):
        """
        If the I{LISTEN_FDS} environment variable is not present, no inherited
        descriptors are reported.
        """
        fakeEnvironment = self.initializeEnvironment(3, os.getpid())
        del fakeEnvironment['LISTEN_FDS']
        sddaemon = ListenFDs.fromEnvironment(environ=fakeEnvironment)
        self.assertEqual([], sddaemon.inheritedDescriptors())


    def test_nonIntegerFDSVariable(self):
        """
        If the I{LISTEN_FDS} environment variable is set to a string that cannot
        be parsed as an integer, no inherited descriptors are reported.
        """
        fakeEnvironment = self.initializeEnvironment("hello, world", os.getpid())
        sddaemon = ListenFDs.fromEnvironment(environ=fakeEnvironment)
        self.assertEqual([], sddaemon.inheritedDescriptors())


    def test_defaultEnviron(self):
        """
        If the process environment is not explicitly passed to
        L{Environment.__init__}, the real process environment dictionary is
        used.
        """
        self.patch(os, 'environ', {
                'LISTEN_PID': str(os.getpid()),
                'LISTEN_FDS': '5'})
        sddaemon = ListenFDs.fromEnvironment()
        self.assertEqual(list(range(3, 3 + 5)),
            sddaemon.inheritedDescriptors())
