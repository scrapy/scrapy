from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.exceptions import NotConfigured
from scrapy.http import JsonResponse

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request
    from scrapy.crawler import Crawler
    from scrapy.http import Response


class JsonValidationMiddleware:
    """Raise :exc:`json.JSONDecodeError` for a successful
    :class:`~scrapy.http.JsonResponse` whose body is not valid JSON.

    .. versionadded:: VERSION

    .. setting:: JSONVALIDATION_ENABLED

    Set :setting:`JSONVALIDATION_ENABLED` to ``True`` to enable it, and
    :setting:`DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS` to ``True`` for
    :class:`~scrapy.downloadermiddlewares.retry.RetryMiddleware` to retry those
    responses:

    .. code-block:: python

        JSONVALIDATION_ENABLED = True
        DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS = True
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("JSONVALIDATION_ENABLED"):
            raise NotConfigured
        return cls()

    def process_response(self, request: Request, response: Response) -> Response:
        if (
            isinstance(response, JsonResponse)
            and request.method != "HEAD"
            and 200 <= response.status < 300
            and response.status != 204
        ):
            response.json()
        return response
