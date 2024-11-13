from __future__ import annotations

from typing import TYPE_CHECKING, cast

from twisted.python.failure import Failure

from scrapy.commands import BaseRunSpiderCommand
from scrapy.exceptions import UsageError

if TYPE_CHECKING:
    import argparse


class Command(BaseRunSpiderCommand):
    """Command to run a spider within a Scrapy project."""

    requires_project = True

    def syntax(self) -> str:
        """Return the syntax for using the command."""
        return "[options] <spider>"

    def short_desc(self) -> str:
        """Return a short description of the command."""
        return "Run a spider"

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        """Execute the command to run the specified spider.
        
        Args:
            args (list[str]): List containing the name of the spider to run.
            opts (argparse.Namespace): Parsed command-line options.
        
        Raises:
            UsageError: If no spider name is provided or if more than one spider is specified.
        """
        if len(args) < 1:
            raise UsageError("No spider specified.")
        elif len(args) > 1:
            raise UsageError(
                "running 'scrapy crawl' with more than one spider is not supported"
            )
        spname = args[0]

        assert self.crawler_process
        crawl_defer = self.crawler_process.crawl(spname, **opts.spargs)

        if getattr(crawl_defer, "result", None) is not None and issubclass(
            cast(Failure, crawl_defer.result).type, Exception
        ):
            self.exitcode = 1
        else:
            self.crawler_process.start()

            if (
                self.crawler_process.bootstrap_failed
                or hasattr(self.crawler_process, "has_exception")
                and self.crawler_process.has_exception
            ):
                self.exitcode = 1
