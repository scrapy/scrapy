import argparse
from typing import List, cast

from twisted.python.failure import Failure

from scrapy.commands import BaseRunSpiderCommand
from scrapy.exceptions import UsageError


class Command(BaseRunSpiderCommand):
    requires_project = True

    def syntax(self) -> str:
        return "[options] <spider>"

    def short_desc(self) -> str:
        return "Run a spider"

    def run(self, args: List[str], opts: argparse.Namespace) -> None:
        if len(args) < 1:
            raise UsageError()
        elif len(args) > 1:
            raise UsageError(
                "running 'scrapy crawl' with more than one spider is not supported"
            )
        self.validate_feed_exporter(opts)
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
