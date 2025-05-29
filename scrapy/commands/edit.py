import argparse
import os
import sys

from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.spiderloader import get_spider_loader


class Command(ScrapyCommand):
    requires_project = True
    requires_crawler_process = False
    default_settings = {"LOG_ENABLED": False}

    def syntax(self) -> str:
        return "<spider>"

    def short_desc(self) -> str:
        return "Edit spider"

    def long_desc(self) -> str:
        return (
            "Edit a spider using the editor defined in the EDITOR environment"
            " variable or else the EDITOR setting"
        )

    def _err(self, msg: str) -> None:
        sys.stderr.write(msg + os.linesep)
        self.exitcode = 1

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        if len(args) != 1:
            raise UsageError

        assert self.settings is not None
        editor = self.settings["EDITOR"]
        spider_loader = get_spider_loader(self.settings)
        try:
            spidercls = spider_loader.load(args[0])
        except KeyError:
            self._err(f"Spider not found: {args[0]}")
            return

        sfile = sys.modules[spidercls.__module__].__file__
        assert sfile
        sfile = sfile.replace(".pyc", ".py")
        self.exitcode = os.system(f'{editor} "{sfile}"')  # noqa: S605
