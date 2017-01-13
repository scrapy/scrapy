# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for Trial's interaction with the Python warning system.
"""

from __future__ import division, absolute_import

import sys, warnings

from unittest import TestResult

from twisted.python.compat import NativeStringIO as StringIO
from twisted.python.filepath import FilePath
from twisted.trial.unittest import SynchronousTestCase
from twisted.trial._synctest import _collectWarnings, _setWarningRegistryToNone


class Mask(object):
    """
    Hide a test case definition from trial's automatic discovery mechanism.
    """
    class MockTests(SynchronousTestCase):
        """
        A test case which is used by L{FlushWarningsTests} to verify behavior
        which cannot be verified by code inside a single test method.
        """
        message = "some warning text"
        category = UserWarning

        def test_unflushed(self):
            """
            Generate a warning and don't flush it.
            """
            warnings.warn(self.message, self.category)


        def test_flushed(self):
            """
            Generate a warning and flush it.
            """
            warnings.warn(self.message, self.category)
            self.assertEqual(len(self.flushWarnings()), 1)



class FlushWarningsTests(SynchronousTestCase):
    """
    Tests for C{flushWarnings}, an API for examining the warnings
    emitted so far in a test.
    """

    def assertDictSubset(self, set, subset):
        """
        Assert that all the keys present in C{subset} are also present in
        C{set} and that the corresponding values are equal.
        """
        for k, v in subset.items():
            self.assertEqual(set[k], v)


    def assertDictSubsets(self, sets, subsets):
        """
        For each pair of corresponding elements in C{sets} and C{subsets},
        assert that the element from C{subsets} is a subset of the element from
        C{sets}.
        """
        self.assertEqual(len(sets), len(subsets))
        for a, b in zip(sets, subsets):
            self.assertDictSubset(a, b)


    def test_none(self):
        """
        If no warnings are emitted by a test, C{flushWarnings} returns an empty
        list.
        """
        self.assertEqual(self.flushWarnings(), [])


    def test_several(self):
        """
        If several warnings are emitted by a test, C{flushWarnings} returns a
        list containing all of them.
        """
        firstMessage = "first warning message"
        firstCategory = UserWarning
        warnings.warn(message=firstMessage, category=firstCategory)

        secondMessage = "second warning message"
        secondCategory = RuntimeWarning
        warnings.warn(message=secondMessage, category=secondCategory)

        self.assertDictSubsets(
            self.flushWarnings(),
            [{'category': firstCategory, 'message': firstMessage},
             {'category': secondCategory, 'message': secondMessage}])


    def test_repeated(self):
        """
        The same warning triggered twice from the same place is included twice
        in the list returned by C{flushWarnings}.
        """
        message = "the message"
        category = RuntimeWarning
        for i in range(2):
            warnings.warn(message=message, category=category)

        self.assertDictSubsets(
            self.flushWarnings(),
            [{'category': category, 'message': message}] * 2)


    def test_cleared(self):
        """
        After a particular warning event has been returned by C{flushWarnings},
        it is not returned by subsequent calls.
        """
        message = "the message"
        category = RuntimeWarning
        warnings.warn(message=message, category=category)
        self.assertDictSubsets(
            self.flushWarnings(),
            [{'category': category, 'message': message}])
        self.assertEqual(self.flushWarnings(), [])


    def test_unflushed(self):
        """
        Any warnings emitted by a test which are not flushed are emitted to the
        Python warning system.
        """
        result = TestResult()
        case = Mask.MockTests('test_unflushed')
        case.run(result)
        warningsShown = self.flushWarnings([Mask.MockTests.test_unflushed])
        self.assertEqual(warningsShown[0]['message'], 'some warning text')
        self.assertIdentical(warningsShown[0]['category'], UserWarning)

        where = type(case).test_unflushed.__code__
        filename = where.co_filename
        # If someone edits MockTests.test_unflushed, the value added to
        # firstlineno might need to change.
        lineno = where.co_firstlineno + 4

        self.assertEqual(warningsShown[0]['filename'], filename)
        self.assertEqual(warningsShown[0]['lineno'], lineno)

        self.assertEqual(len(warningsShown), 1)


    def test_flushed(self):
        """
        Any warnings emitted by a test which are flushed are not emitted to the
        Python warning system.
        """
        result = TestResult()
        case = Mask.MockTests('test_flushed')
        output = StringIO()
        monkey = self.patch(sys, 'stdout', output)
        case.run(result)
        monkey.restore()
        self.assertEqual(output.getvalue(), "")


    def test_warningsConfiguredAsErrors(self):
        """
        If a warnings filter has been installed which turns warnings into
        exceptions, tests have an error added to the reporter for them for each
        unflushed warning.
        """
        class CustomWarning(Warning):
            pass

        result = TestResult()
        case = Mask.MockTests('test_unflushed')
        case.category = CustomWarning

        originalWarnings = warnings.filters[:]
        try:
            warnings.simplefilter('error')
            case.run(result)
            self.assertEqual(len(result.errors), 1)
            self.assertIdentical(result.errors[0][0], case)
            self.assertTrue(
                # Different python versions differ in whether they report the
                # fully qualified class name or just the class name.
                result.errors[0][1].splitlines()[-1].endswith(
                    "CustomWarning: some warning text"))
        finally:
            warnings.filters[:] = originalWarnings


    def test_flushedWarningsConfiguredAsErrors(self):
        """
        If a warnings filter has been installed which turns warnings into
        exceptions, tests which emit those warnings but flush them do not have
        an error added to the reporter.
        """
        class CustomWarning(Warning):
            pass

        result = TestResult()
        case = Mask.MockTests('test_flushed')
        case.category = CustomWarning

        originalWarnings = warnings.filters[:]
        try:
            warnings.simplefilter('error')
            case.run(result)
            self.assertEqual(result.errors, [])
        finally:
            warnings.filters[:] = originalWarnings


    def test_multipleFlushes(self):
        """
        Any warnings emitted after a call to C{flushWarnings} can be flushed by
        another call to C{flushWarnings}.
        """
        warnings.warn("first message")
        self.assertEqual(len(self.flushWarnings()), 1)
        warnings.warn("second message")
        self.assertEqual(len(self.flushWarnings()), 1)


    def test_filterOnOffendingFunction(self):
        """
        The list returned by C{flushWarnings} includes only those
        warnings which refer to the source of the function passed as the value
        for C{offendingFunction}, if a value is passed for that parameter.
        """
        firstMessage = "first warning text"
        firstCategory = UserWarning
        def one():
            warnings.warn(firstMessage, firstCategory, stacklevel=1)

        secondMessage = "some text"
        secondCategory = RuntimeWarning
        def two():
            warnings.warn(secondMessage, secondCategory, stacklevel=1)

        one()
        two()

        self.assertDictSubsets(
            self.flushWarnings(offendingFunctions=[one]),
            [{'category': firstCategory, 'message': firstMessage}])
        self.assertDictSubsets(
            self.flushWarnings(offendingFunctions=[two]),
            [{'category': secondCategory, 'message': secondMessage}])


    def test_functionBoundaries(self):
        """
        Verify that warnings emitted at the very edges of a function are still
        determined to be emitted from that function.
        """
        def warner():
            warnings.warn("first line warning")
            warnings.warn("internal line warning")
            warnings.warn("last line warning")

        warner()
        self.assertEqual(
            len(self.flushWarnings(offendingFunctions=[warner])), 3)


    def test_invalidFilter(self):
        """
        If an object which is neither a function nor a method is included in the
        C{offendingFunctions} list, C{flushWarnings} raises L{ValueError}.  Such
        a call flushes no warnings.
        """
        warnings.warn("oh no")
        self.assertRaises(ValueError, self.flushWarnings, [None])
        self.assertEqual(len(self.flushWarnings()), 1)


    def test_missingSource(self):
        """
        Warnings emitted by a function the source code of which is not
        available can still be flushed.
        """
        package = FilePath(self.mktemp().encode('utf-8')).child(b'twisted_private_helper')
        package.makedirs()
        package.child(b'__init__.py').setContent(b'')
        package.child(b'missingsourcefile.py').setContent(b'''
import warnings
def foo():
    warnings.warn("oh no")
''')
        pathEntry = package.parent().path.decode('utf-8')
        sys.path.insert(0, pathEntry)
        self.addCleanup(sys.path.remove, pathEntry)
        from twisted_private_helper import missingsourcefile
        self.addCleanup(sys.modules.pop, 'twisted_private_helper')
        self.addCleanup(sys.modules.pop, missingsourcefile.__name__)
        package.child(b'missingsourcefile.py').remove()

        missingsourcefile.foo()
        self.assertEqual(len(self.flushWarnings([missingsourcefile.foo])), 1)


    def test_renamedSource(self):
        """
        Warnings emitted by a function defined in a file which has been renamed
        since it was initially compiled can still be flushed.

        This is testing the code which specifically supports working around the
        unfortunate behavior of CPython to write a .py source file name into
        the .pyc files it generates and then trust that it is correct in
        various places.  If source files are renamed, .pyc files may not be
        regenerated, but they will contain incorrect filenames.
        """
        package = FilePath(self.mktemp().encode('utf-8')).child(b'twisted_private_helper')
        package.makedirs()
        package.child(b'__init__.py').setContent(b'')
        package.child(b'module.py').setContent(b'''
import warnings
def foo():
    warnings.warn("oh no")
''')
        pathEntry = package.parent().path.decode('utf-8')
        sys.path.insert(0, pathEntry)
        self.addCleanup(sys.path.remove, pathEntry)

        # Import it to cause pycs to be generated
        from twisted_private_helper import module

        # Clean up the state resulting from that import; we're not going to use
        # this module, so it should go away.
        del sys.modules['twisted_private_helper']
        del sys.modules[module.__name__]

        # Some Python versions have extra state related to the just
        # imported/renamed package.  Clean it up too.  See also
        # http://bugs.python.org/issue15912
        try:
            from importlib import invalidate_caches
        except ImportError:
            pass
        else:
            invalidate_caches()

        # Rename the source directory
        package.moveTo(package.sibling(b'twisted_renamed_helper'))

        # Import the newly renamed version
        from twisted_renamed_helper import module
        self.addCleanup(sys.modules.pop, 'twisted_renamed_helper')
        self.addCleanup(sys.modules.pop, module.__name__)

        # Generate the warning
        module.foo()

        # Flush it
        self.assertEqual(len(self.flushWarnings([module.foo])), 1)



class FakeWarning(Warning):
    pass



class CollectWarningsTests(SynchronousTestCase):
    """
    Tests for L{_collectWarnings}.
    """
    def test_callsObserver(self):
        """
        L{_collectWarnings} calls the observer with each emitted warning.
        """
        firstMessage = "dummy calls observer warning"
        secondMessage = firstMessage[::-1]
        events = []
        def f():
            events.append('call')
            warnings.warn(firstMessage)
            warnings.warn(secondMessage)
            events.append('returning')

        _collectWarnings(events.append, f)

        self.assertEqual(events[0], 'call')
        self.assertEqual(events[1].message, firstMessage)
        self.assertEqual(events[2].message, secondMessage)
        self.assertEqual(events[3], 'returning')
        self.assertEqual(len(events), 4)


    def test_suppresses(self):
        """
        Any warnings emitted by a call to a function passed to
        L{_collectWarnings} are not actually emitted to the warning system.
        """
        output = StringIO()
        self.patch(sys, 'stdout', output)
        _collectWarnings(lambda x: None, warnings.warn, "text")
        self.assertEqual(output.getvalue(), "")


    def test_callsFunction(self):
        """
        L{_collectWarnings} returns the result of calling the callable passed to
        it with the parameters given.
        """
        arguments = []
        value = object()

        def f(*args, **kwargs):
            arguments.append((args, kwargs))
            return value

        result = _collectWarnings(lambda x: None, f, 1, 'a', b=2, c='d')
        self.assertEqual(arguments, [((1, 'a'), {'b': 2, 'c': 'd'})])
        self.assertIdentical(result, value)


    def test_duplicateWarningCollected(self):
        """
        Subsequent emissions of a warning from a particular source site can be
        collected by L{_collectWarnings}.  In particular, the per-module
        emitted-warning cache should be bypassed (I{__warningregistry__}).
        """
        # Make sure the worst case is tested: if __warningregistry__ isn't in a
        # module's globals, then the warning system will add it and start using
        # it to avoid emitting duplicate warnings.  Delete __warningregistry__
        # to ensure that even modules which are first imported as a test is
        # running still interact properly with the warning system.
        global __warningregistry__
        del __warningregistry__

        def f():
            warnings.warn("foo")
        warnings.simplefilter('default')
        f()
        events = []
        _collectWarnings(events.append, f)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].message, "foo")
        self.assertEqual(len(self.flushWarnings()), 1)


    def test_immutableObject(self):
        """
        L{_collectWarnings}'s behavior is not altered by the presence of an
        object which cannot have attributes set on it as a value in
        C{sys.modules}.
        """
        key = object()
        sys.modules[key] = key
        self.addCleanup(sys.modules.pop, key)
        self.test_duplicateWarningCollected()


    def test_setWarningRegistryChangeWhileIterating(self):
        """
        If the dictionary passed to L{_setWarningRegistryToNone} changes size
        partway through the process, C{_setWarningRegistryToNone} continues to
        set C{__warningregistry__} to L{None} on the rest of the values anyway.


        This might be caused by C{sys.modules} containing something that's not
        really a module and imports things on setattr.  py.test does this, as
        does L{twisted.python.deprecate.deprecatedModuleAttribute}.
        """
        d = {}

        class A(object):
            def __init__(self, key):
                self.__dict__['_key'] = key

            def __setattr__(self, value, item):
                d[self._key] = None

        key1 = object()
        key2 = object()
        d[key1] = A(key2)

        key3 = object()
        key4 = object()
        d[key3] = A(key4)

        _setWarningRegistryToNone(d)

        # If both key2 and key4 were added, then both A instanced were
        # processed.
        self.assertEqual(set([key1, key2, key3, key4]), set(d.keys()))
