import unittest

from scrapy.utils.misc import is_generator_with_return_value


class UtilsMiscPy3TestCase(unittest.TestCase):

    def test_generators_with_return_statements(self):
        def f():
            yield 1
            return 2

        def g():
            yield 1
            return 'asdf'

        def h():
            yield 1
            return None

        def i():
            yield 1
            return

        def j():
            yield 1

        def k():
            yield 1
            yield from g()

        def m():
            yield 1

            def helper():
                return 0

            yield helper()

        def n():
            yield 1

            def helper():
                return 0

            yield helper()
            return 2

        assert is_generator_with_return_value(f)
        assert is_generator_with_return_value(g)
        assert not is_generator_with_return_value(h)
        assert not is_generator_with_return_value(i)
        assert not is_generator_with_return_value(j)
        assert not is_generator_with_return_value(k)  # not recursive
        assert not is_generator_with_return_value(m)
        assert is_generator_with_return_value(n)
