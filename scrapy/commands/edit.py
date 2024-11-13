import argparse
import os
import sys

from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError


class Command(ScrapyCommand):
    """Command to open a spider in an editor for editing within a Scrapy project."""

    requires_project = True
    default_settings = {"LOG_ENABLED": False}

    def syntax(self) -> str:
        """Return the syntax for using the command."""
        return "<spider>"

    def short_desc(self) -> str:
        """Return a short description of the command."""
        return "Edit spider"

    def long_desc(self) -> str:
        """Return a detailed description of the command's purpose."""
        return (
            "Edit a spider using the editor defined in the EDITOR environment"
            " variable or else the EDITOR setting"
        )

    def _err(self, msg: str) -> None:
        """Print an error message to standard error and set the exit code.
        
        Args:
            msg (str): The error message to print.
        """
        sys.stderr.write(msg + os.linesep)
        self.exitcode = 1

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        """Run the command to open a spider file for editing.
        
        Args:
            args (list[str]): List containing the name of the spider to edit.
            opts (argparse.Namespace): Parsed command-line options.
        
        Raises:
            UsageError: If the number of arguments is not equal to one.
        """
        if len(args) != 1:
            raise UsageError("A single spider name must be specified.")

        editor = self.settings["EDITOR"]
        assert self.crawler_process
        try:
            spidercls = self.crawler_process.spider_loader.load(args[0])
        except KeyError:
            return self._err(f"Spider not found: {args[0]}")

        sfile = sys.modules[spidercls.__module__].__file__
        assert sfile
        sfile = sfile.replace(".pyc", ".py")
        self.exitcode = os.system(f'{editor} "{sfile}"')  # nosec