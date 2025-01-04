from __future__ import annotations

from typing import TYPE_CHECKING, cast

from twisted.python.failure import Failure

from scrapy.commands import BaseRunSpiderCommand
from scrapy.exceptions import UsageError

if TYPE_CHECKING:
    import argparse


class Command(BaseRunSpiderCommand):
    requires_project = True

    def syntax(self) -> str:
        return "[options] <spider>"

    def short_desc(self) -> str:
        return "Run a spider"

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        if len(args) < 1:
            raise UsageError
        if len(args) > 1:
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

            if self.crawler_process.bootstrap_failed or (
                hasattr(self.crawler_process, "has_exception")
                and self.crawler_process.has_exception
            ):
                self.exitcode = 1
