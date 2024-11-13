import argparse
import os
import sys

from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError


class Command(ScrapyCommand):
    """
    Command to open a spider file in the system editor.

    Uses the editor defined in the EDITOR environment variable or the Scrapy 
    EDITOR setting.
    """
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
        """
        Runs the command to open the specified spider in an editor.

        Validates the spider name, checks for the editor setting, and attempts
        to open the spider file. Raises UsageError if no spider name is provided.

        Args:
            args (list[str]): Command-line arguments.
            opts (argparse.Namespace): Parsed command-line options.

        Raises:
            UsageError: If an incorrect number of arguments is provided.
        """
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
