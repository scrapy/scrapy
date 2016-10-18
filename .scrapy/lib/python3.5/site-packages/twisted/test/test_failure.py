# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for the L{twisted.python.failure} module.
"""

from __future__ import division, absolute_import

import re
import sys
import traceback
import pdb
import linecache

from twisted.python.compat import NativeStringIO, _PY3
from twisted.python import reflect
from twisted.python import failure

from twisted.trial.unittest import SynchronousTestCase


try:
    from twisted.test import raiser
except ImportError:
    raiser = None



def getDivisionFailure(*args, **kwargs):
    """
    Make a C{Failure} of a divide-by-zero error.

    @param args: Any C{*args} are passed to Failure's constructor.
    @param kwargs: Any C{**kwargs} are passed to Failure's constructor.
    """
    try:
        1/0
    except:
        f = failure.Failure(*args, **kwargs)
    return f


class FailureTests(SynchronousTestCase):
    """
    Tests for L{failure.Failure}.
    """

    def test_failAndTrap(self):
        """
        Trapping a L{Failure}.
        """
        try:
            raise NotImplementedError('test')
        except:
            f = failure.Failure()
        error = f.trap(SystemExit, RuntimeError)
        self.assertEqual(error, RuntimeError)
        self.assertEqual(f.type, NotImplementedError)


    def test_trapRaisesCurrentFailure(self):
        """
        If the wrapped C{Exception} is not a subclass of one of the
        expected types, L{failure.Failure.trap} raises the current
        L{failure.Failure} ie C{self}.
        """
        exception = ValueError()
        try:
            raise exception
        except:
            f = failure.Failure()
        untrapped = self.assertRaises(failure.Failure, f.trap, OverflowError)
        self.assertIs(f, untrapped)


    if _PY3:
        test_trapRaisesCurrentFailure.skip = (
            "In Python3, Failure.trap raises the wrapped Exception "
            "instead of the original Failure instance.")


    def test_trapRaisesWrappedException(self):
        """
        If the wrapped C{Exception} is not a subclass of one of the
        expected types, L{failure.Failure.trap} raises the wrapped
        C{Exception}.
        """
        exception = ValueError()
        try:
            raise exception
        except:
            f = failure.Failure()

        untrapped = self.assertRaises(ValueError, f.trap, OverflowError)
        self.assertIs(exception, untrapped)


    if not _PY3:
        test_trapRaisesWrappedException.skip = (
            "In Python2, Failure.trap raises the current Failure instance "
            "instead of the wrapped Exception.")


    def test_failureValueFromFailure(self):
        """
        A L{failure.Failure} constructed from another
        L{failure.Failure} instance, has its C{value} property set to
        the value of that L{failure.Failure} instance.
        """
        exception = ValueError()
        f1 = failure.Failure(exception)
        f2 = failure.Failure(f1)
        self.assertIs(f2.value, exception)


    def test_failureValueFromFoundFailure(self):
        """
        A L{failure.Failure} constructed without a C{exc_value}
        argument, will search for an "original" C{Failure}, and if
        found, its value will be used as the value for the new
        C{Failure}.
        """
        exception = ValueError()
        f1 = failure.Failure(exception)
        try:
            f1.trap(OverflowError)
        except:
            f2 = failure.Failure()

        self.assertIs(f2.value, exception)


    def assertStartsWith(self, s, prefix):
        """
        Assert that C{s} starts with a particular C{prefix}.

        @param s: The input string.
        @type s: C{str}
        @param prefix: The string that C{s} should start with.
        @type prefix: C{str}
        """
        self.assertTrue(s.startswith(prefix),
                        '%r is not the start of %r' % (prefix, s))


    def assertEndsWith(self, s, suffix):
        """
        Assert that C{s} end with a particular C{suffix}.

        @param s: The input string.
        @type s: C{str}
        @param suffix: The string that C{s} should end with.
        @type suffix: C{str}
        """
        self.assertTrue(s.endswith(suffix),
                        '%r is not the end of %r' % (suffix, s))


    def assertTracebackFormat(self, tb, prefix, suffix):
        """
        Assert that the C{tb} traceback contains a particular C{prefix} and
        C{suffix}.

        @param tb: The traceback string.
        @type tb: C{str}
        @param prefix: The string that C{tb} should start with.
        @type prefix: C{str}
        @param suffix: The string that C{tb} should end with.
        @type suffix: C{str}
        """
        self.assertStartsWith(tb, prefix)
        self.assertEndsWith(tb, suffix)


    def assertDetailedTraceback(self, captureVars=False, cleanFailure=False):
        """
        Assert that L{printDetailedTraceback} produces and prints a detailed
        traceback.

        The detailed traceback consists of a header::

          *--- Failure #20 ---

        The body contains the stacktrace::

          /twisted/trial/_synctest.py:1180: _run(...)
          /twisted/python/util.py:1076: runWithWarningsSuppressed(...)
          --- <exception caught here> ---
          /twisted/test/test_failure.py:39: getDivisionFailure(...)

        If C{captureVars} is enabled the body also includes a list of
        globals and locals::

           [ Locals ]
             exampleLocalVar : 'xyz'
             ...
           ( Globals )
             ...

        Or when C{captureVars} is disabled::

           [Capture of Locals and Globals disabled (use captureVars=True)]

        When C{cleanFailure} is enabled references to other objects are removed
        and replaced with strings.

        And finally the footer with the L{Failure}'s value::

          exceptions.ZeroDivisionError: float division
          *--- End of Failure #20 ---

        @param captureVars: Enables L{Failure.captureVars}.
        @type captureVars: C{bool}
        @param cleanFailure: Enables L{Failure.cleanFailure}.
        @type cleanFailure: C{bool}
        """
        if captureVars:
            exampleLocalVar = 'xyz'
            # Silence the linter as this variable is checked via
            # the traceback.
            exampleLocalVar

        f = getDivisionFailure(captureVars=captureVars)
        out = NativeStringIO()
        if cleanFailure:
            f.cleanFailure()
        f.printDetailedTraceback(out)

        tb = out.getvalue()
        start = "*--- Failure #%d%s---\n" % (f.count,
            (f.pickled and ' (pickled) ') or ' ')
        end = "%s: %s\n*--- End of Failure #%s ---\n" % (reflect.qual(f.type),
            reflect.safe_str(f.value), f.count)
        self.assertTracebackFormat(tb, start, end)

        # Variables are printed on lines with 2 leading spaces.
        linesWithVars = [line for line in tb.splitlines()
                             if line.startswith('  ')]

        if captureVars:
            self.assertNotEqual([], linesWithVars)
            if cleanFailure:
                line = '  exampleLocalVar : "\'xyz\'"'
            else:
                line = "  exampleLocalVar : 'xyz'"
            self.assertIn(line, linesWithVars)
        else:
            self.assertEqual([], linesWithVars)
            self.assertIn(' [Capture of Locals and Globals disabled (use '
                'captureVars=True)]\n', tb)


    def assertBriefTraceback(self, captureVars=False):
        """
        Assert that L{printBriefTraceback} produces and prints a brief
        traceback.

        The brief traceback consists of a header::

          Traceback: <type 'exceptions.ZeroDivisionError'>: float division

        The body with the stacktrace::

          /twisted/trial/_synctest.py:1180:_run
          /twisted/python/util.py:1076:runWithWarningsSuppressed

        And the footer::

          --- <exception caught here> ---
          /twisted/test/test_failure.py:39:getDivisionFailure

        @param captureVars: Enables L{Failure.captureVars}.
        @type captureVars: C{bool}
        """
        if captureVars:
            exampleLocalVar = 'abcde'
            # Silence the linter as this variable is checked via
            # the traceback.
            exampleLocalVar

        f = getDivisionFailure()
        out = NativeStringIO()
        f.printBriefTraceback(out)
        tb = out.getvalue()
        stack = ''
        for method, filename, lineno, localVars, globalVars in f.frames:
            stack += '%s:%s:%s\n' % (filename, lineno, method)

        if _PY3:
            zde = "class 'ZeroDivisionError'"
        else:
            zde = "type 'exceptions.ZeroDivisionError'"

        self.assertTracebackFormat(tb,
            "Traceback: <%s>: " % (zde,),
            "%s\n%s" % (failure.EXCEPTION_CAUGHT_HERE, stack))

        if captureVars:
            self.assertIsNone(re.search('exampleLocalVar.*abcde', tb))


    def assertDefaultTraceback(self, captureVars=False):
        """
        Assert that L{printTraceback} produces and prints a default traceback.

        The default traceback consists of a header::

          Traceback (most recent call last):

        The body with traceback::

          File "/twisted/trial/_synctest.py", line 1180, in _run
             runWithWarningsSuppressed(suppress, method)

        And the footer::

          --- <exception caught here> ---
            File "twisted/test/test_failure.py", line 39, in getDivisionFailure
              1/0
            exceptions.ZeroDivisionError: float division

        @param captureVars: Enables L{Failure.captureVars}.
        @type captureVars: C{bool}
        """
        if captureVars:
            exampleLocalVar = 'xyzzy'
            # Silence the linter as this variable is checked via
            # the traceback.
            exampleLocalVar

        f = getDivisionFailure(captureVars=captureVars)
        out = NativeStringIO()
        f.printTraceback(out)
        tb = out.getvalue()
        stack = ''
        for method, filename, lineno, localVars, globalVars in f.frames:
            stack += '  File "%s", line %s, in %s\n' % (filename, lineno,
                                                        method)
            stack += '    %s\n' % (linecache.getline(
                                   filename, lineno).strip(),)

        self.assertTracebackFormat(tb,
            "Traceback (most recent call last):",
            "%s\n%s%s: %s\n" % (failure.EXCEPTION_CAUGHT_HERE, stack,
            reflect.qual(f.type), reflect.safe_str(f.value)))

        if captureVars:
            self.assertIsNone(re.search('exampleLocalVar.*xyzzy', tb))


    def test_printDetailedTraceback(self):
        """
        L{printDetailedTraceback} returns a detailed traceback including the
        L{Failure}'s count.
        """
        self.assertDetailedTraceback()


    def test_printBriefTraceback(self):
        """
        L{printBriefTraceback} returns a brief traceback.
        """
        self.assertBriefTraceback()


    def test_printTraceback(self):
        """
        L{printTraceback} returns a traceback.
        """
        self.assertDefaultTraceback()


    def test_printDetailedTracebackCapturedVars(self):
        """
        L{printDetailedTraceback} captures the locals and globals for its
        stack frames and adds them to the traceback, when called on a
        L{Failure} constructed with C{captureVars=True}.
        """
        self.assertDetailedTraceback(captureVars=True)


    def test_printBriefTracebackCapturedVars(self):
        """
        L{printBriefTraceback} returns a brief traceback when called on a
        L{Failure} constructed with C{captureVars=True}.

        Local variables on the stack can not be seen in the resulting
        traceback.
        """
        self.assertBriefTraceback(captureVars=True)


    def test_printTracebackCapturedVars(self):
        """
        L{printTraceback} returns a traceback when called on a L{Failure}
        constructed with C{captureVars=True}.

        Local variables on the stack can not be seen in the resulting
        traceback.
        """
        self.assertDefaultTraceback(captureVars=True)


    def test_printDetailedTracebackCapturedVarsCleaned(self):
        """
        C{printDetailedTraceback} includes information about local variables on
        the stack after C{cleanFailure} has been called.
        """
        self.assertDetailedTraceback(captureVars=True, cleanFailure=True)


    def test_invalidFormatFramesDetail(self):
        """
        L{failure.format_frames} raises a L{ValueError} if the supplied
        C{detail} level is unknown.
        """
        self.assertRaises(ValueError, failure.format_frames, None, None,
            detail='noisia')


    def test_ExplictPass(self):
        e = RuntimeError()
        f = failure.Failure(e)
        f.trap(RuntimeError)
        self.assertEqual(f.value, e)


    def _getInnermostFrameLine(self, f):
        try:
            f.raiseException()
        except ZeroDivisionError:
            tb = traceback.extract_tb(sys.exc_info()[2])
            return tb[-1][-1]
        else:
            raise Exception(
                "f.raiseException() didn't raise ZeroDivisionError!?")


    def test_RaiseExceptionWithTB(self):
        f = getDivisionFailure()
        innerline = self._getInnermostFrameLine(f)
        self.assertEqual(innerline, '1/0')


    def test_stringExceptionConstruction(self):
        """
        Constructing a C{Failure} with a string as its exception value raises
        a C{TypeError}, as this is no longer supported as of Python 2.6.
        """
        exc = self.assertRaises(TypeError, failure.Failure, "ono!")
        self.assertIn("Strings are not supported by Failure", str(exc))


    def test_ConstructionFails(self):
        """
        Creating a Failure with no arguments causes it to try to discover the
        current interpreter exception state.  If no such state exists, creating
        the Failure should raise a synchronous exception.
        """
        if sys.version_info < (3, 0):
            sys.exc_clear()
        self.assertRaises(failure.NoCurrentExceptionError, failure.Failure)


    def test_getTracebackObject(self):
        """
        If the C{Failure} has not been cleaned, then C{getTracebackObject}
        returns the traceback object that captured in its constructor.
        """
        f = getDivisionFailure()
        self.assertEqual(f.getTracebackObject(), f.tb)


    def test_getTracebackObjectFromCaptureVars(self):
        """
        C{captureVars=True} has no effect on the result of
        C{getTracebackObject}.
        """
        try:
            1/0
        except ZeroDivisionError:
            noVarsFailure = failure.Failure()
            varsFailure = failure.Failure(captureVars=True)
        self.assertEqual(noVarsFailure.getTracebackObject(), varsFailure.tb)


    def test_getTracebackObjectFromClean(self):
        """
        If the Failure has been cleaned, then C{getTracebackObject} returns an
        object that looks the same to L{traceback.extract_tb}.
        """
        f = getDivisionFailure()
        expected = traceback.extract_tb(f.getTracebackObject())
        f.cleanFailure()
        observed = traceback.extract_tb(f.getTracebackObject())
        self.assertIsNotNone(expected)
        self.assertEqual(expected, observed)


    def test_getTracebackObjectFromCaptureVarsAndClean(self):
        """
        If the Failure was created with captureVars, then C{getTracebackObject}
        returns an object that looks the same to L{traceback.extract_tb}.
        """
        f = getDivisionFailure(captureVars=True)
        expected = traceback.extract_tb(f.getTracebackObject())
        f.cleanFailure()
        observed = traceback.extract_tb(f.getTracebackObject())
        self.assertEqual(expected, observed)


    def test_getTracebackObjectWithoutTraceback(self):
        """
        L{failure.Failure}s need not be constructed with traceback objects. If
        a C{Failure} has no traceback information at all, C{getTracebackObject}
        just returns None.

        None is a good value, because traceback.extract_tb(None) -> [].
        """
        f = failure.Failure(Exception("some error"))
        self.assertIsNone(f.getTracebackObject())


    def test_tracebackFromExceptionInPython3(self):
        """
        If a L{failure.Failure} is constructed with an exception but no
        traceback in Python 3, the traceback will be extracted from the
        exception's C{__traceback__} attribute.
        """
        try:
            1/0
        except:
            klass, exception, tb = sys.exc_info()
        f = failure.Failure(exception)
        self.assertIs(f.tb, tb)


    def test_cleanFailureRemovesTracebackInPython3(self):
        """
        L{failure.Failure.cleanFailure} sets the C{__traceback__} attribute of
        the exception to L{None} in Python 3.
        """
        f = getDivisionFailure()
        self.assertIsNotNone(f.tb)
        self.assertIs(f.value.__traceback__, f.tb)
        f.cleanFailure()
        self.assertIsNone(f.value.__traceback__)

    if not _PY3:
        test_tracebackFromExceptionInPython3.skip = "Python 3 only."
        test_cleanFailureRemovesTracebackInPython3.skip = "Python 3 only."


    def test_repr(self):
        """
        The C{repr} of a L{failure.Failure} shows the type and string
        representation of the underlying exception.
        """
        f = getDivisionFailure()
        if _PY3:
            typeName = 'builtins.ZeroDivisionError'
        else:
            typeName = 'exceptions.ZeroDivisionError'
        self.assertEqual(
            repr(f),
            '<twisted.python.failure.Failure '
            '%s: division by zero>' % (typeName,))



class BrokenStr(Exception):
    """
    An exception class the instances of which cannot be presented as strings via
    C{str}.
    """
    def __str__(self):
        # Could raise something else, but there's no point as yet.
        raise self



class BrokenExceptionMetaclass(type):
    """
    A metaclass for an exception type which cannot be presented as a string via
    C{str}.
    """
    def __str__(self):
        raise ValueError("You cannot make a string out of me.")



class BrokenExceptionType(Exception, object):
    """
    The aforementioned exception type which cnanot be presented as a string via
    C{str}.
    """
    __metaclass__ = BrokenExceptionMetaclass



class GetTracebackTests(SynchronousTestCase):
    """
    Tests for L{Failure.getTraceback}.
    """
    def _brokenValueTest(self, detail):
        """
        Construct a L{Failure} with an exception that raises an exception from
        its C{__str__} method and then call C{getTraceback} with the specified
        detail and verify that it returns a string.
        """
        x = BrokenStr()
        f = failure.Failure(x)
        traceback = f.getTraceback(detail=detail)
        self.assertIsInstance(traceback, str)


    def test_brokenValueBriefDetail(self):
        """
        A L{Failure} might wrap an exception with a C{__str__} method which
        raises an exception.  In this case, calling C{getTraceback} on the
        failure with the C{"brief"} detail does not raise an exception.
        """
        self._brokenValueTest("brief")


    def test_brokenValueDefaultDetail(self):
        """
        Like test_brokenValueBriefDetail, but for the C{"default"} detail case.
        """
        self._brokenValueTest("default")


    def test_brokenValueVerboseDetail(self):
        """
        Like test_brokenValueBriefDetail, but for the C{"default"} detail case.
        """
        self._brokenValueTest("verbose")


    def _brokenTypeTest(self, detail):
        """
        Construct a L{Failure} with an exception type that raises an exception
        from its C{__str__} method and then call C{getTraceback} with the
        specified detail and verify that it returns a string.
        """
        f = failure.Failure(BrokenExceptionType())
        traceback = f.getTraceback(detail=detail)
        self.assertIsInstance(traceback, str)


    def test_brokenTypeBriefDetail(self):
        """
        A L{Failure} might wrap an exception the type object of which has a
        C{__str__} method which raises an exception.  In this case, calling
        C{getTraceback} on the failure with the C{"brief"} detail does not raise
        an exception.
        """
        self._brokenTypeTest("brief")


    def test_brokenTypeDefaultDetail(self):
        """
        Like test_brokenTypeBriefDetail, but for the C{"default"} detail case.
        """
        self._brokenTypeTest("default")


    def test_brokenTypeVerboseDetail(self):
        """
        Like test_brokenTypeBriefDetail, but for the C{"verbose"} detail case.
        """
        self._brokenTypeTest("verbose")



class FindFailureTests(SynchronousTestCase):
    """
    Tests for functionality related to L{Failure._findFailure}.
    """

    def test_findNoFailureInExceptionHandler(self):
        """
        Within an exception handler, _findFailure should return
        L{None} in case no Failure is associated with the current
        exception.
        """
        try:
            1/0
        except:
            self.assertIsNone(failure.Failure._findFailure())
        else:
            self.fail("No exception raised from 1/0!?")


    def test_findNoFailure(self):
        """
        Outside of an exception handler, _findFailure should return None.
        """
        if sys.version_info < (3, 0):
            sys.exc_clear()
        self.assertIsNone(sys.exc_info()[-1]) #environment sanity check
        self.assertIsNone(failure.Failure._findFailure())


    def test_findFailure(self):
        """
        Within an exception handler, it should be possible to find the
        original Failure that caused the current exception (if it was
        caused by raiseException).
        """
        f = getDivisionFailure()
        f.cleanFailure()
        try:
            f.raiseException()
        except:
            self.assertEqual(failure.Failure._findFailure(), f)
        else:
            self.fail("No exception raised from raiseException!?")


    def test_failureConstructionFindsOriginalFailure(self):
        """
        When a Failure is constructed in the context of an exception
        handler that is handling an exception raised by
        raiseException, the new Failure should be chained to that
        original Failure.
        """
        f = getDivisionFailure()
        f.cleanFailure()
        try:
            f.raiseException()
        except:
            newF = failure.Failure()
            self.assertEqual(f.getTraceback(), newF.getTraceback())
        else:
            self.fail("No exception raised from raiseException!?")


    def test_failureConstructionWithMungedStackSucceeds(self):
        """
        Pyrex and Cython are known to insert fake stack frames so as to give
        more Python-like tracebacks. These stack frames with empty code objects
        should not break extraction of the exception.
        """
        try:
            raiser.raiseException()
        except raiser.RaiserException:
            f = failure.Failure()
            self.assertTrue(f.check(raiser.RaiserException))
        else:
            self.fail("No exception raised from extension?!")


    if raiser is None:
        skipMsg = "raiser extension not available"
        test_failureConstructionWithMungedStackSucceeds.skip = skipMsg



# On Python 3.5, extract_tb returns "FrameSummary" objects, which are almost
# like the old tuples. This being different does not affect the actual tests
# as we are testing that the input works, and that extract_tb returns something
# reasonable.
if sys.version_info < (3, 5):
    _tb = lambda fn, lineno, name, text: (fn, lineno, name, text)
else:
    from traceback import FrameSummary
    _tb = lambda fn, lineno, name, text: FrameSummary(fn, lineno, name)



class FormattableTracebackTests(SynchronousTestCase):
    """
    Whitebox tests that show that L{failure._Traceback} constructs objects that
    can be used by L{traceback.extract_tb}.

    If the objects can be used by L{traceback.extract_tb}, then they can be
    formatted using L{traceback.format_tb} and friends.
    """

    def test_singleFrame(self):
        """
        A C{_Traceback} object constructed with a single frame should be able
        to be passed to L{traceback.extract_tb}, and we should get a singleton
        list containing a (filename, lineno, methodname, line) tuple.
        """
        tb = failure._Traceback([['method', 'filename.py', 123, {}, {}]])
        # Note that we don't need to test that extract_tb correctly extracts
        # the line's contents. In this case, since filename.py doesn't exist,
        # it will just use None.
        self.assertEqual(traceback.extract_tb(tb),
                         [_tb('filename.py', 123, 'method', None)])


    def test_manyFrames(self):
        """
        A C{_Traceback} object constructed with multiple frames should be able
        to be passed to L{traceback.extract_tb}, and we should get a list
        containing a tuple for each frame.
        """
        tb = failure._Traceback([
            ['method1', 'filename.py', 123, {}, {}],
            ['method2', 'filename.py', 235, {}, {}]])
        self.assertEqual(traceback.extract_tb(tb),
                         [_tb('filename.py', 123, 'method1', None),
                          _tb('filename.py', 235, 'method2', None)])



class FrameAttributesTests(SynchronousTestCase):
    """
    _Frame objects should possess some basic attributes that qualify them as
    fake python Frame objects.
    """

    def test_fakeFrameAttributes(self):
        """
        L{_Frame} instances have the C{f_globals} and C{f_locals} attributes
        bound to C{dict} instance.  They also have the C{f_code} attribute
        bound to something like a code object.
        """
        frame = failure._Frame("dummyname", "dummyfilename")
        self.assertIsInstance(frame.f_globals, dict)
        self.assertIsInstance(frame.f_locals, dict)
        self.assertIsInstance(frame.f_code, failure._Code)



class DebugModeTests(SynchronousTestCase):
    """
    Failure's debug mode should allow jumping into the debugger.
    """

    def setUp(self):
        """
        Override pdb.post_mortem so we can make sure it's called.
        """
        # Make sure any changes we make are reversed:
        post_mortem = pdb.post_mortem
        if _PY3:
            origInit = failure.Failure.__init__
        else:
            origInit = failure.Failure.__dict__['__init__']
        def restore():
            pdb.post_mortem = post_mortem
            if _PY3:
                failure.Failure.__init__ = origInit
            else:
                failure.Failure.__dict__['__init__'] = origInit
        self.addCleanup(restore)

        self.result = []
        pdb.post_mortem = self.result.append
        failure.startDebugMode()


    def test_regularFailure(self):
        """
        If startDebugMode() is called, calling Failure() will first call
        pdb.post_mortem with the traceback.
        """
        try:
            1/0
        except:
            typ, exc, tb = sys.exc_info()
            f = failure.Failure()
        self.assertEqual(self.result, [tb])
        self.assertFalse(f.captureVars)


    def test_captureVars(self):
        """
        If startDebugMode() is called, passing captureVars to Failure() will
        not blow up.
        """
        try:
            1/0
        except:
            typ, exc, tb = sys.exc_info()
            f = failure.Failure(captureVars=True)
        self.assertEqual(self.result, [tb])
        self.assertTrue(f.captureVars)



class ExtendedGeneratorTests(SynchronousTestCase):
    """
    Tests C{failure.Failure} support for generator features added in Python 2.5
    """

    def _throwIntoGenerator(self, f, g):
        try:
            f.throwExceptionIntoGenerator(g)
        except StopIteration:
            pass
        else:
            self.fail("throwExceptionIntoGenerator should have raised "
                      "StopIteration")

    def test_throwExceptionIntoGenerator(self):
        """
        It should be possible to throw the exception that a Failure
        represents into a generator.
        """
        stuff = []
        def generator():
            try:
                yield
            except:
                stuff.append(sys.exc_info())
            else:
                self.fail("Yield should have yielded exception.")
        g = generator()
        f = getDivisionFailure()
        next(g)
        self._throwIntoGenerator(f, g)

        self.assertEqual(stuff[0][0], ZeroDivisionError)
        self.assertIsInstance(stuff[0][1], ZeroDivisionError)

        self.assertEqual(traceback.extract_tb(stuff[0][2])[-1][-1], "1/0")


    def test_findFailureInGenerator(self):
        """
        Within an exception handler, it should be possible to find the
        original Failure that caused the current exception (if it was
        caused by throwExceptionIntoGenerator).
        """
        f = getDivisionFailure()
        f.cleanFailure()

        foundFailures = []
        def generator():
            try:
                yield
            except:
                foundFailures.append(failure.Failure._findFailure())
            else:
                self.fail("No exception sent to generator")

        g = generator()
        next(g)
        self._throwIntoGenerator(f, g)

        self.assertEqual(foundFailures, [f])


    def test_failureConstructionFindsOriginalFailure(self):
        """
        When a Failure is constructed in the context of an exception
        handler that is handling an exception raised by
        throwExceptionIntoGenerator, the new Failure should be chained to that
        original Failure.
        """
        f = getDivisionFailure()
        f.cleanFailure()

        newFailures = []

        def generator():
            try:
                yield
            except:
                newFailures.append(failure.Failure())
            else:
                self.fail("No exception sent to generator")
        g = generator()
        next(g)
        self._throwIntoGenerator(f, g)

        self.assertEqual(len(newFailures), 1)
        self.assertEqual(newFailures[0].getTraceback(), f.getTraceback())

    if _PY3:
        # FIXME: https://twistedmatrix.com/trac/ticket/5949
        test_findFailureInGenerator.skip = (
            "Python 3 support to be fixed in #5949")
        test_failureConstructionFindsOriginalFailure.skip = (
            "Python 3 support to be fixed in #5949")


    def test_ambiguousFailureInGenerator(self):
        """
        When a generator reraises a different exception,
        L{Failure._findFailure} inside the generator should find the reraised
        exception rather than original one.
        """
        def generator():
            try:
                try:
                    yield
                except:
                    [][1]
            except:
                self.assertIsInstance(failure.Failure().value, IndexError)
        g = generator()
        next(g)
        f = getDivisionFailure()
        self._throwIntoGenerator(f, g)


    def test_ambiguousFailureFromGenerator(self):
        """
        When a generator reraises a different exception,
        L{Failure._findFailure} above the generator should find the reraised
        exception rather than original one.
        """
        def generator():
            try:
                yield
            except:
                [][1]
        g = generator()
        next(g)
        f = getDivisionFailure()
        try:
            self._throwIntoGenerator(f, g)
        except:
            self.assertIsInstance(failure.Failure().value, IndexError)
