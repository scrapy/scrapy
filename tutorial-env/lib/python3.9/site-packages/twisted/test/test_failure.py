# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for the L{twisted.python.failure} module.
"""


import linecache
import pdb
import re
import sys
import traceback
from dis import distb
from io import StringIO
from traceback import FrameSummary
from unittest import skipIf

from cython_test_exception_raiser import raiser  # type: ignore[import]

from twisted.python import failure, reflect
from twisted.trial.unittest import SynchronousTestCase


def getDivisionFailure(*args, **kwargs):
    """
    Make a C{Failure} of a divide-by-zero error.

    @param args: Any C{*args} are passed to Failure's constructor.
    @param kwargs: Any C{**kwargs} are passed to Failure's constructor.
    """
    try:
        1 / 0
    except BaseException:
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
            raise NotImplementedError("test")
        except BaseException:
            f = failure.Failure()
        error = f.trap(SystemExit, RuntimeError)
        self.assertEqual(error, RuntimeError)
        self.assertEqual(f.type, NotImplementedError)

    def test_trapRaisesWrappedException(self):
        """
        If the wrapped C{Exception} is not a subclass of one of the
        expected types, L{failure.Failure.trap} raises the wrapped
        C{Exception}.
        """
        exception = ValueError()
        try:
            raise exception
        except BaseException:
            f = failure.Failure()

        untrapped = self.assertRaises(ValueError, f.trap, OverflowError)
        self.assertIs(exception, untrapped)

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
        except BaseException:
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
        self.assertTrue(s.startswith(prefix), f"{prefix!r} is not the start of {s!r}")

    def assertEndsWith(self, s, suffix):
        """
        Assert that C{s} end with a particular C{suffix}.

        @param s: The input string.
        @type s: C{str}
        @param suffix: The string that C{s} should end with.
        @type suffix: C{str}
        """
        self.assertTrue(s.endswith(suffix), f"{suffix!r} is not the end of {s!r}")

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
            exampleLocalVar = "xyz"
            # Silence the linter as this variable is checked via
            # the traceback.
            exampleLocalVar

        f = getDivisionFailure(captureVars=captureVars)
        out = StringIO()
        if cleanFailure:
            f.cleanFailure()
        f.printDetailedTraceback(out)

        tb = out.getvalue()
        start = "*--- Failure #%d%s---\n" % (
            f.count,
            (f.pickled and " (pickled) ") or " ",
        )
        end = "{}: {}\n*--- End of Failure #{} ---\n".format(
            reflect.qual(f.type),
            reflect.safe_str(f.value),
            f.count,
        )
        self.assertTracebackFormat(tb, start, end)

        # Variables are printed on lines with 2 leading spaces.
        linesWithVars = [line for line in tb.splitlines() if line.startswith("  ")]

        if captureVars:
            self.assertNotEqual([], linesWithVars)
            if cleanFailure:
                line = "  exampleLocalVar : \"'xyz'\""
            else:
                line = "  exampleLocalVar : 'xyz'"
            self.assertIn(line, linesWithVars)
        else:
            self.assertEqual([], linesWithVars)
            self.assertIn(
                " [Capture of Locals and Globals disabled (use " "captureVars=True)]\n",
                tb,
            )

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
            exampleLocalVar = "abcde"
            # Silence the linter as this variable is checked via
            # the traceback.
            exampleLocalVar

        f = getDivisionFailure()
        out = StringIO()
        f.printBriefTraceback(out)
        tb = out.getvalue()
        stack = ""
        for method, filename, lineno, localVars, globalVars in f.frames:
            stack += f"{filename}:{lineno}:{method}\n"

        zde = repr(ZeroDivisionError)
        self.assertTracebackFormat(
            tb,
            f"Traceback: {zde}: ",
            f"{failure.EXCEPTION_CAUGHT_HERE}\n{stack}",
        )

        if captureVars:
            self.assertIsNone(re.search("exampleLocalVar.*abcde", tb))

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
              1 / 0
            exceptions.ZeroDivisionError: float division

        @param captureVars: Enables L{Failure.captureVars}.
        @type captureVars: C{bool}
        """
        if captureVars:
            exampleLocalVar = "xyzzy"
            # Silence the linter as this variable is checked via
            # the traceback.
            exampleLocalVar

        f = getDivisionFailure(captureVars=captureVars)
        out = StringIO()
        f.printTraceback(out)
        tb = out.getvalue()
        stack = ""
        for method, filename, lineno, localVars, globalVars in f.frames:
            stack += f'  File "{filename}", line {lineno}, in {method}\n'
            stack += f"    {linecache.getline(filename, lineno).strip()}\n"

        self.assertTracebackFormat(
            tb,
            "Traceback (most recent call last):",
            "%s\n%s%s: %s\n"
            % (
                failure.EXCEPTION_CAUGHT_HERE,
                stack,
                reflect.qual(f.type),
                reflect.safe_str(f.value),
            ),
        )

        if captureVars:
            self.assertIsNone(re.search("exampleLocalVar.*xyzzy", tb))

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
        self.assertRaises(
            ValueError, failure.format_frames, None, None, detail="noisia"
        )

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
            raise Exception("f.raiseException() didn't raise ZeroDivisionError!?")

    def test_RaiseExceptionWithTB(self):
        f = getDivisionFailure()
        innerline = self._getInnermostFrameLine(f)
        self.assertEqual(innerline, "1 / 0")

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
            1 / 0
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
            1 / 0
        except BaseException:
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

    def test_distb(self):
        """
        The traceback captured by a L{Failure} is compatible with the stdlib
        L{dis.distb} function as used in post-mortem debuggers. Specifically,
        it doesn't cause that function to raise an exception.
        """
        f = getDivisionFailure()
        buf = StringIO()
        distb(f.getTracebackObject(), file=buf)
        # The bytecode details vary across Python versions, so we only check
        # that the arrow pointing at the source of the exception is present.
        self.assertIn(" --> ", buf.getvalue())

    def test_repr(self):
        """
        The C{repr} of a L{failure.Failure} shows the type and string
        representation of the underlying exception.
        """
        f = getDivisionFailure()
        typeName = reflect.fullyQualifiedName(ZeroDivisionError)
        self.assertEqual(
            repr(f),
            "<twisted.python.failure.Failure " "%s: division by zero>" % (typeName,),
        )


