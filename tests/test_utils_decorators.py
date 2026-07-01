from __future__ import annotations

import warnings

import pytest
from twisted.internet.defer import Deferred

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.decorators import _warn_spider_arg, deprecated, inthread
from scrapy.utils.defer import maybe_deferred_to_future
from tests.utils.decorators import coroutine_test


class TestDeprecated:
    def test_warns_and_still_calls(self):
        @deprecated()
        def add(a, b):
            return a + b

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Call to deprecated function add\."
        ):
            result = add(2, 3)

        assert result == 5

    def test_use_instead_in_message(self):
        @deprecated(use_instead="other_function")
        def old():
            return None

        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"Call to deprecated function old\. Use other_function instead\.",
        ):
            old()

    def test_applied_without_parentheses(self):
        @deprecated
        def square(x):
            return x * x

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Call to deprecated function square\."
        ) as record:
            result = square(4)

        assert result == 16
        # No "Use ... instead." part when applied directly to the function.
        assert "instead" not in str(record[0].message)


class TestInthread:
    @coroutine_test
    async def test_returns_deferred_with_result(self):
        @inthread
        def multiply(a, b):
            return a * b

        deferred = multiply(6, 7)
        assert isinstance(deferred, Deferred)
        assert await maybe_deferred_to_future(deferred) == 42


class TestWarnSpiderArg:
    def test_sync_warns_with_spider_arg(self):
        @_warn_spider_arg
        def parse(response, spider=None):
            return response

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Passing a 'spider' argument"
        ):
            assert parse("response", spider="spider") == "response"

    def test_sync_no_warning_without_spider_arg(self):
        @_warn_spider_arg
        def parse(response, spider=None):
            return response

        with warnings.catch_warnings():
            warnings.simplefilter("error", category=ScrapyDeprecationWarning)
            assert parse("response") == "response"

    @coroutine_test
    async def test_async_warns_with_spider_arg(self):
        @_warn_spider_arg
        async def parse(response, spider=None):
            return response

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Passing a 'spider' argument"
        ):
            assert await parse("response", spider="spider") == "response"

    @coroutine_test
    async def test_asyncgen_warns_with_spider_arg(self):
        @_warn_spider_arg
        async def parse(response, spider=None):
            yield response

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Passing a 'spider' argument"
        ):
            results = [item async for item in parse("response", spider="spider")]

        assert results == ["response"]
