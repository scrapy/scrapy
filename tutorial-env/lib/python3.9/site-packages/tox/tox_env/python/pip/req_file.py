from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .req.file import ParsedRequirement, ReqFileLines, RequirementsFile

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace
    from pathlib import Path
    from typing import Final


class PythonDeps(RequirementsFile):
    # these options are valid in requirements.txt, but not via pip cli and
    # thus cannot be used in the testenv `deps` list
    _illegal_options: Final[list[str]] = ["hash"]

    def __init__(self, raw: str, root: Path) -> None:
        super().__init__(root / "tox.ini", constraint=False)
        self._raw = self._normalize_raw(raw)
        self._unroll: tuple[list[str], list[str]] | None = None
        self._req_parser_: RequirementsFile | None = None

    def _extend_parser(self, parser: ArgumentParser) -> None:
        parser.add_argument("--no-deps", action="store_true", dest="no_deps", default=False)

    def _merge_option_line(self, base_opt: Namespace, opt: Namespace, filename: str) -> None:
        super()._merge_option_line(base_opt, opt, filename)
        if getattr(opt, "no_deps", False):  # if the option comes from a requirements file this flag is missing there
            base_opt.no_deps = True

    def _option_to_args(self, opt: Namespace) -> list[str]:
        result = super()._option_to_args(opt)
        if getattr(opt, "no_deps", False):
            result.append("--no-deps")
        return result

    @property
    def _req_parser(self) -> RequirementsFile:
        if self._req_parser_ is None:
            self._req_parser_ = RequirementsFile(path=self._path, constraint=False)
        return self._req_parser_

    def _get_file_content(self, url: str) -> str:
        if self._is_url_self(url):
            return self._raw
        return super()._get_file_content(url)

    def _is_url_self(self, url: str) -> bool:
        return url == str(self._path)

    def _pre_process(self, content: str) -> ReqFileLines:
        for at, line in super()._pre_process(content):
            if line.startswith("-r") or line.startswith("-c") and line[2].isalpha():
                found_line = f"{line[0:2]} {line[2:]}"
            else:
                found_line = line
            yield at, found_line

    def lines(self) -> list[str]:
        return self._raw.splitlines()

    @staticmethod
    def _normalize_raw(raw: str) -> str:
        # a line ending in an unescaped \ is treated as a line continuation and the newline following it is effectively
        # ignored
        raw = "".join(raw.replace("\r", "").split("\\\n"))
        # for tox<4 supporting requirement/constraint files via -rreq.txt/-creq.txt
        lines: list[str] = [PythonDeps._normalize_line(line) for line in raw.splitlines()]
        adjusted = "\n".join(lines)
        return f"{adjusted}\n" if raw.endswith("\\\n") else adjusted  # preserve trailing newline if input has it

    @staticmethod
    def _normalize_line(line: str) -> str:
        arg_match = next(
            (
                arg
                for arg in ONE_ARG
                if line.startswith(arg)
                and len(line) > len(arg)
                and not (line[len(arg)].isspace() or line[len(arg)] == "=")
            ),
            None,
        )
        if arg_match is not None:
            line = f"{arg_match} {line[len(arg_match):]}"
        # escape spaces
        escape_match = next((e for e in ONE_ARG_ESCAPE if line.startswith(e) and line[len(e)].isspace()), None)
        if escape_match is not None:
            # escape not already escaped spaces
            escaped = re.sub(r"(?<!\\)(\s)", r"\\\1", line[len(escape_match) + 1 :])
            line = f"{line[:len(escape_match)]} {escaped}"
        return line

    def _parse_requirements(self, opt: Namespace, recurse: bool) -> list[ParsedRequirement]:  # noqa: FBT001
        # check for any invalid options in the deps list
        # (requirements recursively included from other files are not checked)
        requirements = super()._parse_requirements(opt, recurse)
        for req in requirements:
            if req.from_file != str(self.path):
                continue
            for illegal_option in self._illegal_options:
                if req.options.get(illegal_option):
                    msg = f"Cannot use --{illegal_option} in deps list, it must be in requirements file. ({req})"
                    raise ValueError(msg)
        return requirements

    def unroll(self) -> tuple[list[str], list[str]]:
        if self._unroll is None:
            opts_dict = vars(self.options)
            if not self.requirements and opts_dict:
                msg = "no dependencies"
                raise ValueError(msg)
            result_opts: list[str] = [f"{key}={value}" for key, value in opts_dict.items()]
            result_req = [str(req) for req in self.requirements]
            self._unroll = result_opts, result_req
        return self._unroll

    @classmethod
    def factory(cls, root: Path, raw: object) -> PythonDeps:
        if not isinstance(raw, str):
            raise TypeError(raw)
        return cls(raw, root)


ONE_ARG = {
    "-i",
    "--index-url",
    "--extra-index-url",
    "-e",
    "--editable",
    "-c",
    "--constraint",
    "-r",
    "--requirement",
    "-f",
    "--find-links",
    "--trusted-host",
    "--use-feature",
    "--no-binary",
    "--only-binary",
}
ONE_ARG_ESCAPE = {
    "-c",
    "--constraint",
    "-r",
    "--requirement",
    "-f",
    "--find-links",
    "-e",
    "--editable",
}

__all__ = (
    "PythonDeps",
    "ONE_ARG",
)
