from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from scrapy.downloadermiddlewares.retry import get_retry_request
from scrapy.exceptions import ChecksumError

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response


class ChecksumMiddleware:
    """Verifies response bodies against the checksums declared in the
    :reqmeta:`expected_checksum` request meta key.

    .. versionadded:: VERSION"""

    def __init__(self, crawler: Crawler):
        self.crawler: Crawler = crawler

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def process_response(
        self, request: Request, response: Response
    ) -> Request | Response:
        for algorithm, checksum in request.meta.get("expected_checksum", {}).items():
            expected = (
                bytes.fromhex(checksum) if isinstance(checksum, str) else checksum
            )
            if hashlib.new(algorithm, response.body).digest() == expected:
                continue
            if not request.meta.get("dont_retry", False):
                assert self.crawler.spider
                new_request = get_retry_request(
                    request,
                    spider=self.crawler.spider,
                    reason=f"checksum/{algorithm}",
                )
                if new_request:
                    return new_request
            raise ChecksumError(
                f"The {algorithm} checksum of the response body of {request} does "
                f"not match the expected checksum."
            )
        return response
