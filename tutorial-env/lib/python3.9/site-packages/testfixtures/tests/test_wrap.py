from unittest import TestCase

from testfixtures.mock import Mock, MagicMock, patch, DEFAULT

from testfixtures import wrap, compare, log_capture, LogCapture


class TestWrap(TestCase):

    def test_wrapping(self):

        m = Mock()

        @wrap(m.before, m.after)
        def test_function(r):
            m.test()
            return 'something'

        compare(m.method_calls, [])
        compare(test_function(), 'something')
        compare(m.method_calls, [
            ('before', (), {}),
            ('test', (), {}),
            ('after', (), {})
            ])

    def test_wrapping_only_before(self):

        before = Mock()

        @wrap(before)
        def test_function():
            return 'something'

        self.assertFalse(before.called)
        compare(test_function(), 'something')
        compare(before.call_count, 1)

    def test_wrapping_wants_return(self):

        m = Mock()
        m.before.return_value = 'something'

        @wrap(m.before, m.after)
        def test_function(r):
            m.test(r)
            return 'r:'+r

        compare(m.method_calls, [])
        compare(test_function(), 'r:something')
        compare(m.method_calls, [
            ('before', (), {}),
            ('test', ('something', ), {}),
            ('after', (), {})
            ])

    def test_wrapping_wants_arguments(self):

        # This only works in python 2.5+, for
        # earlier versions, you'll have to come
        # up with your own `partial` class...
        from functools import partial

        m = Mock()

        @wrap(partial(m.before, 1, x=2), partial(m.after, 3, y=4))
        def test_function(r):
            m.test()
            return 'something'

        compare(m.method_calls, [])
        compare(test_function(), 'something')
        compare(m.method_calls, [
            ('before', (1, ), {'x': 2}),
            ('test', (), {}),
            ('after', (3, ), {'y': 4})
            ])

    def test_multiple_wrappers(self):

        m = Mock()

        @wrap(m.before2, m.after2)
        @wrap(m.before1, m.after1)
        def test_function():
            m.test_function()
            return 'something'

        compare(m.method_calls, [])
        compare(test_function(), 'something')
        compare(m.method_calls, [
            ('before1', (), {}),
            ('before2', (), {}),
            ('test_function', (), {}),
            ('after2', (), {}),
            ('after1', (), {}),
            ])

    def test_multiple_wrappers_wants_return(self):

        m = Mock()
        m.before1.return_value = 1
        m.before2.return_value = 2

        @wrap(m.before2, m.after2)
        @wrap(m.before1, m.after1)
        def test_function(r1, r2):
            m.test_function(r1, r2)
            return 'something'

        compare(m.method_calls, [])
        compare(test_function(), 'something')
        compare(m.method_calls, [
            ('before1', (), {}),
            ('before2', (), {}),
            ('test_function', (1, 2), {}),
            ('after2', (), {}),
            ('after1', (), {}),
            ])

    def test_multiple_wrappers_only_want_first_return(self):

        m = Mock()
        m.before1.return_value = 1

        @wrap(m.before2, m.after2)
        @wrap(m.before1, m.after1)
        def test_function(r1):
            m.test_function(r1)
            return 'something'

        compare(m.method_calls, [])
        compare(test_function(), 'something')
        compare(m.method_calls, [
            ('before1', (), {}),
            ('before2', (), {}),
            ('test_function', (1, ), {}),
            ('after2', (), {}),
            ('after1', (), {}),
            ])

    def test_wrap_method(self):

        m = Mock()

        class T:
            @wrap(m.before, m.after)
            def method(self):
                m.method()

        T().method()

        compare(m.method_calls, [
            ('before', (), {}),
            ('method', (), {}),
            ('after', (), {})
            ])

    def test_wrap_method_wants_return(self):

        m = Mock()
        m.before.return_value = 'return'

        class T:
            @wrap(m.before, m.after)
            def method(self, r):
                m.method(r)

        T().method()

        compare(m.method_calls, [
            ('before', (), {}),
            ('method', ('return', ), {}),
            ('after', (), {})
            ])

    def test_wrapping_different_functions(self):

        m = Mock()

        @wrap(m.before1, m.after1)
        def test_function1():
            m.something1()
            return 'something1'

        @wrap(m.before2, m.after2)
        def test_function2():
            m.something2()
            return 'something2'

        compare(m.method_calls, [])
        compare(test_function1(), 'something1')
        compare(m.method_calls, [
            ('before1', (), {}),
            ('something1', (), {}),
            ('after1', (), {})
            ])
        compare(test_function2(), 'something2')
        compare(m.method_calls, [
            ('before1', (), {}),
            ('something1', (), {}),
            ('after1', (), {}),
            ('before2', (), {}),
            ('something2', (), {}),
            ('after2', (), {})
            ])

    def test_wrapping_local_vars(self):

        m = Mock()

        @wrap(m.before, m.after)
        def test_function():
            something = 1
            m.test()
            return 'something'

        compare(m.method_calls, [])
        compare(test_function(), 'something')
        compare(m.method_calls, [
            ('before', (), {}),
            ('test', (), {}),
            ('after', (), {})
            ])

    def test_wrapping__name__(self):

        m = Mock()

        @wrap(m.before, m.after)
        def test_function():
            pass  # pragma: no cover

        compare(test_function.__name__, 'test_function')

    def test_our_wrap_dealing_with_mock_patch(self):

        @patch.multiple('testfixtures.tests.sample1', X=DEFAULT)
        @log_capture()
        def patched(log, X):
            from testfixtures.tests.sample1 import X as imported_X
            assert isinstance(log, LogCapture)
            assert isinstance(X, MagicMock)
            assert imported_X is X

        patched()

    def test_patch_with_dict(self):
        @patch('testfixtures.tests.sample1.X', {'x': 1})
        @log_capture()
        def patched(log):
            assert isinstance(log, LogCapture)
            from testfixtures.tests.sample1 import X
            assert X == {'x': 1}

        patched()
