from textwrap import dedent

from testfixtures import Comparison as C, ShouldRaise, should_raise
from unittest import TestCase

from ..compat import PY_37_PLUS
from ..shouldraise import ShouldAssert


class TestShouldAssert(object):

    def test_no_exception(self):
        try:
            with ShouldAssert('foo'):
                pass
        except AssertionError as e:
            assert str(e) == "Expected AssertionError('foo'), None raised!"

    def test_wrong_exception(self):
        try:
            with ShouldAssert('foo'):
                raise KeyError()
        except KeyError:
            pass

    def test_wrong_text(self):
        try:
            with ShouldAssert('foo'):
                assert False, 'bar'
        except AssertionError as e:
            assert str(e) == dedent("""\
                --- expected
                +++ actual
                @@ -1 +1,2 @@
                -foo
                +bar
                +assert False""")



class TestShouldRaise(TestCase):

    def test_no_params(self):
        def to_test():
            raise ValueError('wrong value supplied')
        should_raise(ValueError('wrong value supplied'))(to_test)()

    def test_no_exception(self):
        def to_test():
            pass
        with ShouldAssert('ValueError() (expected) != None (raised)'):
            should_raise(ValueError())(to_test)()

    def test_wrong_exception(self):
        def to_test():
            raise ValueError('bar')
        if PY_37_PLUS:
            expected = "ValueError('foo') (expected) != ValueError('bar') (raised)"
        else:
            expected = "ValueError('foo',) (expected) != ValueError('bar',) (raised)"
        with ShouldAssert(expected):
            should_raise(ValueError('foo'))(to_test)()

    def test_only_exception_class(self):
        def to_test():
            raise ValueError('bar')
        should_raise(ValueError)(to_test)()

    def test_wrong_exception_class(self):
        expected_exception = ValueError('bar')
        def to_test():
            raise expected_exception
        try:
            should_raise(KeyError)(to_test)()
        except ValueError as actual_exception:
            assert actual_exception is expected_exception
        else:  # pragma: no cover
            self.fail(('Wrong exception raised'))

    def test_wrong_exception_type(self):
        expected_exception = ValueError('bar')
        def to_test():
            raise expected_exception
        try:
            should_raise(KeyError('foo'))(to_test)()
        except ValueError as actual_exception:
            assert actual_exception is expected_exception
        else:  # pragma: no cover
            self.fail(('Wrong exception raised'))

    def test_no_supplied_or_raised(self):
        # effectvely we're saying "something should be raised!"
        # but we want to inspect s.raised rather than making
        # an up-front assertion
        def to_test():
            pass
        with ShouldAssert("No exception raised!"):
            should_raise()(to_test)()

    def test_args(self):
        def to_test(*args):
            raise ValueError('%s' % repr(args))
        should_raise(ValueError('(1,)'))(to_test)(1)

    def test_kw_to_args(self):
        def to_test(x):
            raise ValueError('%s' % x)
        should_raise(ValueError('1'))(to_test)(x=1)

    def test_kw(self):
        def to_test(**kw):
            raise ValueError('%r' % kw)
        should_raise(ValueError("{'x': 1}"))(to_test)(x=1)

    def test_both(self):
        def to_test(*args, **kw):
            raise ValueError('%r %r' % (args, kw))
        should_raise(ValueError("(1,) {'x': 2}"))(to_test)(1, x=2)

    def test_method_args(self):
        class X:
            def to_test(self, *args):
                self.args = args
                raise ValueError()
        x = X()
        should_raise(ValueError)(x.to_test)(1, 2, 3)
        self.assertEqual(x.args, (1, 2, 3))

    def test_method_kw(self):
        class X:
            def to_test(self, **kw):
                self.kw = kw
                raise ValueError()
        x = X()
        should_raise(ValueError)(x.to_test)(x=1, y=2)
        self.assertEqual(x.kw, {'x': 1, 'y': 2})

    def test_method_both(self):
        class X:
            def to_test(self, *args, **kw):
                self.args = args
                self.kw = kw
                raise ValueError()
        x = X()
        should_raise(ValueError)(x.to_test)(1, y=2)
        self.assertEqual(x.args, (1, ))
        self.assertEqual(x.kw, {'y': 2})

    def test_class_class(self):
        class Test:
            def __init__(self, x):
                # The TypeError is raised due to the mis-matched parameters
                # so the pass never gets executed
                pass  # pragma: no cover
        should_raise(TypeError)(Test)()

    def test_raised(self):
        with ShouldRaise() as s:
            raise ValueError('wrong value supplied')
        self.assertEqual(s.raised, C(ValueError('wrong value supplied')))

    def test_catch_baseexception_1(self):
        with ShouldRaise(SystemExit):
            raise SystemExit()

    def test_catch_baseexception_2(self):
        with ShouldRaise(KeyboardInterrupt):
            raise KeyboardInterrupt()

    def test_with_exception_class_supplied(self):
        with ShouldRaise(ValueError):
            raise ValueError('foo bar')

    def test_with_exception_supplied(self):
        with ShouldRaise(ValueError('foo bar')):
            raise ValueError('foo bar')

    def test_with_exception_supplied_wrong_args(self):
        if PY_37_PLUS:
            expected = "ValueError('foo') (expected) != ValueError('bar') (raised)"
        else:
            expected = "ValueError('foo',) (expected) != ValueError('bar',) (raised)"
        with ShouldAssert(expected):
            with ShouldRaise(ValueError('foo')):
                raise ValueError('bar')

    def test_neither_supplied(self):
        with ShouldRaise():
            raise ValueError('foo bar')

    def test_with_no_exception_when_expected(self):
        if PY_37_PLUS:
            expected = "ValueError('foo') (expected) != None (raised)"
        else:
            expected = "ValueError('foo',) (expected) != None (raised)"
        with ShouldAssert(expected):
            with ShouldRaise(ValueError('foo')):
                pass

    def test_with_no_exception_when_expected_by_type(self):
        with ShouldAssert("<class 'ValueError'> (expected) != None (raised)"):
            with ShouldRaise(ValueError):
                pass

    def test_with_no_exception_when_neither_expected(self):
        with ShouldAssert("No exception raised!"):
            with ShouldRaise():
                pass

    def test_with_getting_raised_exception(self):
        e = ValueError('foo bar')
        with ShouldRaise() as s:
            raise e
        assert e is s.raised

    def test_import_errors_1(self):
        with ShouldRaise(ModuleNotFoundError("No module named 'textfixtures'")):
            import textfixtures.foo.bar

    def test_import_errors_2(self):
        with ShouldRaise(ImportError('X')):
            raise ImportError('X')

    def test_custom_exception(self):

        class FileTypeError(Exception):
            def __init__(self, value):
                self.value = value

        with ShouldRaise(FileTypeError('X')):
            raise FileTypeError('X')

    def test_decorator_usage(self):

        @should_raise(ValueError('bad'))
        def to_test():
            raise ValueError('bad')

        to_test()

    def test_unless_false_okay(self):
        with ShouldRaise(unless=False):
            raise AttributeError()

    def test_unless_false_bad(self):
        with ShouldAssert("No exception raised!"):
            with ShouldRaise(unless=False):
                pass

    def test_unless_true_okay(self):
        with ShouldRaise(unless=True):
            pass

    def test_unless_true_not_okay(self):
        expected_exception = AttributeError('foo')
        try:
            with ShouldRaise(unless=True):
                raise expected_exception
        except AttributeError as actual_exception:
            assert actual_exception is expected_exception
        else:  # pragma: no cover
            self.fail(('Wrong exception raised'))

    def test_unless_decorator_usage(self):

        @should_raise(unless=True)
        def to_test():
            pass

        to_test()

    def test_identical_reprs(self):
        class AnnoyingException(Exception):
            def __init__(self, **kw):
                self.other = kw.get('other')

        with ShouldAssert(
            "AnnoyingException not as expected:\n\n"
            'attributes same:\n'
            "['args']\n\n"
            "attributes differ:\n"
            "'other': 'bar' (expected) != 'baz' (raised)\n\n"
            "While comparing .other: 'bar' (expected) != 'baz' (raised)"
        ):
            with ShouldRaise(AnnoyingException(other='bar')):
                raise AnnoyingException(other='baz')

    def test_identical_reprs_but_args_different(self):

        class MessageError(Exception):
           def __init__(self, message, type=None):
               self.message = message
               self.type = type
           def __repr__(self):
               return 'MessageError({!r}, {!r})'.format(self.message, self.type)

        with ShouldAssert(
            "MessageError not as expected:\n\n"
            'attributes same:\n'
            "['message', 'type']\n\n"
            "attributes differ:\n"
            "'args': ('foo',) (expected) != ('foo', None) (raised)\n\n"
            "While comparing .args: sequence not as expected:\n\n"
            "same:\n"
            "('foo',)\n\n"
            "expected:\n"
            "()\n\n"
            "raised:\n"
            "(None,)"
        ):
            with ShouldRaise(MessageError('foo')):
                raise MessageError('foo', None)


