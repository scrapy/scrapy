import sys
from typing import TYPE_CHECKING

from w3lib.url import is_url

from scrapy import Spider
from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.http import Request, Response
from scrapy.utils.datatypes import SequenceExclude
from scrapy.utils.spider import DefaultSpider, spidercls_for_request

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace


class Command(ScrapyCommand):
    """Command to fetch a URL using the Scrapy downloader and print the response."""

    requires_project = False

    def syntax(self) -> str:
        """Return the syntax for using the command."""
        return "[options] <url>"

    def short_desc(self) -> str:
        """Return a short description of the command."""
        return "Fetch a URL using the Scrapy downloader"

    def long_desc(self) -> str:
        """Return a detailed description of the command's purpose."""
        return (
            "Fetch a URL using the Scrapy downloader and print its content"
            " to stdout. You may want to use --nolog to disable logging"
        )

    def add_options(self, parser: ArgumentParser) -> None:
        """Add custom command-line options for the command.
        
        Args:
            parser (ArgumentParser): The argument parser instance.
        """
        super().add_options(parser)
        parser.add_argument("--spider", dest="spider", help="use this spider")
        parser.add_argument(
            "--headers",
            dest="headers",
            action="store_true",
            help="print response HTTP headers instead of body",
        )
        parser.add_argument(
            "--no-redirect",
            dest="no_redirect",
            action="store_true",
            default=False,
            help="do not handle HTTP 3xx status codes and print response as-is",
        )

    def _print_headers(self, headers: dict[bytes, list[bytes]], prefix: bytes) -> None:
        """Print the HTTP headers with a given prefix.
        
        Args:
            headers (dict[bytes, list[bytes]]): The headers to print.
            prefix (bytes): The prefix to print before each header.
        """
        for key, values in headers.items():
            for value in values:
                self._print_bytes(prefix + b" " + key + b": " + value)

    def _print_response(self, response: Response, opts: Namespace) -> None:
        """Print the response body or headers based on the options provided.
        
        Args:
            response (Response): The response to print.
            opts (Namespace): The command-line options that determine what to print.
        """
        if opts.headers:
            assert response.request
            self._print_headers(response.request.headers, b">")
            print(">")
            self._print_headers(response.headers, b"<")
        else:
            self._print_bytes(response.body)

    def _print_bytes(self, bytes_: bytes) -> None:
        """Write bytes to standard output.
        
        Args:
            bytes_ (bytes): The byte content to print.
        """
        sys.stdout.buffer.write(bytes_ + b"\n")

    def run(self, args: list[str], opts: Namespace) -> None:
        """Run the command to fetch and print the content of a URL.
        
        Args:
            args (list[str]): List containing the URL to fetch.
            opts (Namespace): Parsed command-line options.
        
        Raises:
            UsageError: If no valid URL is provided or multiple URLs are specified.
        """
        if len(args) != 1 or not is_url(args[0]):
            raise UsageError("A single valid URL must be provided.")
        
        request = Request(
            args[0],
            callback=self._print_response,
            cb_kwargs={"opts": opts},
            dont_filter=True,
        )
        
        if not opts.no_redirect:
            request.meta["handle_httpstatus_list"] = SequenceExclude(range(300, 400))
        else:
            request.meta["handle_httpstatus_all"] = True

        spidercls: type[Spider] = DefaultSpider
        assert self.crawler_process
        spider_loader = self.crawler_process.spider_loader
        if opts.spider:
            spidercls = spider_loader.load(opts.spider)
        else:
            spidercls = spidercls_for_request(spider_loader, request, spidercls)

        self.crawler_process.crawl(spidercls, start_requests=lambda: [request])
        self.crawler_process.start()
