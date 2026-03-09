from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from scrapy.commands import BaseRunSpiderCommand
from scrapy.exceptions import ScrapyDeprecationWarning, UsageError

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
        assert self.settings

        spidercls = self.crawler_process.spider_loader.load(spname)
        custom = getattr(spidercls, "custom_settings", None)
        if (
            custom
            and custom.get("TWISTED_REACTOR")
            and not self.settings.getbool("FORCE_CRAWLER_PROCESS")
        ):
            warnings.warn(
                f"The spider {spname!r} sets TWISTED_REACTOR to "
                f"{custom['TWISTED_REACTOR']!r}, but this "
                "setting is ignored when running 'scrapy crawl'. To use the "
                "spider's reactor, either set FORCE_CRAWLER_PROCESS=True in "
                "your project settings, or use CrawlerRunner instead of "
                "CrawlerProcess.",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )

        self.crawler_process.crawl(spname, **opts.spargs)
        self.crawler_process.start()
        if self.crawler_process.bootstrap_failed:
            self.exitcode = 1
