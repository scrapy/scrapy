import warnings
from functools import partial
from unittest import mock

import pytest

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
    @pytest.fixture
    def mock_spider(self):
        class MockSettings:
            def __init__(self, settings_dict=None):
                self.settings_dict = settings_dict or {
                    "WARN_ON_GENERATOR_RETURN_VALUE": True
                }

            def getbool(self, name, default=False):
                return self.settings_dict.get(name, default)

        class MockSpider:
            def __init__(self):
                self.settings = MockSettings()

        return MockSpider()

    def test_generators_return_something(self, mock_spider):
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

        with pytest.warns(
            UserWarning,
            match='The "MockSpider.top_level_return_something" method is a generator',
        ):
            warn_on_generator_with_return_value(mock_spider, top_level_return_something)
        with pytest.warns(
            UserWarning, match='The "MockSpider.f1" method is a generator'
        ):
            warn_on_generator_with_return_value(mock_spider, f1)
        with pytest.warns(
            UserWarning, match='The "MockSpider.g1" method is a generator'
        ):
            warn_on_generator_with_return_value(mock_spider, g1)
        with pytest.warns(
            UserWarning, match='The "MockSpider.h1" method is a generator'
        ):
            warn_on_generator_with_return_value(mock_spider, h1)
        with pytest.warns(
            UserWarning, match='The "MockSpider.i1" method is a generator'
        ):
            warn_on_generator_with_return_value(mock_spider, i1)

    def test_generators_return_none(self, mock_spider):
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

        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            warn_on_generator_with_return_value(mock_spider, top_level_return_none)
            warn_on_generator_with_return_value(mock_spider, f2)
            warn_on_generator_with_return_value(mock_spider, g2)
            warn_on_generator_with_return_value(mock_spider, h2)
            warn_on_generator_with_return_value(mock_spider, i2)
            warn_on_generator_with_return_value(mock_spider, j2)
            warn_on_generator_with_return_value(mock_spider, k2)
            warn_on_generator_with_return_value(mock_spider, l2)

    def test_generators_return_none_with_decorator(self, mock_spider):
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

        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            warn_on_generator_with_return_value(mock_spider, top_level_return_none)
            warn_on_generator_with_return_value(mock_spider, f3)
            warn_on_generator_with_return_value(mock_spider, g3)
            warn_on_generator_with_return_value(mock_spider, h3)
            warn_on_generator_with_return_value(mock_spider, i3)
            warn_on_generator_with_return_value(mock_spider, j3)
            warn_on_generator_with_return_value(mock_spider, k3)
            warn_on_generator_with_return_value(mock_spider, l3)

    @mock.patch(
        "scrapy.utils.misc.is_generator_with_return_value", new=_indentation_error
    )
    def test_indentation_error(self, mock_spider):
        with pytest.warns(UserWarning, match="Unable to determine"):
            warn_on_generator_with_return_value(mock_spider, top_level_return_none)

    def test_partial(self):
        def cb(arg1, arg2):
            yield {}

        partial_cb = partial(cb, arg1=42)
        assert not is_generator_with_return_value(partial_cb)

    def test_warn_on_generator_with_return_value_settings_disabled(self):
        class MockSettings:
            def __init__(self, settings_dict=None):
                self.settings_dict = settings_dict or {}

            def getbool(self, name, default=False):
                return self.settings_dict.get(name, default)

        class MockSpider:
            def __init__(self):
                self.settings = MockSettings({"WARN_ON_GENERATOR_RETURN_VALUE": False})

        spider = MockSpider()

        def gen_with_return():
            yield 1
            return "value"

        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            warn_on_generator_with_return_value(spider, gen_with_return)

        spider.settings.settings_dict["WARN_ON_GENERATOR_RETURN_VALUE"] = True

        with pytest.warns(UserWarning, match="is a generator"):
            warn_on_generator_with_return_value(spider, gen_with_return)
