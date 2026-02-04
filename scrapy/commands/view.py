import argparse
import logging

from scrapy.commands import fetch
from scrapy.http import Response, TextResponse
from scrapy.utils.response import open_in_browser

logger = logging.getLogger(__name__)


class Command(fetch.Command):
    def short_desc(self) -> str:
        return "Open URL in browser, as seen by Scrapy"

    def long_desc(self) -> str:
        return (
            "Fetch a URL using the Scrapy downloader and show its contents in a browser"
        )

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        super().add_options(parser)
        parser.add_argument("--headers", help=argparse.SUPPRESS)

    def _print_response(self, response: Response, opts: argparse.Namespace) -> None:
        if not isinstance(response, TextResponse):
            logger.error("Cannot view a non-text response.")
            return
        open_in_browser(response)
