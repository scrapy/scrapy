from __future__ import annotations

from typing import TYPE_CHECKING, cast

from twisted.python.failure import Failure

from scrapy.commands import BaseRunSpiderCommand
from scrapy.exceptions import UsageError

if TYPE_CHECKING:
    import argparse


class Command(BaseRunSpiderCommand):
    """
    Command class for running a spider from the command line.

    This class provides the functionality to start a spider via the command line, ensuring
    correct arguments are passed and handling any errors that may arise during the crawl process.

    Attributes:
        requires_project (bool): Flag indicating whether the command requires a project.
    """
    requires_project = True

    def syntax(self) -> str:
        return "[options] <spider>"

    def short_desc(self) -> str:
        return "Run a spider"

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        """
        Runs the spider with the specified arguments and options.

        Validates the input arguments and starts the crawl process. If an error occurs, 
        the process is stopped, and an appropriate exit code is set.

        Args:
            args (list[str]): The command-line arguments passed to the command.
            opts (argparse.Namespace): The parsed command-line options.

        Raises:
            UsageError: If invalid arguments are provided (e.g., more than one spider).
        """
        if len(args) < 1:
            raise UsageError("Spider name is required.")
        if len(args) > 1:
            raise UsageError(
                "Running 'scrapy crawl' with more than one spider is not supported"
            )
        spname = args[0]

        assert self.crawler_process
        crawl_defer = self.crawler_process.crawl(spname, **opts.spargs)

        # If there was an exception during crawl, set exit code to 1
        if getattr(crawl_defer, "result", None) is not None and issubclass(
            cast(Failure, crawl_defer.result).type, Exception
        ):
            self.exitcode = 1
        else:
            self.crawler_process.start()

            # If the crawler process has failed to bootstrap or encountered an exception
            if (
                self.crawler_process.bootstrap_failed
                or hasattr(self.crawler_process, "has_exception")
                and self.crawler_process.has_exception
            ):
                self.exitcode = 1
