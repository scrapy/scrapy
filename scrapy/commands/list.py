import argparse
from typing import List

from scrapy.commands import ScrapyCommand


class Command(ScrapyCommand):
    requires_project = True
    default_settings = {"LOG_ENABLED": False}

    def short_desc(self) -> str:
        return "List available spiders"

    def run(self, args: List[str], opts: argparse.Namespace) -> None:
        assert self.crawler_process
        for s in sorted(self.crawler_process.spider_loader.list()):
            print(s)
