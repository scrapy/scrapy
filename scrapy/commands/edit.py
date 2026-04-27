import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.spiderloader import get_spider_loader


def edit_file(editor: str, file_path: str | Path) -> int:
    active_editor = editor or os.environ.get('EDITOR')

    if not active_editor:
        if sys.platform == 'win32':
            active_editor = 'notepad'
        else:
            active_editor = 'vi'

    if "%s" in active_editor:
        active_editor = active_editor.replace("%s", sys.executable)

    try:
        if sys.platform == 'win32':
            command = [*shlex.split(active_editor, posix=False), str(file_path)]
        else:
            command = [*shlex.split(active_editor), str(file_path)]

        return subprocess.call(command)

    except FileNotFoundError:
        # 3. Messaggio amichevole se l'editor non esiste
        print(f"Error: Could not find the editor '{active_editor}'.", file=sys.stderr)
        print("Please set the EDITOR environment variable to your preferred text editor.", file=sys.stderr)
        return 1



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
        self.exitcode = edit_file(editor, sfile)
