from __future__ import annotations

import logging
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING

from tox.report import HandledError

from .legacy_toml import LegacyToml
from .setup_cfg import SetupCfg
from .tox_ini import ToxIni

if TYPE_CHECKING:
    from .api import Source

SOURCE_TYPES: tuple[type[Source], ...] = (ToxIni, SetupCfg, LegacyToml)


def discover_source(config_file: Path | None, root_dir: Path | None) -> Source:
    """
    Discover a source for configuration.

    :param config_file: the file storing the source
    :param root_dir: the root directory as set by the user (None means not set)
    :return: the source of the config
    """
    if config_file is None:
        src = _locate_source()
        if src is None:
            src = _create_default_source(root_dir)
    elif config_file.is_dir():
        src = None
        for src_type in SOURCE_TYPES:
            candidate: Path = config_file / src_type.FILENAME
            try:
                src = src_type(candidate)
                break
            except ValueError:
                continue
        if src is None:
            msg = f"could not find any config file in {config_file}"
            raise HandledError(msg)
    else:
        src = _load_exact_source(config_file)
    return src


def _locate_source() -> Source | None:
    folder = Path.cwd()
    for base in chain([folder], folder.parents):
        for src_type in SOURCE_TYPES:
            candidate: Path = base / src_type.FILENAME
            try:
                return src_type(candidate)
            except ValueError:
                pass
    return None


def _load_exact_source(config_file: Path) -> Source:
    # if the filename matches to the letter some config file name do not fallback to other source types
    exact_match = next((s for s in SOURCE_TYPES if config_file.name == s.FILENAME), None)  # pragma: no cover
    for src_type in (exact_match,) if exact_match is not None else SOURCE_TYPES:  # pragma: no branch
        try:
            return src_type(config_file)
        except ValueError:  # noqa: PERF203
            pass
    msg = f"could not recognize config file {config_file}"
    raise HandledError(msg)


def _create_default_source(root_dir: Path | None) -> Source:
    if root_dir is None:  # if set use that
        empty = Path.cwd()
        for base in chain([empty], empty.parents):
            if (base / "pyproject.toml").exists():
                empty = base
                break
    else:  # if not set use where we find pyproject.toml in the tree or cwd
        empty = root_dir
    logging.warning("No %s found, assuming empty tox.ini at %s", " or ".join(i.FILENAME for i in SOURCE_TYPES), empty)
    return ToxIni(empty / "tox.ini", content="")


__all__ = ("discover_source",)
