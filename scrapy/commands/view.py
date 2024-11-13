import argparse
import logging

from scrapy.commands import fetch
from scrapy.http import Response, TextResponse
from scrapy.utils.response import open_in_browser

logger = logging.getLogger(__name__)

class Command(fetch.Command):
    """Custom Scrapy command to open a URL in the browser as fetched by Scrapy."""

    def short_desc(self) -> str:
        """Return a brief description of the command.

        Returns:
            str: A short description of the command.
        """
        return "Open URL in browser, as seen by Scrapy"

    def long_desc(self) -> str:
        """Return a longer description of the command.

        This description explains that the command fetches a URL using the Scrapy
        downloader and opens the response in a browser.

        Returns:
            str: A detailed description of the command.
        """
        return (
            "Fetch a URL using the Scrapy downloader and show its contents in a browser"
        )

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        """Add custom options to the argument parser.

        Args:
            parser (argparse.ArgumentParser): The argument parser instance to which
                options will be added.
        """
        super().add_options(parser)
        parser.add_argument("--headers", help=argparse.SUPPRESS)

    def _print_response(self, response: Response, opts: argparse.Namespace) -> None:
        """Handle the response and open it in the browser if it is a text response.

        Logs an error if the response is not a `TextResponse`.

        Args:
            response (Response): The response object to be processed.
            opts (argparse.Namespace): The parsed command-line options.
        """
        if not isinstance(response, TextResponse):
            logger.error("Cannot view a non-text response.")
            return
        open_in_browser(response)
