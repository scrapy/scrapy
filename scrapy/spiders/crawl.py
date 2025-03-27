"""
This modules implements the CrawlSpider which is the recommended spider to use
for scraping typical websites that requires crawling pages.

See documentation in docs/topics/spiders.rst
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING, Any, Optional, TypeVar, cast

from twisted.python.failure import Failure

from scrapy.http import HtmlResponse, Request, Response
from scrapy.link import Link
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import Spider
from scrapy.utils.asyncgen import collect_asyncgen
from scrapy.utils.spider import iterate_spider_output

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http.request import CallbackT


_T = TypeVar("_T")
ProcessLinksT = Callable[[list[Link]], list[Link]]
ProcessRequestT = Callable[[Request, Response], Optional[Request]]


def _identity(x: _T) -> _T:
    return x


def _identity_process_request(request: Request, response: Response) -> Request | None:
    return request


def _get_method(method: Callable | str | None, spider: Spider) -> Callable | None:
    if callable(method):
        return method
    if isinstance(method, str):
        return getattr(spider, method, None)
    return None


_default_link_extractor = LinkExtractor()


class Rule:
    def __init__(
        self,
        link_extractor: LinkExtractor | None = None,
        callback: CallbackT | str | None = None,
        cb_kwargs: dict[str, Any] | None = None,
        follow: bool | None = None,
        process_links: ProcessLinksT | str | None = None,
        process_request: ProcessRequestT | str | None = None,
        errback: Callable[[Failure], Any] | str | None = None,
    ):
        self.link_extractor: LinkExtractor = link_extractor or _default_link_extractor
        self.callback: CallbackT | str | None = callback
        self.errback: Callable[[Failure], Any] | str | None = errback
        self.cb_kwargs: dict[str, Any] = cb_kwargs or {}
        self.process_links: ProcessLinksT | str = process_links or _identity
        self.process_request: ProcessRequestT | str = (
            process_request or _identity_process_request
        )
        self.follow: bool = follow if follow is not None else not callback

    def _compile(self, spider: Spider) -> None:
        # this replaces method names with methods and we can't express this in type hints
        self.callback = cast("CallbackT", _get_method(self.callback, spider))
        self.errback = cast(Callable[[Failure], Any], _get_method(self.errback, spider))
        self.process_links = cast(
            ProcessLinksT, _get_method(self.process_links, spider)
        )
        self.process_request = cast(
            ProcessRequestT, _get_method(self.process_request, spider)
        )


class CrawlSpider(Spider):
    rules: Sequence[Rule] = ()
    _rules: list[Rule]
    _follow_links: bool

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self._compile_rules()

    def _parse(self, response: Response, **kwargs: Any) -> Any:
        return self._parse_response(
            response=response,
            callback=self.parse_start_url,
            cb_kwargs=kwargs,
            follow=True,
        )

    def parse_start_url(self, response: Response, **kwargs: Any) -> Any:
        return []

    def process_results(
        self, response: Response, results: Iterable[Any]
    ) -> Iterable[Any]:
        return results

    def _build_request(self, rule_index: int, link: Link) -> Request:
        return Request(
            url=link.url,
            callback=self._callback,
            errback=self._errback,
            meta={"rule": rule_index, "link_text": link.text},
        )

    def _requests_to_follow(self, response: Response) -> Iterable[Request | None]:
        if not isinstance(response, HtmlResponse):
            return
        seen: set[Link] = set()
        for rule_index, rule in enumerate(self._rules):
            links: list[Link] = [
                lnk
                for lnk in rule.link_extractor.extract_links(response)
                if lnk not in seen
            ]
            for link in cast(ProcessLinksT, rule.process_links)(links):
                seen.add(link)
                request = self._build_request(rule_index, link)
                yield cast(ProcessRequestT, rule.process_request)(request, response)

    def _callback(self, response: Response, **cb_kwargs: Any) -> Any:
        rule = self._rules[cast(int, response.meta["rule"])]
        return self._parse_response(
            response,
            cast("CallbackT", rule.callback),
            {**rule.cb_kwargs, **cb_kwargs},
            rule.follow,
        )

    def _errback(self, failure: Failure) -> Iterable[Any]:
        rule = self._rules[cast(int, failure.request.meta["rule"])]  # type: ignore[attr-defined]
        return self._handle_failure(
            failure, cast(Callable[[Failure], Any], rule.errback)
        )

    async def _parse_response(
        self,
        response: Response,
        callback: CallbackT | None,
        cb_kwargs: dict[str, Any],
        follow: bool = True,
    ) -> AsyncIterator[Any]:
        if callback:
            cb_res = callback(response, **cb_kwargs) or ()
            if isinstance(cb_res, AsyncIterator):
                cb_res = await collect_asyncgen(cb_res)
            elif isinstance(cb_res, Awaitable):
                cb_res = await cb_res
            cb_res = self.process_results(response, cb_res)
            for request_or_item in iterate_spider_output(cb_res):
                yield request_or_item

        if follow and self._follow_links:
            for request_or_item in self._requests_to_follow(response):
                yield request_or_item

    def _handle_failure(
        self, failure: Failure, errback: Callable[[Failure], Any] | None
    ) -> Iterable[Any]:
        if errback:
            results = errback(failure) or ()
            yield from iterate_spider_output(results)

    def _compile_rules(self) -> None:
        self._rules = []
        for rule in self.rules:
            self._rules.append(copy.copy(rule))
            self._rules[-1]._compile(self)

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any) -> Self:
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider._follow_links = crawler.settings.getbool(
            "CRAWLSPIDER_FOLLOW_LINKS", True
        )
        return spider
