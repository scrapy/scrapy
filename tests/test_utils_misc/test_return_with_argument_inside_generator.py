import warnings
from functools import partial
from unittest import mock

from scrapy.utils.misc import (
    is_generator_with_return_value,
    warn_on_generator_with_return_value,
)


def _indentation_error(*args, **kwargs):
    raise IndentationError


def top_level_return_something():
    """
    docstring
    """
    url = """
https://example.org
"""
    yield url
    return 1


def top_level_return_none():
    """
    docstring
    """
    url = """
https://example.org
"""
    yield url


def generator_that_returns_stuff():
    yield 1
    yield 2
    return 3


class TestUtilsMisc:
    def test_generators_return_something(self):
        def f1():
            yield 1
            return 2

        def g1():
            yield 1
            return "asdf"

        def h1():
            yield 1

            def helper():
                return 0

            yield helper()
            return 2

        def i1():
            """
            docstring
            """
            url = """
https://example.org
        """
            yield url
            return 1

        assert is_generator_with_return_value(top_level_return_something)
        assert is_generator_with_return_value(f1)
        assert is_generator_with_return_value(g1)
        assert is_generator_with_return_value(h1)
        assert is_generator_with_return_value(i1)

        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, top_level_return_something)
            assert len(w) == 1
            assert (
                'The "NoneType.top_level_return_something" method is a generator'
                in str(w[0].message)
            )
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, f1)
            assert len(w) == 1
            assert 'The "NoneType.f1" method is a generator' in str(w[0].message)
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, g1)
            assert len(w) == 1
            assert 'The "NoneType.g1" method is a generator' in str(w[0].message)
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, h1)
            assert len(w) == 1
            assert 'The "NoneType.h1" method is a generator' in str(w[0].message)
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, i1)
            assert len(w) == 1
            assert 'The "NoneType.i1" method is a generator' in str(w[0].message)

    def test_generators_return_none(self):
        def f2():
            yield 1

        def g2():
            yield 1

        def h2():
            yield 1

        def i2():
            yield 1
            yield from generator_that_returns_stuff()

        def j2():
            yield 1

            def helper():
                return 0

            yield helper()

        def k2():
            """
            docstring
            """
            url = """
https://example.org
        """
            yield url

        def l2():
            return

        assert not is_generator_with_return_value(top_level_return_none)
        assert not is_generator_with_return_value(f2)
        assert not is_generator_with_return_value(g2)
        assert not is_generator_with_return_value(h2)
        assert not is_generator_with_return_value(i2)
        assert not is_generator_with_return_value(j2)  # not recursive
        assert not is_generator_with_return_value(k2)  # not recursive
        assert not is_generator_with_return_value(l2)

        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, top_level_return_none)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, f2)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, g2)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, h2)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, i2)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, j2)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, k2)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, l2)
            assert len(w) == 0

    def test_generators_return_none_with_decorator(self):
        def decorator(func):
            def inner_func():
                func()

            return inner_func

        @decorator
        def f3():
            yield 1

        @decorator
        def g3():
            yield 1

        @decorator
        def h3():
            yield 1

        @decorator
        def i3():
            yield 1
            yield from generator_that_returns_stuff()

        @decorator
        def j3():
            yield 1

            def helper():
                return 0

            yield helper()

        @decorator
        def k3():
            """
            docstring
            """
            url = """
https://example.org
        """
            yield url

        @decorator
        def l3():
            return

        assert not is_generator_with_return_value(top_level_return_none)
        assert not is_generator_with_return_value(f3)
        assert not is_generator_with_return_value(g3)
        assert not is_generator_with_return_value(h3)
        assert not is_generator_with_return_value(i3)
        assert not is_generator_with_return_value(j3)  # not recursive
        assert not is_generator_with_return_value(k3)  # not recursive
        assert not is_generator_with_return_value(l3)

        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, top_level_return_none)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, f3)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, g3)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, h3)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, i3)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, j3)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, k3)
            assert len(w) == 0
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, l3)
            assert len(w) == 0

    @mock.patch(
        "scrapy.utils.misc.is_generator_with_return_value", new=_indentation_error
    )
    def test_indentation_error(self):
        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(None, top_level_return_none)
            assert len(w) == 1
            assert "Unable to determine" in str(w[0].message)

    def test_partial(self):
        def cb(arg1, arg2):
            yield {}

        partial_cb = partial(cb, arg1=42)
        assert not is_generator_with_return_value(partial_cb)

    def test_warn_on_generator_return_value_setting_disabled(self):
        class DummySettings:
            def getbool(self, key, default=None):
                assert key == "WARN_ON_GENERATOR_RETURN_VALUE"
                return False

        class DummySpider:
            settings = DummySettings()

        def generator_with_return():
            yield 1
            return 42

        assert is_generator_with_return_value(generator_with_return)

        with warnings.catch_warnings(record=True) as w:
            warn_on_generator_with_return_value(DummySpider(), generator_with_return)
            assert len(w) == 0
