# -*- test-case-name: twisted.python.test.test_util
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.util}.
"""

from __future__ import division, absolute_import

import errno
import os.path
import shutil
import sys
import warnings

try:
    import pwd, grp
except ImportError:
    pwd = grp = None

from twisted.trial import unittest
from twisted.trial.util import suppress as SUPPRESS

from twisted.python import util
from twisted.python.filepath import FilePath
from twisted.internet import reactor
from twisted.internet.interfaces import IReactorProcess
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.defer import Deferred
from twisted.internet.error import ProcessDone
from twisted.test.test_process import MockOS


pyExe = FilePath(sys.executable)._asBytesPath()


class UtilTests(unittest.TestCase):

    def testUniq(self):
        l = ["a", 1, "ab", "a", 3, 4, 1, 2, 2, 4, 6]
        self.assertEqual(util.uniquify(l), ["a", 1, "ab", 3, 4, 2, 6])

    def testRaises(self):
        self.assertTrue(util.raises(ZeroDivisionError, divmod, 1, 0))
        self.assertFalse(util.raises(ZeroDivisionError, divmod, 0, 1))

        try:
            util.raises(TypeError, divmod, 1, 0)
        except ZeroDivisionError:
            pass
        else:
            raise unittest.FailTest("util.raises didn't raise when it should have")


    def test_uidFromNumericString(self):
        """
        When L{uidFromString} is called with a base-ten string representation
        of an integer, it returns the integer.
        """
        self.assertEqual(util.uidFromString("100"), 100)


    def test_uidFromUsernameString(self):
        """
        When L{uidFromString} is called with a base-ten string representation
        of an integer, it returns the integer.
        """
        pwent = pwd.getpwuid(os.getuid())
        self.assertEqual(util.uidFromString(pwent.pw_name), pwent.pw_uid)
    if pwd is None:
        test_uidFromUsernameString.skip = (
            "Username/UID conversion requires the pwd module.")


    def test_gidFromNumericString(self):
        """
        When L{gidFromString} is called with a base-ten string representation
        of an integer, it returns the integer.
        """
        self.assertEqual(util.gidFromString("100"), 100)


    def test_gidFromGroupnameString(self):
        """
        When L{gidFromString} is called with a base-ten string representation
        of an integer, it returns the integer.
        """
        grent = grp.getgrgid(os.getgid())
        self.assertEqual(util.gidFromString(grent.gr_name), grent.gr_gid)
    if grp is None:
        test_gidFromGroupnameString.skip = (
            "Group Name/GID conversion requires the grp module.")



class NameToLabelTests(unittest.TestCase):
    """
    Tests for L{nameToLabel}.
    """

    def test_nameToLabel(self):
        """
        Test the various kinds of inputs L{nameToLabel} supports.
        """
        nameData = [
            ('f', 'F'),
            ('fo', 'Fo'),
            ('foo', 'Foo'),
            ('fooBar', 'Foo Bar'),
            ('fooBarBaz', 'Foo Bar Baz'),
            ]
        for inp, out in nameData:
            got = util.nameToLabel(inp)
            self.assertEqual(
                got, out,
                "nameToLabel(%r) == %r != %r" % (inp, got, out))



class UntilConcludesTests(unittest.TestCase):
    """
    Tests for L{untilConcludes}, an C{EINTR} helper.
    """
    def test_uninterruptably(self):
        """
        L{untilConcludes} calls the function passed to it until the function
        does not raise either L{OSError} or L{IOError} with C{errno} of
        C{EINTR}.  It otherwise completes with the same result as the function
        passed to it.
        """
        def f(a, b):
            self.calls += 1
            exc = self.exceptions.pop()
            if exc is not None:
                raise exc(errno.EINTR, "Interrupted system call!")
            return a + b

        self.exceptions = [None]
        self.calls = 0
        self.assertEqual(util.untilConcludes(f, 1, 2), 3)
        self.assertEqual(self.calls, 1)

        self.exceptions = [None, OSError, IOError]
        self.calls = 0
        self.assertEqual(util.untilConcludes(f, 2, 3), 5)
        self.assertEqual(self.calls, 3)



class SwitchUIDTests(unittest.TestCase):
    """
    Tests for L{util.switchUID}.
    """

    if getattr(os, "getuid", None) is None:
        skip = "getuid/setuid not available"


    def setUp(self):
        self.mockos = MockOS()
        self.patch(util, "os", self.mockos)
        self.patch(util, "initgroups", self.initgroups)
        self.initgroupsCalls = []


    def initgroups(self, uid, gid):
        """
        Save L{util.initgroups} calls in C{self.initgroupsCalls}.
        """
        self.initgroupsCalls.append((uid, gid))


    def test_uid(self):
        """
        L{util.switchUID} calls L{util.initgroups} and then C{os.setuid} with
        the given uid.
        """
        util.switchUID(12000, None)
        self.assertEqual(self.initgroupsCalls, [(12000, None)])
        self.assertEqual(self.mockos.actions, [("setuid", 12000)])


    def test_euid(self):
        """
        L{util.switchUID} calls L{util.initgroups} and then C{os.seteuid} with
        the given uid if the C{euid} parameter is set to C{True}.
        """
        util.switchUID(12000, None, True)
        self.assertEqual(self.initgroupsCalls, [(12000, None)])
        self.assertEqual(self.mockos.seteuidCalls, [12000])


    def test_currentUID(self):
        """
        If the current uid is the same as the uid passed to L{util.switchUID},
        then initgroups does not get called, but a warning is issued.
        """
        uid = self.mockos.getuid()
        util.switchUID(uid, None)
        self.assertEqual(self.initgroupsCalls, [])
        self.assertEqual(self.mockos.actions, [])
        currentWarnings = self.flushWarnings([util.switchUID])
        self.assertEqual(len(currentWarnings), 1)
        self.assertIn('tried to drop privileges and setuid %i' % uid,
                      currentWarnings[0]['message'])
        self.assertIn(
            'but uid is already %i' % uid, currentWarnings[0]['message'])


    def test_currentEUID(self):
        """
        If the current euid is the same as the euid passed to L{util.switchUID},
        then initgroups does not get called, but a warning is issued.
        """
        euid = self.mockos.geteuid()
        util.switchUID(euid, None, True)
        self.assertEqual(self.initgroupsCalls, [])
        self.assertEqual(self.mockos.seteuidCalls, [])
        currentWarnings = self.flushWarnings([util.switchUID])
        self.assertEqual(len(currentWarnings), 1)
        self.assertIn('tried to drop privileges and seteuid %i' % euid,
                      currentWarnings[0]['message'])
        self.assertIn(
            'but euid is already %i' % euid, currentWarnings[0]['message'])



class MergeFunctionMetadataTests(unittest.TestCase):
    """
    Tests for L{mergeFunctionMetadata}.
    """

    def test_mergedFunctionBehavesLikeMergeTarget(self):
        """
        After merging C{foo}'s data into C{bar}, the returned function behaves
        as if it is C{bar}.
        """
        foo_object = object()
        bar_object = object()

        def foo():
            return foo_object

        def bar(x, y, ab, c=10, *d, **e):
            (a, b) = ab
            return bar_object

        baz = util.mergeFunctionMetadata(foo, bar)
        self.assertIs(baz(1, 2, (3, 4), quux=10), bar_object)


    def test_moduleIsMerged(self):
        """
        Merging C{foo} into C{bar} returns a function with C{foo}'s
        C{__module__}.
        """
        def foo():
            pass

        def bar():
            pass
        bar.__module__ = 'somewhere.else'

        baz = util.mergeFunctionMetadata(foo, bar)
        self.assertEqual(baz.__module__, foo.__module__)


    def test_docstringIsMerged(self):
        """
        Merging C{foo} into C{bar} returns a function with C{foo}'s docstring.
        """

        def foo():
            """
            This is foo.
            """

        def bar():
            """
            This is bar.
            """

        baz = util.mergeFunctionMetadata(foo, bar)
        self.assertEqual(baz.__doc__, foo.__doc__)


    def test_nameIsMerged(self):
        """
        Merging C{foo} into C{bar} returns a function with C{foo}'s name.
        """

        def foo():
            pass

        def bar():
            pass

        baz = util.mergeFunctionMetadata(foo, bar)
        self.assertEqual(baz.__name__, foo.__name__)


    def test_instanceDictionaryIsMerged(self):
        """
        Merging C{foo} into C{bar} returns a function with C{bar}'s
        dictionary, updated by C{foo}'s.
        """

        def foo():
            pass
        foo.a = 1
        foo.b = 2

        def bar():
            pass
        bar.b = 3
        bar.c = 4

        baz = util.mergeFunctionMetadata(foo, bar)
        self.assertEqual(foo.a, baz.a)
        self.assertEqual(foo.b, baz.b)
        self.assertEqual(bar.c, baz.c)



class OrderedDictTests(unittest.TestCase):
    """
    Tests for L{util.OrderedDict}.
    """
    def test_deprecated(self):
        """
        L{util.OrderedDict} is deprecated.
        """
        from twisted.python.util import OrderedDict
        OrderedDict # Shh pyflakes

        currentWarnings = self.flushWarnings(offendingFunctions=[
            self.test_deprecated])
        self.assertEqual(
            currentWarnings[0]['message'],
            "twisted.python.util.OrderedDict was deprecated in Twisted "
            "15.5.0: Use collections.OrderedDict instead.")
        self.assertEqual(currentWarnings[0]['category'], DeprecationWarning)
        self.assertEqual(len(currentWarnings), 1)



class InsensitiveDictTests(unittest.TestCase):
    """
    Tests for L{util.InsensitiveDict}.
    """

    def test_preserve(self):
        """
        L{util.InsensitiveDict} preserves the case of keys if constructed with
        C{preserve=True}.
        """
        dct = util.InsensitiveDict({'Foo':'bar', 1:2, 'fnz':{1:2}}, preserve=1)
        self.assertEqual(dct['fnz'], {1:2})
        self.assertEqual(dct['foo'], 'bar')
        self.assertEqual(dct.copy(), dct)
        self.assertEqual(dct['foo'], dct.get('Foo'))
        self.assertIn(1, dct)
        self.assertIn('foo', dct)

        result = eval(repr(dct), {
            'dct': dct,
            'InsensitiveDict': util.InsensitiveDict,
            })
        self.assertEqual(result, dct)

        keys=['Foo', 'fnz', 1]
        for x in keys:
            self.assertIn(x, dct.keys())
            self.assertIn((x, dct[x]), dct.items())
        self.assertEqual(len(keys), len(dct))
        del dct[1]
        del dct['foo']
        self.assertEqual(dct.keys(), ['fnz'])


    def test_noPreserve(self):
        """
        L{util.InsensitiveDict} does not preserves the case of keys if
        constructed with C{preserve=False}.
        """
        dct = util.InsensitiveDict({'Foo':'bar', 1:2, 'fnz':{1:2}}, preserve=0)
        keys=['foo', 'fnz', 1]
        for x in keys:
            self.assertIn(x, dct.keys())
            self.assertIn((x, dct[x]), dct.items())
        self.assertEqual(len(keys), len(dct))
        del dct[1]
        del dct['foo']
        self.assertEqual(dct.keys(), ['fnz'])


    def test_unicode(self):
        """
        Unicode keys are case insensitive.
        """
        d = util.InsensitiveDict(preserve=False)
        d[u"Foo"] = 1
        self.assertEqual(d[u"FOO"], 1)
        self.assertEqual(d.keys(), [u"foo"])


    def test_bytes(self):
        """
        Bytes keys are case insensitive.
        """
        d = util.InsensitiveDict(preserve=False)
        d[b"Foo"] = 1
        self.assertEqual(d[b"FOO"], 1)
        self.assertEqual(d.keys(), [b"foo"])



class PasswordTestingProcessProtocol(ProcessProtocol):
    """
    Write the string C{"secret\n"} to a subprocess and then collect all of
    its output and fire a Deferred with it when the process ends.
    """
    def connectionMade(self):
        self.output = []
        self.transport.write(b'secret\n')

    def childDataReceived(self, fd, output):
        self.output.append((fd, output))

    def processEnded(self, reason):
        self.finished.callback((reason, self.output))


class GetPasswordTests(unittest.TestCase):
    if not IReactorProcess.providedBy(reactor):
        skip = "Process support required to test getPassword"

    def test_stdin(self):
        """
        Making sure getPassword accepts a password from standard input by
        running a child process which uses getPassword to read in a string
        which it then writes it out again.  Write a string to the child
        process and then read one and make sure it is the right string.
        """
        p = PasswordTestingProcessProtocol()
        p.finished = Deferred()
        reactor.spawnProcess(
            p, pyExe,
            [pyExe,
             b'-c',
             (b'import sys\n'
              b'from twisted.python.util import getPassword\n'
              b'sys.stdout.write(getPassword())\n'
              b'sys.stdout.flush()\n')],
            env={b'PYTHONPATH': os.pathsep.join(sys.path).encode("utf8")})

        def processFinished(result):
            (reason, output) = result
            reason.trap(ProcessDone)
            self.assertIn((1, b'secret'), output)

        return p.finished.addCallback(processFinished)



class SearchUpwardsTests(unittest.TestCase):
    def testSearchupwards(self):
        os.makedirs('searchupwards/a/b/c')
        open('searchupwards/foo.txt', 'w').close()
        open('searchupwards/a/foo.txt', 'w').close()
        open('searchupwards/a/b/c/foo.txt', 'w').close()
        os.mkdir('searchupwards/bar')
        os.mkdir('searchupwards/bam')
        os.mkdir('searchupwards/a/bar')
        os.mkdir('searchupwards/a/b/bam')
        actual=util.searchupwards('searchupwards/a/b/c',
                                  files=['foo.txt'],
                                  dirs=['bar', 'bam'])
        expected=os.path.abspath('searchupwards') + os.sep
        self.assertEqual(actual, expected)
        shutil.rmtree('searchupwards')
        actual=util.searchupwards('searchupwards/a/b/c',
                                  files=['foo.txt'],
                                  dirs=['bar', 'bam'])
        expected=None
        self.assertEqual(actual, expected)



class IntervalDifferentialTests(unittest.TestCase):
    def testDefault(self):
        d = iter(util.IntervalDifferential([], 10))
        for i in range(100):
            self.assertEqual(next(d), (10, None))

    def testSingle(self):
        d = iter(util.IntervalDifferential([5], 10))
        for i in range(100):
            self.assertEqual(next(d), (5, 0))

    def testPair(self):
        d = iter(util.IntervalDifferential([5, 7], 10))
        for i in range(100):
            self.assertEqual(next(d), (5, 0))
            self.assertEqual(next(d), (2, 1))
            self.assertEqual(next(d), (3, 0))
            self.assertEqual(next(d), (4, 1))
            self.assertEqual(next(d), (1, 0))
            self.assertEqual(next(d), (5, 0))
            self.assertEqual(next(d), (1, 1))
            self.assertEqual(next(d), (4, 0))
            self.assertEqual(next(d), (3, 1))
            self.assertEqual(next(d), (2, 0))
            self.assertEqual(next(d), (5, 0))
            self.assertEqual(next(d), (0, 1))

    def testTriple(self):
        d = iter(util.IntervalDifferential([2, 4, 5], 10))
        for i in range(100):
            self.assertEqual(next(d), (2, 0))
            self.assertEqual(next(d), (2, 0))
            self.assertEqual(next(d), (0, 1))
            self.assertEqual(next(d), (1, 2))
            self.assertEqual(next(d), (1, 0))
            self.assertEqual(next(d), (2, 0))
            self.assertEqual(next(d), (0, 1))
            self.assertEqual(next(d), (2, 0))
            self.assertEqual(next(d), (0, 2))
            self.assertEqual(next(d), (2, 0))
            self.assertEqual(next(d), (0, 1))
            self.assertEqual(next(d), (2, 0))
            self.assertEqual(next(d), (1, 2))
            self.assertEqual(next(d), (1, 0))
            self.assertEqual(next(d), (0, 1))
            self.assertEqual(next(d), (2, 0))
            self.assertEqual(next(d), (2, 0))
            self.assertEqual(next(d), (0, 1))
            self.assertEqual(next(d), (0, 2))

    def testInsert(self):
        d = iter(util.IntervalDifferential([], 10))
        self.assertEqual(next(d), (10, None))
        d.addInterval(3)
        self.assertEqual(next(d), (3, 0))
        self.assertEqual(next(d), (3, 0))
        d.addInterval(6)
        self.assertEqual(next(d), (3, 0))
        self.assertEqual(next(d), (3, 0))
        self.assertEqual(next(d), (0, 1))
        self.assertEqual(next(d), (3, 0))
        self.assertEqual(next(d), (3, 0))
        self.assertEqual(next(d), (0, 1))

    def testRemove(self):
        d = iter(util.IntervalDifferential([3, 5], 10))
        self.assertEqual(next(d), (3, 0))
        self.assertEqual(next(d), (2, 1))
        self.assertEqual(next(d), (1, 0))
        d.removeInterval(3)
        self.assertEqual(next(d), (4, 0))
        self.assertEqual(next(d), (5, 0))
        d.removeInterval(5)
        self.assertEqual(next(d), (10, None))
        self.assertRaises(ValueError, d.removeInterval, 10)



class Record(util.FancyEqMixin):
    """
    Trivial user of L{FancyEqMixin} used by tests.
    """
    compareAttributes = ('a', 'b')

    def __init__(self, a, b):
        self.a = a
        self.b = b



class DifferentRecord(util.FancyEqMixin):
    """
    Trivial user of L{FancyEqMixin} which is not related to L{Record}.
    """
    compareAttributes = ('a', 'b')

    def __init__(self, a, b):
        self.a = a
        self.b = b



class DerivedRecord(Record):
    """
    A class with an inheritance relationship to L{Record}.
    """



class EqualToEverything(object):
    """
    A class the instances of which consider themselves equal to everything.
    """
    def __eq__(self, other):
        return True


    def __ne__(self, other):
        return False



class EqualToNothing(object):
    """
    A class the instances of which consider themselves equal to nothing.
    """
    def __eq__(self, other):
        return False


    def __ne__(self, other):
        return True



class EqualityTests(unittest.TestCase):
    """
    Tests for L{FancyEqMixin}.
    """
    def test_identity(self):
        """
        Instances of a class which mixes in L{FancyEqMixin} but which
        defines no comparison attributes compare by identity.
        """
        class Empty(util.FancyEqMixin):
            pass

        self.assertFalse(Empty() == Empty())
        self.assertTrue(Empty() != Empty())
        empty = Empty()
        self.assertTrue(empty == empty)
        self.assertFalse(empty != empty)


    def test_equality(self):
        """
        Instances of a class which mixes in L{FancyEqMixin} should compare
        equal if all of their attributes compare equal.  They should not
        compare equal if any of their attributes do not compare equal.
        """
        self.assertTrue(Record(1, 2) == Record(1, 2))
        self.assertFalse(Record(1, 2) == Record(1, 3))
        self.assertFalse(Record(1, 2) == Record(2, 2))
        self.assertFalse(Record(1, 2) == Record(3, 4))


    def test_unequality(self):
        """
        Inequality between instances of a particular L{record} should be
        defined as the negation of equality.
        """
        self.assertFalse(Record(1, 2) != Record(1, 2))
        self.assertTrue(Record(1, 2) != Record(1, 3))
        self.assertTrue(Record(1, 2) != Record(2, 2))
        self.assertTrue(Record(1, 2) != Record(3, 4))


    def test_differentClassesEquality(self):
        """
        Instances of different classes which mix in L{FancyEqMixin} should not
        compare equal.
        """
        self.assertFalse(Record(1, 2) == DifferentRecord(1, 2))


    def test_differentClassesInequality(self):
        """
        Instances of different classes which mix in L{FancyEqMixin} should
        compare unequal.
        """
        self.assertTrue(Record(1, 2) != DifferentRecord(1, 2))


    def test_inheritedClassesEquality(self):
        """
        An instance of a class which derives from a class which mixes in
        L{FancyEqMixin} should compare equal to an instance of the base class
        if and only if all of their attributes compare equal.
        """
        self.assertTrue(Record(1, 2) == DerivedRecord(1, 2))
        self.assertFalse(Record(1, 2) == DerivedRecord(1, 3))
        self.assertFalse(Record(1, 2) == DerivedRecord(2, 2))
        self.assertFalse(Record(1, 2) == DerivedRecord(3, 4))


    def test_inheritedClassesInequality(self):
        """
        An instance of a class which derives from a class which mixes in
        L{FancyEqMixin} should compare unequal to an instance of the base
        class if any of their attributes compare unequal.
        """
        self.assertFalse(Record(1, 2) != DerivedRecord(1, 2))
        self.assertTrue(Record(1, 2) != DerivedRecord(1, 3))
        self.assertTrue(Record(1, 2) != DerivedRecord(2, 2))
        self.assertTrue(Record(1, 2) != DerivedRecord(3, 4))


    def test_rightHandArgumentImplementsEquality(self):
        """
        The right-hand argument to the equality operator is given a chance
        to determine the result of the operation if it is of a type
        unrelated to the L{FancyEqMixin}-based instance on the left-hand
        side.
        """
        self.assertTrue(Record(1, 2) == EqualToEverything())
        self.assertFalse(Record(1, 2) == EqualToNothing())


    def test_rightHandArgumentImplementsUnequality(self):
        """
        The right-hand argument to the non-equality operator is given a
        chance to determine the result of the operation if it is of a type
        unrelated to the L{FancyEqMixin}-based instance on the left-hand
        side.
        """
        self.assertFalse(Record(1, 2) != EqualToEverything())
        self.assertTrue(Record(1, 2) != EqualToNothing())



class RunAsEffectiveUserTests(unittest.TestCase):
    """
    Test for the L{util.runAsEffectiveUser} function.
    """

    if getattr(os, "geteuid", None) is None:
        skip = "geteuid/seteuid not available"

    def setUp(self):
        self.mockos = MockOS()
        self.patch(os, "geteuid", self.mockos.geteuid)
        self.patch(os, "getegid", self.mockos.getegid)
        self.patch(os, "seteuid", self.mockos.seteuid)
        self.patch(os, "setegid", self.mockos.setegid)


    def _securedFunction(self, startUID, startGID, wantUID, wantGID):
        """
        Check if wanted UID/GID matched start or saved ones.
        """
        self.assertTrue(wantUID == startUID or
                        wantUID == self.mockos.seteuidCalls[-1])
        self.assertTrue(wantGID == startGID or
                        wantGID == self.mockos.setegidCalls[-1])


    def test_forwardResult(self):
        """
        L{util.runAsEffectiveUser} forwards the result obtained by calling the
        given function
        """
        result = util.runAsEffectiveUser(0, 0, lambda: 1)
        self.assertEqual(result, 1)


    def test_takeParameters(self):
        """
        L{util.runAsEffectiveUser} pass the given parameters to the given
        function.
        """
        result = util.runAsEffectiveUser(0, 0, lambda x: 2*x, 3)
        self.assertEqual(result, 6)


    def test_takesKeyworkArguments(self):
        """
        L{util.runAsEffectiveUser} pass the keyword parameters to the given
        function.
        """
        result = util.runAsEffectiveUser(0, 0, lambda x, y=1, z=1: x*y*z, 2, z=3)
        self.assertEqual(result, 6)


    def _testUIDGIDSwitch(self, startUID, startGID, wantUID, wantGID,
                          expectedUIDSwitches, expectedGIDSwitches):
        """
        Helper method checking the calls to C{os.seteuid} and C{os.setegid}
        made by L{util.runAsEffectiveUser}, when switching from startUID to
        wantUID and from startGID to wantGID.
        """
        self.mockos.euid = startUID
        self.mockos.egid = startGID
        util.runAsEffectiveUser(
            wantUID, wantGID,
            self._securedFunction, startUID, startGID, wantUID, wantGID)
        self.assertEqual(self.mockos.seteuidCalls, expectedUIDSwitches)
        self.assertEqual(self.mockos.setegidCalls, expectedGIDSwitches)
        self.mockos.seteuidCalls = []
        self.mockos.setegidCalls = []


    def test_root(self):
        """
        Check UID/GID switches when current effective UID is root.
        """
        self._testUIDGIDSwitch(0, 0, 0, 0, [], [])
        self._testUIDGIDSwitch(0, 0, 1, 0, [1, 0], [])
        self._testUIDGIDSwitch(0, 0, 0, 1, [], [1, 0])
        self._testUIDGIDSwitch(0, 0, 1, 1, [1, 0], [1, 0])


    def test_UID(self):
        """
        Check UID/GID switches when current effective UID is non-root.
        """
        self._testUIDGIDSwitch(1, 0, 0, 0, [0, 1], [])
        self._testUIDGIDSwitch(1, 0, 1, 0, [], [])
        self._testUIDGIDSwitch(1, 0, 1, 1, [0, 1, 0, 1], [1, 0])
        self._testUIDGIDSwitch(1, 0, 2, 1, [0, 2, 0, 1], [1, 0])


    def test_GID(self):
        """
        Check UID/GID switches when current effective GID is non-root.
        """
        self._testUIDGIDSwitch(0, 1, 0, 0, [], [0, 1])
        self._testUIDGIDSwitch(0, 1, 0, 1, [], [])
        self._testUIDGIDSwitch(0, 1, 1, 1, [1, 0], [])
        self._testUIDGIDSwitch(0, 1, 1, 2, [1, 0], [2, 1])


    def test_UIDGID(self):
        """
        Check UID/GID switches when current effective UID/GID is non-root.
        """
        self._testUIDGIDSwitch(1, 1, 0, 0, [0, 1], [0, 1])
        self._testUIDGIDSwitch(1, 1, 0, 1, [0, 1], [])
        self._testUIDGIDSwitch(1, 1, 1, 0, [0, 1, 0, 1], [0, 1])
        self._testUIDGIDSwitch(1, 1, 1, 1, [], [])
        self._testUIDGIDSwitch(1, 1, 2, 1, [0, 2, 0, 1], [])
        self._testUIDGIDSwitch(1, 1, 1, 2, [0, 1, 0, 1], [2, 1])
        self._testUIDGIDSwitch(1, 1, 2, 2, [0, 2, 0, 1], [2, 1])



class InitGroupsTests(unittest.TestCase):
    """
    Tests for L{util.initgroups}.
    """
    def setUp(self):
        self.addCleanup(setattr, util, "_initgroups", util._initgroups)
        self.addCleanup(setattr, util, "setgroups", util.setgroups)


    def test_initgroupsInStdlib(self):
        """
        Calling L{util.initgroups} will call the underlying stdlib
        implmentation.
        """
        calls = []
        util._initgroups = lambda x, y: calls.append((x, y))
        setgroupsCalls = []
        util.setgroups = setgroupsCalls.append

        util.initgroups(os.getuid(), 4)
        self.assertEqual(calls, [(pwd.getpwuid(os.getuid())[0], 4)])
        self.assertFalse(setgroupsCalls)


    if util._initgroups is None:
        test_initgroupsInStdlib.skip = ("stdlib support for initgroups is not "
                                        "available")



class DeprecationTests(unittest.TestCase):
    """
    Tests for deprecations in C{twisted.python.util}.
    """
    def test_getPluginDirs(self):
        """
        L{util.getPluginDirs} is deprecated.
        """
        util.getPluginDirs()
        currentWarnings = self.flushWarnings(offendingFunctions=[
            self.test_getPluginDirs])
        self.assertEqual(
            currentWarnings[0]['message'],
            "twisted.python.util.getPluginDirs is deprecated since Twisted "
            "12.2.")
        self.assertEqual(currentWarnings[0]['category'], DeprecationWarning)
        self.assertEqual(len(currentWarnings), 1)


    def test_addPluginDir(self):
        """
        L{util.addPluginDir} is deprecated.
        """
        util.addPluginDir()
        currentWarnings = self.flushWarnings(offendingFunctions=[
            self.test_addPluginDir])
        self.assertEqual(
            currentWarnings[0]['message'],
            "twisted.python.util.addPluginDir is deprecated since Twisted "
            "12.2.")
        self.assertEqual(currentWarnings[0]['category'], DeprecationWarning)
        self.assertEqual(len(currentWarnings), 1)
    test_addPluginDir.suppress = [
            SUPPRESS(category=DeprecationWarning,
                     message="twisted.python.util.getPluginDirs is deprecated")
            ]



class SuppressedWarningsTests(unittest.TestCase):
    """
    Tests for L{util.runWithWarningsSuppressed}.
    """
    runWithWarningsSuppressed = staticmethod(util.runWithWarningsSuppressed)

    def test_runWithWarningsSuppressedFiltered(self):
        """
        Warnings from the function called by C{runWithWarningsSuppressed} are
        suppressed if they match the passed in filter.
        """
        filters = [(("ignore", ".*foo.*"), {}),
                   (("ignore", ".*bar.*"), {})]
        self.runWithWarningsSuppressed(filters, warnings.warn, "ignore foo")
        self.runWithWarningsSuppressed(filters, warnings.warn, "ignore bar")
        self.assertEqual([], self.flushWarnings())


    def test_runWithWarningsSuppressedUnfiltered(self):
        """
        Warnings from the function called by C{runWithWarningsSuppressed} are
        not suppressed if they do not match the passed in filter.
        """
        filters = [(("ignore", ".*foo.*"), {}),
                   (("ignore", ".*bar.*"), {})]
        self.runWithWarningsSuppressed(filters, warnings.warn, "don't ignore")
        self.assertEqual(
            ["don't ignore"], [w['message'] for w in self.flushWarnings()])


    def test_passThrough(self):
        """
        C{runWithWarningsSuppressed} returns the result of the function it
        called.
        """
        self.assertEqual(self.runWithWarningsSuppressed([], lambda: 4), 4)


    def test_noSideEffects(self):
        """
        Once C{runWithWarningsSuppressed} has returned, it no longer
        suppresses warnings.
        """
        filters = [(("ignore", ".*foo.*"), {}),
                   (("ignore", ".*bar.*"), {})]
        self.runWithWarningsSuppressed(filters, lambda: None)
        warnings.warn("ignore foo")
        self.assertEqual(
            ["ignore foo"], [w['message'] for w in self.flushWarnings()])



class FancyStrMixinTests(unittest.TestCase):
    """
    Tests for L{util.FancyStrMixin}.
    """

    def test_sequenceOfStrings(self):
        """
        If C{showAttributes} is set to a sequence of strings, C{__str__}
        renders using those by looking them up as attributes on the object.
        """
        class Foo(util.FancyStrMixin):
            showAttributes = ("first", "second")
            first = 1
            second = "hello"
        self.assertEqual(str(Foo()), "<Foo first=1 second='hello'>")


    def test_formatter(self):
        """
        If C{showAttributes} has an item that is a 2-tuple, C{__str__} renders
        the first item in the tuple as a key and the result of calling the
        second item with the value of the attribute named by the first item as
        the value.
        """
        class Foo(util.FancyStrMixin):
            showAttributes = (
                "first",
                ("second", lambda value: repr(value[::-1])))
            first = "hello"
            second = "world"
        self.assertEqual("<Foo first='hello' second='dlrow'>", str(Foo()))


    def test_override(self):
        """
        If C{showAttributes} has an item that is a 3-tuple, C{__str__} renders
        the second item in the tuple as a key, and the contents of the
        attribute named in the first item are rendered as the value. The value
        is formatted using the third item in the tuple.
        """
        class Foo(util.FancyStrMixin):
            showAttributes = ("first", ("second", "2nd", "%.1f"))
            first = 1
            second = 2.111
        self.assertEqual(str(Foo()), "<Foo first=1 2nd=2.1>")


    def test_fancybasename(self):
        """
        If C{fancybasename} is present, C{__str__} uses it instead of the class name.
        """
        class Foo(util.FancyStrMixin):
            fancybasename = "Bar"
        self.assertEqual(str(Foo()), "<Bar>")


    def test_repr(self):
        """
        C{__repr__} outputs the same content as C{__str__}.
        """
        class Foo(util.FancyStrMixin):
            showAttributes = ("first", "second")
            first = 1
            second = "hello"
        obj = Foo()
        self.assertEqual(str(obj), repr(obj))



class PadToTests(unittest.TestCase):
    """
    Tests for L{util.padTo}.
    """

    def test_default(self):
        """
        L{None} values can be added to a list to cause it to have a certain
        length.
        """
        padded = util.padTo(3, [])
        self.assertEqual([None] * 3, padded)


    def test_specificDefaultValue(self):
        """
        A specific value can be added to a list to cause it to have a certain
        length.
        """
        padded = util.padTo(4, [], "x")
        self.assertEqual(["x"] * 4, padded)


    def test_padNonEmptyList(self):
        """
        A list which already has some items has the padding value added after
        those items.
        """
        padded = util.padTo(3, [1, 2], "z")
        self.assertEqual([1, 2, "z"], padded)


    def test_padToSmallerSize(self):
        """
        L{util.padTo} can't pad a list if the size requested is smaller than
        the size of the list to pad.
        """
        self.assertRaises(ValueError, util.padTo, 1, [1, 2])


    def test_alreadyPadded(self):
        """
        If the list is already the length indicated by the padding argument
        then a list with the same value is returned.
        """
        items = [1, 2]
        padded = util.padTo(len(items), items)
        self.assertEqual(items, padded)


    def test_alreadyPaddedCopies(self):
        """
        If the list is already the length indicated by the padding argument
        then the return value is a copy of the input.
        """
        items = [1, 2]
        padded = util.padTo(len(items), items)
        self.assertIsNot(padded, items)


    def test_makeCopy(self):
        """
        L{util.padTo} doesn't modify the input list but makes a copy.
        """
        items = []
        util.padTo(4, items)
        self.assertEqual([], items)



class ReplaceIfTests(unittest.TestCase):
    """
    Tests for L{util._replaceIf}.
    """

    def test_replacesIfTrue(self):
        """
        L{util._replaceIf} swaps out the body of a function if the conditional
        is C{True}.
        """
        @util._replaceIf(True, lambda: "hi")
        def test():
            return "bye"

        self.assertEqual(test(), "hi")
        self.assertEqual(test.__name__, "test")
        self.assertEqual(test.__module__, "twisted.python.test.test_util")


    def test_keepsIfFalse(self):
        """
        L{util._replaceIf} keeps the original body of the function if the
        conditional is C{False}.
        """
        @util._replaceIf(False, lambda: "hi")
        def test():
            return "bye"

        self.assertEqual(test(), "bye")


    def test_multipleReplace(self):
        """
        In the case that multiple conditions are true, the first one
        (to the reader) is chosen by L{util._replaceIf}
        """
        @util._replaceIf(True, lambda: "hi")
        @util._replaceIf(False, lambda: "bar")
        @util._replaceIf(True, lambda: "baz")
        def test():
            return "bye"

        self.assertEqual(test(), "hi")


    def test_boolsOnly(self):
        """
        L{util._replaceIf}'s condition argument only accepts bools.
        """
        with self.assertRaises(ValueError) as e:

            @util._replaceIf("hi", "there")
            def test():
                """
                Some test function.
                """

        self.assertEqual(e.exception.args[0],
                         ("condition argument to _replaceIf requires a bool, "
                          "not 'hi'"))
