from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from scrapy import Spider
from scrapy.addons import AddonManager
from scrapy.commands import ScrapyCommand
from scrapy.crawler import Crawler
from scrapy.exceptions import UsageError
from scrapy.settings import BaseSettings
from scrapy.spiderloader import get_spider_loader

if TYPE_CHECKING:
    import argparse

    from scrapy.settings import Settings


class Command(ScrapyCommand):
    requires_crawler_process = False
    default_settings: ClassVar[dict[str, Any]] = {"LOG_ENABLED": False}

    def syntax(self) -> str:
        return "[options]"

    def short_desc(self) -> str:
        return "Get settings values"

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        super().add_options(parser)
        parser.add_argument(
            "--get", dest="get", metavar="SETTING", help="print raw setting value"
        )
        parser.add_argument(
            "--getbool",
            dest="getbool",
            metavar="SETTING",
            help="print setting value, interpreted as a boolean",
        )
        parser.add_argument(
            "--getint",
            dest="getint",
            metavar="SETTING",
            help="print setting value, interpreted as an integer",
        )
        parser.add_argument(
            "--getfloat",
            dest="getfloat",
            metavar="SETTING",
            help="print setting value, interpreted as a float",
        )
        parser.add_argument(
            "--getlist",
            dest="getlist",
            metavar="SETTING",
            help="print setting value, interpreted as a list",
        )
        parser.add_argument(
            "--spider",
            dest="spider",
            metavar="SPIDER",
            help="also apply the settings of this spider",
        )

    def _build_settings(self, spider_name: str | None) -> Settings:
        """Return the settings as they would be during a crawl."""
        assert self.settings is not None
        # Must run before get_spider_loader(), because add-ons may change
        # SPIDER_MODULES and other pre-crawler settings that it relies on.
        AddonManager.load_pre_crawler_settings(self.settings)
        spidercls: type[Spider] = Spider
        if spider_name is not None:
            try:
                spidercls = get_spider_loader(self.settings).load(spider_name)
            except KeyError:
                raise UsageError(f"Unable to find spider: {spider_name}") from None
        # Building a Crawler applies the spider settings and does not install a
        # reactor or build any component.
        crawler = Crawler(spidercls, self.settings)
        crawler.addons.load_settings(crawler.settings)
        return crawler.settings

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        settings = self._build_settings(opts.spider)
        if opts.get:
            s = settings.get(opts.get)
            if isinstance(s, BaseSettings):
                print(json.dumps(s.copy_to_dict()))
            else:
                print(s)
        elif opts.getbool:
            print(settings.getbool(opts.getbool))
        elif opts.getint:
            print(settings.getint(opts.getint))
        elif opts.getfloat:
            print(settings.getfloat(opts.getfloat))
        elif opts.getlist:
            print(settings.getlist(opts.getlist))
