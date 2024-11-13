from __future__ import annotations

from threading import Thread
from typing import TYPE_CHECKING, Any

from scrapy import Spider
from scrapy.commands import ScrapyCommand
from scrapy.http import Request
from scrapy.shell import Shell
from scrapy.utils.spider import DefaultSpider, spidercls_for_request
from scrapy.utils.url import guess_scheme

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace


class Command(ScrapyCommand):
    """Command to launch an interactive scraping console for a given URL or file."""

    requires_project = False
    default_settings = {
        "KEEP_ALIVE": True,
        "LOGSTATS_INTERVAL": 0,
        "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
    }

    def syntax(self) -> str:
        """Return the command syntax for usage.

        Returns:
            str: The syntax of the command.
        """
        return "[url|file]"

    def short_desc(self) -> str:
        """Provide a short description of the command.

        Returns:
            str: A brief description of the command.
        """
        return "Interactive scraping console"

    def long_desc(self) -> str:
        """Provide a detailed description of the command.

        Returns:
            str: A detailed description of the command's purpose.
        """
        return (
            "Interactive console for scraping the given URL or file. "
            "Use ./file.html syntax or full path for a local file."
        )

    def add_options(self, parser: ArgumentParser) -> None:
        """Add command-line options for customizing shell behavior.

        Args:
            parser (ArgumentParser): The argument parser instance.
        """
        super().add_options(parser)
        parser.add_argument(
            "-c",
            dest="code",
            help="Evaluate the code in the shell, print the result and exit",
        )
        parser.add_argument("--spider", dest="spider", help="Specify the spider to use")
        parser.add_argument(
            "--no-redirect",
            dest="no_redirect",
            action="store_true",
            default=False,
            help="Do not handle HTTP 3xx status codes and print response as-is",
        )

    def update_vars(self, vars: dict[str, Any]) -> None:
        """Update the Scrapy objects available in the shell.

        Args:
            vars (dict[str, Any]): The dictionary of variables to update.
        """
        pass  # This method is intended for extension by subclasses or custom use.

    def run(self, args: list[str], opts: Namespace) -> None:
        """Run the interactive shell with the specified options.

        Args:
            args (list[str]): Command-line arguments passed to the command.
            opts (Namespace): Parsed command-line options.
        """
        url = args[0] if args else None
        if url:
            # Convert file paths to URLs by adding the scheme if needed.
            url = guess_scheme(url)

        assert self.crawler_process
        spider_loader = self.crawler_process.spider_loader

        # Determine the spider class to use.
        spidercls: type[Spider] = DefaultSpider
        if opts.spider:
            spidercls = spider_loader.load(opts.spider)
        elif url:
            spidercls = spidercls_for_request(
                spider_loader, Request(url), spidercls, log_multiple=True
            )

        # Create and set up the crawler.
        crawler = self.crawler_process._create_crawler(spidercls)
        crawler._apply_settings()
        crawler.engine = crawler._create_engine()
        crawler.engine.start()

        # Start the crawler engine in a separate thread.
        self._start_crawler_thread()

        # Initialize and start the interactive shell.
        shell = Shell(crawler, update_vars=self.update_vars, code=opts.code)
        shell.start(url=url, redirect=not opts.no_redirect)

    def _start_crawler_thread(self) -> None:
        """Start the crawler engine in a separate thread for concurrent execution."""
        assert self.crawler_process
        t = Thread(
            target=self.crawler_process.start,
            kwargs={"stop_after_crawl": False, "install_signal_handlers": False},
        )
        t.daemon = True
        t.start()
