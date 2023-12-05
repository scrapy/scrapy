"""Adapted from the pip code base."""
from __future__ import annotations

import os
import re
import shlex
import sys
import urllib.parse
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import IO, Any, Iterator, List, Tuple, cast
from urllib.request import urlopen

import chardet
from packaging.requirements import InvalidRequirement, Requirement

from .args import build_parser
from .util import VCS, get_url_scheme, is_url, url_to_path

# Matches environment variable-style values in '${MY_VARIABLE_1}' with the variable name consisting of only uppercase
# letters, digits or the '_' (underscore). This follows the POSIX standard defined in IEEE Std 1003.1, 2013 Edition.
_ENV_VAR_RE = re.compile(r"(?P<var>\${(?P<name>[A-Z0-9_]+)})")
_SCHEME_RE = re.compile(r"^(http|https|file):", re.I)
_COMMENT_RE = re.compile(r"(^|\s+)#.*$")
# https://www.python.org/dev/peps/pep-0508/#extras
_EXTRA_PATH = re.compile(r"(.*)\[([-._,\sa-zA-Z0-9]*)]")
_EXTRA_ELEMENT = re.compile(r"[a-zA-Z0-9]*[-._a-zA-Z0-9]")
ReqFileLines = Iterator[Tuple[int, str]]

DEFAULT_INDEX_URL = "https://pypi.org/simple"


class ParsedRequirement:
    def __init__(self, req: str, options: dict[str, Any], from_file: str, lineno: int) -> None:  # noqa: PLR0912
        req = req.encode("utf-8").decode("utf-8")
        try:
            self._requirement: Requirement | Path | str = Requirement(req)
        except InvalidRequirement:
            if is_url(req) or any(req.startswith(f"{v}+") and is_url(req[len(v) + 1 :]) for v in VCS):
                self._requirement = req
            else:
                root = Path(from_file).parent
                extras: list[str] = []
                match = _EXTRA_PATH.fullmatch(Path(req).name)
                if match:
                    for extra in match.group(2).split(","):
                        extra = extra.strip()  # noqa: PLW2901
                        if not extra:
                            continue
                        if not _EXTRA_ELEMENT.fullmatch(extra):
                            extras = []
                            path = root / req
                            break
                        extras.append(extra)
                    else:
                        path = root / Path(req).parent / match.group(1)
                else:
                    path = root / req
                extra_part = f"[{','.join(sorted(extras))}]" if extras else ""
                try:
                    rel_path = str(path.resolve().relative_to(root))
                    # prefix paths in cwd to not convert them to requirement
                    if rel_path != "." and os.sep not in rel_path:
                        rel_path = f".{os.sep}{rel_path}"
                except ValueError:
                    rel_path = str(path.resolve())

                self._requirement = f"{rel_path}{extra_part}"
        self._options = options
        self._from_file = from_file
        self._lineno = lineno

    @property
    def requirement(self) -> Requirement | Path | str:
        return self._requirement

    @property
    def from_file(self) -> str:
        return self._from_file

    @property
    def lineno(self) -> int:
        return self._lineno

    @property
    def options(self) -> dict[str, Any]:
        return self._options

    def __repr__(self) -> str:
        base = f"{self.__class__.__name__}(requirement={self._requirement}, "
        if self._options:
            base += f"options={self._options!r}, "
        return f"{base.rstrip(', ')})"

    def __str__(self) -> str:
        result = []
        if self.options.get("is_constraint"):
            result.append("-c")
        if self.options.get("is_editable"):
            result.append("-e")
        result.append(str(self.requirement))
        for hash_value in self.options.get("hash", []):
            result.extend(("--hash", hash_value))
        return " ".join(result)

    def as_args(self) -> Iterator[str]:
        if self.options.get("is_editable"):
            yield "-e"
        yield str(self._requirement)


class ParsedLine:
    def __init__(  # noqa: PLR0913
        self,
        filename: str,
        lineno: int,
        args: str,
        opts: Namespace,
        constraint: bool,  # noqa: FBT001
    ) -> None:
        self.filename = filename
        self.lineno = lineno
        self.opts = opts
        self.constraint = constraint
        if args:
            self.is_requirement = True
            self.is_editable = False
            self.requirement = args
        elif opts.editables:
            self.is_requirement = True
            self.is_editable = True
            # We don't support multiple -e on one line
            self.requirement = opts.editables[0]
        else:
            self.is_requirement = False