class BrokenStr(Exception):
    """
    An exception class the instances of which cannot be presented as strings
    via L{str}.
    """

    def __str__(self) -> str:
        # Could raise something else, but there's no point as yet.
        raise self


class BrokenExceptionMetaclass(type):
    """
    A metaclass for an exception type which cannot be presented as a string via
    L{str}.
    """

    def __str__(self) -> str:
        raise ValueError("You cannot make a string out of me.")


class BrokenExceptionType(Exception, metaclass=BrokenExceptionMetaclass):

    """
    The aforementioned exception type which cannot be presented as a string via
    L{str}.
    """


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
            1 / 0
        except BaseException:
            self.assertIsNone(failure.Failure._findFailure())
        else:
            self.fail("No exception raised from 1/0!?")

    def test_findNoFailure(self):
        """
        Outside of an exception handler, _findFailure should return None.
        """
        self.assertIsNone(sys.exc_info()[-1])  # environment sanity check
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
        except BaseException:
            self.assertEqual(failure.Failure._findFailure(), f)
        else:
            self.fail("No exception raised from raiseException!?")

    def test_failureConstructionFindsOriginalFailure(self):
        """
        When a Failure is constructed in the context of an exception
        handler that is handling an exception raised by
        raiseException, the new Failure should be chained to that
        original Failure.
        Means the new failure should still show the same origin frame,
        but with different complete stack trace (as not thrown at same place).
        """
        f = getDivisionFailure()
        f.cleanFailure()
        try:
            f.raiseException()
        except BaseException:
            newF = failure.Failure()
            tb = f.getTraceback().splitlines()
            new_tb = newF.getTraceback().splitlines()
            self.assertNotEqual(tb, new_tb)
            self.assertEqual(tb[-3:], new_tb[-3:])
        else:
            self.fail("No exception raised from raiseException!?")

    @skipIf(raiser is None, "raiser extension not available")
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


# On Python 3.5, extract_tb returns "FrameSummary" objects, which are almost
# like the old tuples. This being different does not affect the actual tests
# as we are testing that the input works, and that extract_tb returns something
# reasonable.
def _tb(fn, lineno, name, text):
    return FrameSummary(fn, lineno, name)


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
        tb = failure._Traceback([], [["method", "filename.py", 123, {}, {}]])
        # Note that we don't need to test that extract_tb correctly extracts
        # the line's contents. In this case, since filename.py doesn't exist,
        # it will just use None.
        self.assertEqual(
            traceback.extract_tb(tb), [_tb("filename.py", 123, "method", None)]
        )

    def test_manyFrames(self):
        """
        A C{_Traceback} object constructed with multiple frames should be able
        to be passed to L{traceback.extract_tb}, and we should get a list
        containing a tuple for each frame.
        """
        tb = failure._Traceback(
            [
                ["caller1", "filename.py", 7, {}, {}],
                ["caller2", "filename.py", 8, {}, {}],
            ],
            [
                ["method1", "filename.py", 123, {}, {}],
                ["method2", "filename.py", 235, {}, {}],
            ],
        )
        self.assertEqual(
            traceback.extract_tb(tb),
            [
                _tb("filename.py", 123, "method1", None),
                _tb("filename.py", 235, "method2", None),
            ],
        )

        # We should also be able to extract_stack on it
        self.assertEqual(
            traceback.extract_stack(tb.tb_frame),
            [
                _tb("filename.py", 7, "caller1", None),
                _tb("filename.py", 8, "caller2", None),
                _tb("filename.py", 123, "method1", None),
            ],
        )


