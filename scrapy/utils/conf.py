from __future__ import annotations

import numbers
import os
import sys
from configparser import ConfigParser
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

from scrapy.exceptions import UsageError
from scrapy.settings import BaseSettings
from scrapy.utils.deprecate import update_classpath
from scrapy.utils.python import without_none_values

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping, MutableMapping


def build_component_list(
    compdict: MutableMapping[Any, Any],
    *,
    convert: Callable[[Any], Any] = update_classpath,
) -> list[Any]:
    """Compose a component list from a :ref:`component priority dictionary
    <component-priority-dictionaries>`."""

    def _check_components(complist: Collection[Any]) -> None:
        if len({convert(c) for c in complist}) != len(complist):
            raise ValueError(
                f"Some paths in {complist!r} convert to the same object, "
                "please update your settings"
            )

    def _map_keys(compdict: Mapping[Any, Any]) -> BaseSettings | dict[Any, Any]:
        if isinstance(compdict, BaseSettings):
            compbs = BaseSettings()
            for k, v in compdict.items():
                prio = compdict.getpriority(k)
                assert prio is not None
                if compbs.getpriority(convert(k)) == prio:
                    raise ValueError(
                        f"Some paths in {list(compdict.keys())!r} "
                        "convert to the same "
                        "object, please update your settings"
                    )
                compbs.set(convert(k), v, priority=prio)
            return compbs
        _check_components(compdict)
        return {convert(k): v for k, v in compdict.items()}

    def _validate_values(compdict: Mapping[Any, Any]) -> None:
        """Fail if a value in the components dict is not a real number or None."""
        for name, value in compdict.items():
            if value is not None and not isinstance(value, numbers.Real):
                raise ValueError(
                    f"Invalid value {value} for component {name}, "
                    "please provide a real number or None instead"
                )

    _validate_values(compdict)
    compdict = without_none_values(_map_keys(compdict))
    return [k for k, v in sorted(compdict.items(), key=itemgetter(1))]


def arglist_to_dict(arglist: list[str]) -> dict[str, str]:
    """Convert a list of arguments like ['arg1=val1', 'arg2=val2', ...] to a
    dict
    """
    return dict(x.split("=", 1) for x in arglist)


def closest_scrapy_cfg(
    path: str | os.PathLike = ".",
    prevpath: str | os.PathLike | None = None,
) -> str:
    """Return the path to the closest scrapy.cfg file by traversing the current
    directory and its parents
    """
    if prevpath is not None and str(path) == str(prevpath):
        return ""
    path = Path(path).resolve()
    cfgfile = path / "scrapy.cfg"
    if cfgfile.exists():
        return str(cfgfile)
    return closest_scrapy_cfg(path.parent, path)


def init_env(project: str = "default", set_syspath: bool = True) -> None:
    """Initialize environment to use command-line tool from inside a project
    dir. This sets the Scrapy settings module and modifies the Python path to
    be able to locate the project module.
    """
    cfg = get_config()
    if cfg.has_option("settings", project):
        os.environ["SCRAPY_SETTINGS_MODULE"] = cfg.get("settings", project)
    closest = closest_scrapy_cfg()
    if closest:
        projdir = str(Path(closest).parent)
        if set_syspath and projdir not in sys.path:
            sys.path.append(projdir)


def get_config(use_closest: bool = True) -> ConfigParser:
    """Get Scrapy config file as a ConfigParser"""
    sources = get_sources(use_closest)
    cfg = ConfigParser()
    cfg.read(sources)
    return cfg


def get_sources(use_closest: bool = True) -> list[str]:
    xdg_config_home = (
        os.environ.get("XDG_CONFIG_HOME") or Path("~/.config").expanduser()
    )
    sources = [
        "/etc/scrapy.cfg",
        r"c:\scrapy\scrapy.cfg",
        str(Path(xdg_config_home) / "scrapy.cfg"),
        str(Path("~/.scrapy.cfg").expanduser()),
    ]
    if use_closest:
        sources.append(closest_scrapy_cfg())
    return sources


def feed_complete_default_values_from_settings(
    feed: dict[str, Any], settings: BaseSettings
) -> dict[str, Any]:
    out = feed.copy()
    out.setdefault("batch_item_count", settings.getint("FEED_EXPORT_BATCH_ITEM_COUNT"))
    out.setdefault("encoding", settings["FEED_EXPORT_ENCODING"])
    out.setdefault("fields", settings.getdictorlist("FEED_EXPORT_FIELDS") or None)
    out.setdefault("store_empty", settings.getbool("FEED_STORE_EMPTY"))
    out.setdefault("uri_params", settings["FEED_URI_PARAMS"])
    out.setdefault("item_export_kwargs", {})
    if settings["FEED_EXPORT_INDENT"] is None:
        out.setdefault("indent", None)
    else:
        out.setdefault("indent", settings.getint("FEED_EXPORT_INDENT"))
    return out


def feed_process_params_from_cli(
    settings: BaseSettings,
    output: list[str],
    *,
    overwrite_output: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Receives feed export params (from the 'crawl' or 'runspider' commands),
    checks for inconsistencies in their quantities and returns a dictionary
    suitable to be used as the FEEDS setting.
    """
    valid_output_formats: Iterable[str] = without_none_values(
        cast(dict[str, str], settings.getwithbase("FEED_EXPORTERS"))
    ).keys()

    def check_valid_format(output_format: str) -> None:
        if output_format not in valid_output_formats:
            raise UsageError(
                f"Unrecognized output format '{output_format}'. "
                f"Set a supported one ({tuple(valid_output_formats)}) "
                "after a colon at the end of the output URI (i.e. -o/-O "
                "<URI>:<FORMAT>) or as a file extension."
            )

    overwrite = False
    if overwrite_output:
        if output:
            raise UsageError(
                "Please use only one of -o/--output and -O/--overwrite-output"
            )
        output = overwrite_output
        overwrite = True

    result: dict[str, dict[str, Any]] = {}
    for element in output:
        try:
            feed_uri, feed_format = element.rsplit(":", 1)
            check_valid_format(feed_format)
        except (ValueError, UsageError):
            feed_uri = element
            feed_format = Path(element).suffix.replace(".", "")
        else:
            if feed_uri == "-":
                feed_uri = "stdout:"
        check_valid_format(feed_format)
        result[feed_uri] = {"format": feed_format}
        if overwrite:
            result[feed_uri]["overwrite"] = True

    # FEEDS setting should take precedence over the matching CLI options
    result.update(settings.getdict("FEEDS"))

    return result
