import argparse
import os
import sys

from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError


class Command(ScrapyCommand):
    requires_project = True
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
            raise UsageError()

        editor = self.settings["EDITOR"]
        assert self.crawler_process
        try:
            spidercls = self.crawler_process.spider_loader.load(args[0])
        except KeyError:
            self._err(f"Spider not found: {args[0]}")
            return

        sfile = sys.modules[spidercls.__module__].__file__
        assert sfile
        sfile = sfile.replace(".pyc", ".py")
        self.exitcode = os.system(f'{editor} "{sfile}"')  # nosec
