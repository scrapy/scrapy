from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING, Any, ClassVar

from scrapy.commands import ScrapyCommand
from scrapy.exceptions import UsageError
from scrapy.utils.curl import curl_to_request_kwargs

if TYPE_CHECKING:
    import argparse


class Command(ScrapyCommand):
    requires_crawler_process = False
    default_settings: ClassVar[dict[str, Any]] = {"LOG_ENABLED": False}

    def syntax(self) -> str:
        return "[<curl command>]"

    def short_desc(self) -> str:
        return "Generate the Python code of a Request equivalent to a curl command"

    def long_desc(self) -> str:
        return (
            "Generate the Python code of a Request equivalent to a curl "
            "command. If the curl command is not given as an argument, it "
            "is read from the system clipboard."
        )

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        if len(args) > 1:
            raise UsageError
        curl_command = args[0] if args else _read_clipboard()
        try:
            request_kwargs = curl_to_request_kwargs(curl_command)
        except ValueError as e:
            raise UsageError(str(e), print_help=False) from e
        kwargs_repr = ", ".join(f"{k}={v!r}" for k, v in request_kwargs.items())
        code = f"Request({kwargs_repr})"
        print(_format_code(code).rstrip("\n"))


def _format_code(code: str) -> str:
    ruff = shutil.which("ruff")
    if ruff is None:
        return code
    try:
        result = subprocess.run(  # noqa: S603
            [ruff, "format", "-"],
            input=code,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return code
    return result.stdout


def _read_clipboard() -> str:
    try:
        import pyperclip  # noqa: PLC0415
    except ImportError:
        raise UsageError(
            "No curl command given, and the pyperclip package is not "
            "installed to read one from the system clipboard. Pass the "
            "curl command as an argument, or install the scrapy[clipboard] "
            "extra.",
            print_help=False,
        ) from None
    return str(pyperclip.paste()).strip()
