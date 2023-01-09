import logging
from typing import Type, TypeVar

from scrapy import signals
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http.headers import Headers
from scrapy.http.request import Request
from scrapy.spiders import Spider
from scrapy.utils.request import request_fingerprint
from twisted.web.iweb import UNKNOWN_LENGTH


ProgressBarExtensionTypeVar = TypeVar("ProgressBarExtensionTypeVar", bound="ProgressBar")


logger = logging.getLogger(__name__)


class ProgressBar:
    """
    A Scrapy extension that shows a progress bar for downloads that exceed a certain threshold
    """

    def __init__(self, threshold: int) -> None:
        self.threshold = threshold
        self.bars: dict = {}

    @classmethod
    def from_crawler(cls: Type[ProgressBarExtensionTypeVar], crawler: Crawler) -> ProgressBarExtensionTypeVar:
        if not crawler.settings.getint("PROGRESS_BAR_ENABLED"):
            raise NotConfigured()

        try:
            from tqdm import tqdm  # noqa: F401
        except ImportError as ex:
            raise NotConfigured("tqdm module not found, ProgressBar extension disabled") from ex

        threshold = crawler.settings.getint("PROGRESS_BAR_THRESHOLD")
        obj = cls(threshold)
        crawler.signals.connect(obj.headers_received, signal=signals.headers_received)
        crawler.signals.connect(obj.bytes_received, signal=signals.bytes_received)
        crawler.signals.connect(obj.response_received, signal=signals.response_received)
        return obj

    def headers_received(self, headers: Headers, body_length: int, request: Request, spider: Spider) -> None:
        if body_length == UNKNOWN_LENGTH:
            logger.debug("Received UNKNOWN_LENGTH for %s, cannot display progress bar", request.url)
            return

        from tqdm import tqdm  # noqa: F401
        fp = request_fingerprint(request)
        self.bars[fp] = tqdm(total=body_length, desc=request.url, unit="B", unit_scale=True)

    def bytes_received(self, data: bytes, request: Request, spider: Spider) -> None:
        fp = request_fingerprint(request)
        bar = self.bars.get(fp)
        if bar is not None:
            bar.update(len(data))

    def response_received(self, response, request: Request, spider: Spider) -> None:
        fp = request_fingerprint(request)
        bar = self.bars.get(fp)
        if bar is not None:
            bar.close()
