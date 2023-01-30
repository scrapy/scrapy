import os
import sys

from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError


class Command(ScrapyCommand):

    requires_project = True
    default_settings = {"LOG_ENABLED": False}

    def syntax(self):
        return "<spider>"

    def short_desc(self):
        return "Edit spider"

    def long_desc(self):
        return (
            "Edit a spider using the editor defined in the EDITOR environment"
            " variable or else the EDITOR setting"
        )

    def _err(self, msg):
        sys.stderr.write(msg + os.linesep)
        self.exitcode = 1

    def run(self, args, opts):
        if len(args) != 1:
            raise UsageError()

        editor = self.settings["EDITOR"]
        try:
            spidercls = self.crawler_process.spider_loader.load(args[0])
        except KeyError:
            return self._err(f"Spider not found: {args[0]}")

        sfile = sys.modules[spidercls.__module__].__file__
        sfile = sfile.replace(".pyc", ".py")
        self.exitcode = os.system(f'{editor} "{sfile}"')
