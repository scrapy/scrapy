from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.commands import BaseRunSpiderCommand
from scrapy.exceptions import UsageError

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterable


class Command(BaseRunSpiderCommand):
    requires_project = True

    def syntax(self) -> str:
        return "[options] <spider>"

    def short_desc(self) -> str:
        return "Run a spider of the current project, by name"

    def complete_argument(self, args: list[str]) -> Iterable[str]:
        return () if args else self._spider_names()

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        if len(args) < 1:
            raise UsageError
        if len(args) > 1:
            raise UsageError(
                "running 'scrapy crawl' with more than one spider is not supported"
            )
        spname = args[0]

        assert self.crawler_process
        self.crawler_process.crawl(spname, **opts.spargs)
        self.crawler_process.start()
        if self.crawler_process.bootstrap_failed:
            self.exitcode = 1
