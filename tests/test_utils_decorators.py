from __future__ import annotations

import sys
import warnings
from typing import TYPE_CHECKING, Any

import pytest
from twisted.internet.defer import Deferred

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.decorators import _warn_spider_arg, deprecated, inthread
from scrapy.utils.defer import maybe_deferred_to_future
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable


class TestDeprecated:
    def test_warns_and_still_calls(self):
        with pytest.warns(
            ScrapyDeprecationWarning, match=r"decorators\.deprecated\(\) is deprecated"
        ):
            decorate = deprecated()

        @decorate
        def add(a: int, b: int) -> int:
            return a + b

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Call to deprecated function add\."
        ):
            result = add(2, 3)

        assert result == 5

    def test_use_instead_in_message(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            decorate = deprecated(use_instead="other_function")

        @decorate
        def old() -> None:
            return None

        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"Call to deprecated function old\. Use other_function instead\.",
        ):
            old()

    def test_applied_without_parentheses(self):
        def square(x: int) -> int:
            return x * x

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            square = deprecated(square)

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
        def parse(response: str, spider: str | None = None) -> str:
            return response

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Passing a 'spider' argument"
        ):
            assert parse("response", spider="spider") == "response"

    @pytest.mark.skipif(
        sys.version_info < (3, 14),
        reason="annotations are only lazily evaluated since Python 3.14 (PEP 649)",
    )
    def test_sync_warns_with_unresolvable_annotations(self):
        # dont_inherit=True, or the module's future import stringizes the annotations
        namespace: dict[str, Any] = {}
        exec(  # pylint: disable=exec-used
            compile(
                "def parse(response: OnlyAtTypeCheckingTime,"
                " spider: OnlyAtTypeCheckingTime | None = None): return response",
                "<test>",
                "exec",
                dont_inherit=True,
            ),
            namespace,
        )
        parse_func: Callable[..., str] = namespace["parse"]
        parse = _warn_spider_arg(parse_func)

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Passing a 'spider' argument"
        ):
            assert parse("response", spider="spider") == "response"

    def test_sync_warns_with_positional_spider_arg(self):
        @_warn_spider_arg
        def parse(response: str, spider: str | None = None) -> str:
            return response

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Passing a 'spider' argument"
        ):
            assert parse("response", "spider") == "response"

    def test_sync_warns_with_keyword_only_spider_arg(self):
        @_warn_spider_arg
        def parse(response: str, *, spider: str | None = None) -> str:
            return response

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Passing a 'spider' argument"
        ):
            assert parse("response", spider="spider") == "response"

    def test_sync_no_warning_without_spider_arg(self):
        @_warn_spider_arg
        def parse(response: str, spider: str | None = None) -> str:
            return response

        with warnings.catch_warnings():
            warnings.simplefilter("error", category=ScrapyDeprecationWarning)
            assert parse("response") == "response"

    @coroutine_test
    async def test_async_warns_with_spider_arg(self):
        @_warn_spider_arg
        async def parse(response: str, spider: str | None = None) -> str:
            return response

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Passing a 'spider' argument"
        ):
            assert await parse("response", spider="spider") == "response"

    @coroutine_test
    async def test_asyncgen_warns_with_spider_arg(self):
        @_warn_spider_arg
        async def parse(
            response: str, spider: str | None = None
        ) -> AsyncGenerator[str]:
            yield response

        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Passing a 'spider' argument"
        ):
            results = [item async for item in parse("response", spider="spider")]

        assert results == ["response"]