class FakeAttributesTests(SynchronousTestCase):
    """
    _Frame, _Code and _TracebackFrame objects should possess some basic
    attributes that qualify them as fake python objects, allowing the return of
    _Traceback to be used as a fake traceback. The attributes that have zero or
    empty values are there so that things expecting them find them (e.g. post
    mortem debuggers).
    """

    def test_fakeFrameAttributes(self):
        """
        L{_Frame} instances have the C{f_globals} and C{f_locals} attributes
        bound to C{dict} instance.  They also have the C{f_code} attribute
        bound to something like a code object.
        """
        back_frame = failure._Frame(
            (
                "dummyparent",
                "dummyparentfile",
                111,
                None,
                None,
            ),
            None,
        )
        fake_locals = {"local_var": 42}
        fake_globals = {"global_var": 100}
        frame = failure._Frame(
            (
                "dummyname",
                "dummyfilename",
                42,
                fake_locals,
                fake_globals,
            ),
            back_frame,
        )
        self.assertEqual(frame.f_globals, fake_globals)
        self.assertEqual(frame.f_locals, fake_locals)
        self.assertIsInstance(frame.f_code, failure._Code)
        self.assertEqual(frame.f_back, back_frame)
        self.assertIsInstance(frame.f_builtins, dict)
        self.assertIsInstance(frame.f_lasti, int)
        self.assertEqual(frame.f_lineno, 42)
        self.assertIsInstance(frame.f_trace, type(None))

    def test_fakeCodeAttributes(self):
        """
        See L{FakeAttributesTests} for more details about this test.
        """
        code = failure._Code("dummyname", "dummyfilename")
        self.assertEqual(code.co_name, "dummyname")
        self.assertEqual(code.co_filename, "dummyfilename")
        self.assertIsInstance(code.co_argcount, int)
        self.assertIsInstance(code.co_code, bytes)
        self.assertIsInstance(code.co_cellvars, tuple)
        self.assertIsInstance(code.co_consts, tuple)
        self.assertIsInstance(code.co_firstlineno, int)
        self.assertIsInstance(code.co_flags, int)
        self.assertIsInstance(code.co_lnotab, bytes)
        self.assertIsInstance(code.co_freevars, tuple)
        self.assertIsInstance(code.co_posonlyargcount, int)
        self.assertIsInstance(code.co_kwonlyargcount, int)
        self.assertIsInstance(code.co_names, tuple)
        self.assertIsInstance(code.co_nlocals, int)
        self.assertIsInstance(code.co_stacksize, int)
        self.assertIsInstance(code.co_varnames, list)
        self.assertIsInstance(code.co_positions(), tuple)

    def test_fakeTracebackFrame(self):
        """
        See L{FakeAttributesTests} for more details about this test.
        """
        frame = failure._Frame(
            ("dummyname", "dummyfilename", 42, {}, {}),
            None,
        )
        traceback_frame = failure._TracebackFrame(frame)
        self.assertEqual(traceback_frame.tb_frame, frame)
        self.assertEqual(traceback_frame.tb_lineno, 42)
        self.assertIsInstance(traceback_frame.tb_lasti, int)
        self.assertTrue(hasattr(traceback_frame, "tb_next"))


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
        origInit = failure.Failure.__init__

        def restore():
            pdb.post_mortem = post_mortem
            failure.Failure.__init__ = origInit

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
            1 / 0
        except BaseException:
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
            1 / 0
        except BaseException:
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
            self.fail("throwExceptionIntoGenerator should have raised " "StopIteration")

    def test_throwExceptionIntoGenerator(self):
        """
        It should be possible to throw the exception that a Failure
        represents into a generator.
        """
        stuff = []

        def generator():
            try:
                yield
            except BaseException:
                stuff.append(sys.exc_info())
            else:
                self.fail("Yield should have yielded exception.")

        g = generator()
        f = getDivisionFailure()
        next(g)
        self._throwIntoGenerator(f, g)

        self.assertEqual(stuff[0][0], ZeroDivisionError)
        self.assertIsInstance(stuff[0][1], ZeroDivisionError)

        self.assertEqual(traceback.extract_tb(stuff[0][2])[-1][-1], "1 / 0")

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
            except BaseException:
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
        original_failure_str = f.getTraceback()

        newFailures = []

        def generator():
            try:
                yield
            except BaseException:
                newFailures.append(failure.Failure())
            else:
                self.fail("No exception sent to generator")

        g = generator()
        next(g)
        self._throwIntoGenerator(f, g)

        self.assertEqual(len(newFailures), 1)

        # The original failure should not be changed.
        self.assertEqual(original_failure_str, f.getTraceback())

        # The new failure should be different and contain stack info for
        # our generator.
        self.assertNotEqual(newFailures[0].getTraceback(), f.getTraceback())
        self.assertIn("generator", newFailures[0].getTraceback())
        self.assertNotIn("generator", f.getTraceback())

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
                except BaseException:
                    [][1]
            except BaseException:
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
            except BaseException:
                [][1]

        g = generator()
        next(g)
        f = getDivisionFailure()
        try:
            self._throwIntoGenerator(f, g)
        except BaseException:
            self.assertIsInstance(failure.Failure().value, IndexError)