class RequirementsFile:
    def __init__(self, path: Path, constraint: bool) -> None:  # noqa: FBT001
        self._path = path
        self._is_constraint: bool = constraint
        self._opt = Namespace()
        self._requirements: list[ParsedRequirement] | None = None
        self._as_root_args: list[str] | None = None
        self._parser_private: ArgumentParser | None = None

    @property
    def _req_parser(self) -> RequirementsFile:
        return self

    def __str__(self) -> str:
        return f"{'-c' if self.is_constraint else '-r'} {self.path}"

    @property
    def path(self) -> Path:
        return self._path

    @property
    def is_constraint(self) -> bool:
        return self._is_constraint

    @property
    def options(self) -> Namespace:
        self._ensure_requirements_parsed()
        return self._opt

    @property
    def requirements(self) -> list[ParsedRequirement]:
        self._ensure_requirements_parsed()
        return cast(List[ParsedRequirement], self._requirements)

    @property
    def _parser(self) -> ArgumentParser:
        if self._parser_private is None:
            self._parser_private = build_parser()
            self._extend_parser(self._parser_private)
        return self._parser_private

    def _extend_parser(self, parser: ArgumentParser) -> None:
        ...

    def _ensure_requirements_parsed(self) -> None:
        if self._requirements is None:
            self._requirements = self._parse_requirements(opt=self._opt, recurse=True)

    def _parse_requirements(self, opt: Namespace, recurse: bool) -> list[ParsedRequirement]:  # noqa: FBT001
        result, found = [], set()
        for parsed_line in self._parse_and_recurse(str(self._path), self.is_constraint, recurse):
            if parsed_line.is_requirement:
                parsed_req = self._handle_requirement_line(parsed_line)
                key = str(parsed_req)
                if key not in found:
                    found.add(key)
                    result.append(parsed_req)
            else:
                self._merge_option_line(opt, parsed_line.opts, parsed_line.filename)
        result.sort(key=self._key_func)
        return result

    def _key_func(self, line: ParsedRequirement) -> tuple[int, tuple[int, str, str]]:
        of_type = {Requirement: 0, Path: 1, str: 2}[type(line.requirement)]
        between = of_type, str(line.requirement).lower(), str(line.options)
        if "is_constraint" in line.options:
            return 2, between
        if "is_editable" in line.options:
            return 1, between
        return 0, between

    def _parse_and_recurse(
        self,
        filename: str,
        constraint: bool,  # noqa: FBT001
        recurse: bool,  # noqa: FBT001
    ) -> Iterator[ParsedLine]:
        for line in self._parse_file(filename, constraint):
            if not line.is_requirement and (line.opts.requirements or line.opts.constraints):
                if line.opts.requirements:  # parse a nested requirements file
                    nested_constraint, req_path = False, line.opts.requirements[0]
                else:
                    nested_constraint, req_path = True, line.opts.constraints[0]
                if _SCHEME_RE.search(filename):  # original file is over http
                    req_path = urllib.parse.urljoin(filename, req_path)  # do a url join so relative paths work
                elif not _SCHEME_RE.search(req_path):  # original file and nested file are paths
                    req_path = str(Path(filename).parent / req_path)  # do a join so relative paths work
                if recurse:
                    yield from self._req_parser._parse_and_recurse(req_path, nested_constraint, recurse)  # noqa: SLF001
                else:
                    line.filename = req_path
                    yield line
            else:
                yield line

    def _parse_file(self, url: str, constraint: bool) -> Iterator[ParsedLine]:  # noqa: FBT001
        content = self._get_file_content(url)
        for line_number, line in self._pre_process(content):
            args_str, opts = self._parse_line(line)
            yield ParsedLine(url, line_number, args_str, opts, constraint)

    def _get_file_content(self, url: str) -> str:
        """
        Gets the content of a file; it may be a filename, file: URL, or http: URL.  Returns (location, content).
        Content is unicode. Respects # -*- coding: declarations on the retrieved files.

        :param url:         File path or url.
        """
        scheme = get_url_scheme(url)
        if scheme in ["http", "https"]:
            with urlopen(url) as response:  # noqa: S310
                return self._read_decode(response)
        elif scheme == "file":
            url = url_to_path(url)
        try:
            with Path(url).open("rb") as file_handler:
                text = self._read_decode(file_handler)
        except OSError as exc:
            msg = f"Could not open requirements file {url}: {exc}"
            raise ValueError(msg) from exc
        return text

    @staticmethod
    def _read_decode(file_handler: IO[bytes]) -> str:
        raw = file_handler.read()
        if not raw:
            return ""
        codec = chardet.detect(raw)["encoding"]
        return raw.decode(codec)

    def _pre_process(self, content: str) -> ReqFileLines:
        """
        Split, filter, and join lines, and return a line iterator.

        :param content: the content of the requirements file
        """
        lines_enum: ReqFileLines = enumerate(content.splitlines(), start=1)
        lines_enum = self._join_lines(lines_enum)
        lines_enum = self._ignore_comments(lines_enum)
        return self._expand_env_variables(lines_enum)

    def _parse_line(self, line: str) -> tuple[str, Namespace]:
        args_str, options_str = self._break_args_options(line)
        args = shlex.split(options_str, posix=sys.platform != "win32")
        opts = self._parser.parse_args(args)
        return args_str, opts

    @staticmethod
    def _handle_requirement_line(line: ParsedLine) -> ParsedRequirement:
        # For editable requirements, we don't support per-requirement options, so just return the parsed requirement.
        # get the options that apply to requirements
        req_options: dict[str, Any] = {}
        if line.is_editable:
            req_options["is_editable"] = line.is_editable
        if line.constraint:
            req_options["is_constraint"] = line.constraint
        hash_values = getattr(line.opts, "hash", [])
        if hash_values:
            req_options["hash"] = hash_values
        return ParsedRequirement(line.requirement, req_options, line.filename, line.lineno)

    def _merge_option_line(  # noqa: C901, PLR0912, PLR0915
        self,
        base_opt: Namespace,
        opt: Namespace,
        filename: str,
    ) -> None:
        # percolate options upward
        if opt.requirements:
            if not hasattr(base_opt, "requirements"):
                base_opt.requirements = []
            if opt.requirements[0] not in base_opt.requirements:
                base_opt.requirements.append(opt.requirements[0])
        if opt.constraints:
            if not hasattr(base_opt, "constraints"):
                base_opt.constraints = []
            if opt.constraints[0] not in base_opt.constraints:
                base_opt.constraints.append(opt.constraints[0])
        if opt.require_hashes:
            base_opt.require_hashes = True
        if opt.features_enabled:
            if not hasattr(base_opt, "features_enabled"):
                base_opt.features_enabled = []
            for feature in opt.features_enabled:
                if feature not in base_opt.features_enabled:
                    base_opt.features_enabled.append(feature)
            base_opt.features_enabled.sort()
        if opt.index_url:
            if getattr(base_opt, "index_url", []):
                base_opt.index_url[0] = opt.index_url
            else:
                base_opt.index_url = [opt.index_url]
        if opt.no_index is True:
            base_opt.index_url = []
        if opt.extra_index_url:
            if not getattr(base_opt, "index_url", []):
                base_opt.index_url = [DEFAULT_INDEX_URL]
            for url in opt.extra_index_url:
                if url not in base_opt.index_url:
                    base_opt.index_url.extend(opt.extra_index_url)
        if opt.find_links:
            # relative to a requirements file.
            if not hasattr(base_opt, "find_links"):
                base_opt.find_links = []
            value = opt.find_links[0]
            req_dir = Path(filename).absolute().parent
            relative_to_reqs_file = req_dir / value
            if os.path.exists(str(relative_to_reqs_file)):  # noqa: PTH110 # Path.exists fails on win32 <=3.7 with URI
                value = str(relative_to_reqs_file)  # pragma: no cover
            if value not in base_opt.find_links:
                base_opt.find_links.append(value)
        if opt.pre:
            base_opt.pre = True
        if opt.prefer_binary:
            base_opt.prefer_binary = True
        for host in opt.trusted_host or []:
            if not hasattr(base_opt, "trusted_hosts"):
                base_opt.trusted_hosts = []
            if host not in base_opt.trusted_hosts:
                base_opt.trusted_hosts.append(host)
        if opt.no_binary:
            base_opt.no_binary = opt.no_binary
        if opt.only_binary:
            base_opt.only_binary = opt.only_binary

    @staticmethod
    def _break_args_options(line: str) -> tuple[str, str]:
        """
        Break up the line into an args and options string.  We only want to shlex (and then optparse) the options, not
        the args. args can contain markers which are corrupted by shlex.
        """
        tokens = line.split(" ")
        args = []
        options = tokens[:]
        for token in tokens:
            if token.startswith("-"):  # both `-` and `--` accepted
                break
            args.append(token)
            options.pop(0)
        return " ".join(args).strip(), " ".join(options)

    @staticmethod
    def _join_lines(lines_enum: ReqFileLines) -> ReqFileLines:
        """
        Joins a line ending in '\' with the previous line (except when following comments). The joined line takes on the
        index of the first line.
        """
        primary_line_number = None
        new_line: list[str] = []
        for line_number, line in lines_enum:
            if not line.endswith("\\") or _COMMENT_RE.match(line):
                if _COMMENT_RE.match(line):
                    line = f" {line}"  # noqa: PLW2901 # this ensures comments are always matched later
                if new_line:
                    new_line.append(line)
                    assert primary_line_number is not None  # noqa: S101
                    yield primary_line_number, "".join(new_line)
                    new_line = []
                else:
                    yield line_number, line
            else:
                if not new_line:  # pragma: no branch
                    primary_line_number = line_number
                new_line.append(line.strip("\\"))
        # last line contains \
        if new_line:
            assert primary_line_number is not None  # noqa: S101
            yield primary_line_number, "".join(new_line)

    @staticmethod
    def _ignore_comments(lines_enum: ReqFileLines) -> ReqFileLines:
        """Strips comments and filter empty lines."""
        for line_number, line in lines_enum:
            processed_line = _COMMENT_RE.sub("", line).strip()
            if processed_line:
                yield line_number, processed_line

    @staticmethod
    def _expand_env_variables(lines_enum: ReqFileLines) -> ReqFileLines:
        """
        Replace all environment variables that can be retrieved via `os.getenv`.

        The only allowed format for environment variables defined in the requirement file is `${MY_VARIABLE_1}` to
        ensure two things:

        1. Strings that contain a `$` aren't accidentally (partially) expanded.
        2. Ensure consistency across platforms for requirement files.

        These points are the result of a discussion on the `github pull request #3514
        <https://github.com/pypa/pip/pull/3514>`_. Valid characters in variable names follow the `POSIX standard
        <http://pubs.opengroup.org/onlinepubs/9699919799/>`_ and are limited to uppercase letter, digits and the `_`.
        """
        for line_number, line in lines_enum:
            expanded_line = line
            for env_var, var_name in _ENV_VAR_RE.findall(expanded_line):
                value = os.getenv(var_name)
                if not value:
                    continue
                expanded_line = expanded_line.replace(env_var, value)
            yield line_number, expanded_line

    @property
    def as_root_args(self) -> list[str]:
        if self._as_root_args is None:
            opt = Namespace()
            result: list[str] = []
            for req in self._parse_requirements(opt=opt, recurse=False):
                result.extend(req.as_args())
            option_args = self._option_to_args(opt)
            result.extend(option_args)

            self._as_root_args = result
        return self._as_root_args

    def _option_to_args(self, opt: Namespace) -> list[str]:  # noqa: C901, PLR0912
        result: list[str] = []
        for req in getattr(opt, "requirements", []):
            result.extend(("-r", req))
        for req in getattr(opt, "constraints", []):
            result.extend(("-c", req))
        index_url = getattr(opt, "index_url", None)
        if index_url is not None:
            if index_url:
                if index_url[0] != DEFAULT_INDEX_URL:
                    result.extend(("-i", index_url[0]))
                for url in index_url[1:]:
                    result.extend(("--extra-index-url", url))
            else:
                result.append("--no-index")
        for link in getattr(opt, "find_links", []):
            result.extend(("-f", link))
        if hasattr(opt, "pre"):
            result.append("--pre")
        for host in getattr(opt, "trusted_hosts", []):
            result.extend(("--trusted-host", host))
        if hasattr(opt, "prefer_binary"):
            result.append("--prefer-binary")
        if hasattr(opt, "require_hashes"):
            result.append("--require-hashes")
        for feature in getattr(opt, "features_enabled", []):
            result.extend(("--use-feature", feature))
        if hasattr(opt, "no_binary"):
            result.extend(("--no-binary", opt.no_binary))
        if hasattr(opt, "only_binary"):
            result.extend(("--only-binary", opt.only_binary))
        return result


__all__ = (
    "RequirementsFile",
    "ReqFileLines",
    "ParsedRequirement",
)
