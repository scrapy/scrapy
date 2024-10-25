from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, cast

from scrapy import Request
from scrapy.spiders import Spider
from scrapy.utils.spider import iterate_spider_output

if TYPE_CHECKING:
    from scrapy.http import Response


class InitSpider(Spider):
    """Base Spider with initialization facilities"""

    def start_requests(self) -> Iterable[Request]:
        self._postinit_reqs: Iterable[Request] = super().start_requests()
        return cast(Iterable[Request], iterate_spider_output(self.init_request()))

    def initialized(self, response: Response | None = None) -> Any:
        """This method must be set as the callback of your last initialization
        request. See self.init_request() docstring for more info.
        """
        return self.__dict__.pop("_postinit_reqs")

    def init_request(self) -> Any:
        """This function should return one initialization request, with the
        self.initialized method as callback. When the self.initialized method
        is called this spider is considered initialized. If you need to perform
        several requests for initializing your spider, you can do so by using
        different callbacks. The only requirement is that the final callback
        (of the last initialization request) must be self.initialized.

        The default implementation calls self.initialized immediately, and
        means that no initialization is needed. This method should be
        overridden only when you need to perform requests to initialize your
        spider
        """
        return self.initialized()
