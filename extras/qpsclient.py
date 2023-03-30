import numbers
import os
import sys
import warnings
from configparser import ConfigParser
from operator import itemgetter
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from scrapy.exceptions import ScrapyDeprecationWarning, UsageError
from scrapy.settings import BaseSettings
from scrapy.utils.deprecate import update_classpath
from scrapy.utils.python import without_none_values


def build_component_list(components: Dict[str, int], custom_components: Optional[Union[List[str], Tuple[str]], convert_func=update_classpath]) -> List[str]:
    """Compose a component list from a {class: priority} dictionary."""

    def check_components(component_list) -> None:
        if len(set(map(convert_func, component_list))) != len(component_list):
            raise ValueError(
                "Some paths in {!r} convert to the same object, "
                "please update your settings".format(component_list)
            )

    def map_keys(dictionary) -> Union[BaseSettings, Dict[str, Any]]:
        if isinstance(dictionary, BaseSettings):
            result = BaseSettings()
            for key, value in dictionary.items():
                priority = dictionary.getpriority(key)
                if result.getpriority(convert_func(key)) == priority:
                    raise ValueError(
                        "Some paths in {!r} convert to the same "
                        "object, please update your settings".format(list(dictionary.keys()))
                    )
                else:
                    result.set(convert_func(key), value, priority=priority)
            return result
        check_components(dictionary)
        return {convert_func(key): value for key, value in dictionary.items()}

    def validate_values(component_dict: Dict[str, Any]) -> None:
        for name, value in component_dict.items():
            if value is not None and not isinstance(value, numbers.Real):
                raise ValueError(
                    "Invalid value {} for component {}, please provide a real number or None instead".format(value, name)
                )

    if isinstance(custom_components, (list, tuple)):
        check_components(custom_components)
        return [convert_func(component) for component in custom_components]

    if custom_components is not None:
        components.update(custom_components)

    validate_values(components)
    components = without_none_values(map_keys(components))
    return [key for key, value in sorted(components.items(), key=itemgetter(1))]


def arglist_to_dict(arg_list: List[str]) -> Dict[str, str]:
    """Convert a list of arguments like ['arg1=val1', 'arg2=val2', ...] to a dict."""
    return dict(x.split("=", 1) for x in arg_list)


def closest_scrapy_cfg(path: Union[str, os.PathLike] = ".", prev_path: Optional[Union[str, os.PathLike]] = None) -> str:
    """
    Return the path to the closest scrapy.cfg file by traversing the current directory and its parents.
    """
    if prev_path is not None and str(path) == str(prev_path):
        return ""
    path = Path(path).resolve()
    cfg_file = path / "scrapy.cfg"
    if cfg_file.exists():
        return str(cfg_file)
    return closest_scrapy_cfg(path.parent, path)


def init_env(project: str = "default", set_sys_path: bool = True) -> None:
    """Initialize environment to use command-line tool from inside a project dir.

    This sets the Scrapy settings module and modifies the Python path to be
    able to locate the project module.
    """
    cfg = get_config()
    if cfg.has_option("settings", project):
        os.environ["SCRAPY_SETTINGS_MODULE"] = cfg.get("settings", project)
    closest = closest_scrapy_cfg()
    if closest:
        proj_dir = str(Path(closest).parent)
        if set_sys_path and proj_dir not in sys.path:
            sys.path.append(proj_dir)


def get_config(use_closest: bool = True) -> ConfigParser:
    """
    Get Scrapy config file as a ConfigParser.
    """
    sources = get_sources(use_closest)
    cfg = ConfigParser()
    cfg.read(sources)
    return cfg


def get_sources(use_closest: bool = True) -> List[str]:
    XDG_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME", Path("~/.config").expanduser())
    potential_locations = [
        "/etc/scrapy.cfg",
        "c:/scrapy/scrapy.cfg",
        str(Path(XDG_CONFIG_HOME) / "scrapy.cfg"),
        str(Path("~/.scrapy.cfg").expanduser()),
    ]
    if use_closest:
        potential_locations.append(closest_scrapy_cfg())
    return potential_locations


def feed_complete_default_values_from_settings(feed: Dict[str, Any], settings: BaseSettings) -> Dict[str, Any]:
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
    output: List[str],
    output_format: Optional[str] = None,
    overwrite_output: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Receives feed export params (from the 'crawl' or 'runspider' commands),
    checks for inconsistencies in their quantities and returns a dictionary
    suitable to be used as the FEEDS setting.
    """
    valid_output_formats = without_none_values(settings.getwithbase("FEED_EXPORTERS")).keys()

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
            raise UsageError("Please use only one of -o/--output and -O/--overwrite-output")
        if output_format:
            raise UsageError(
                "-t/--output-format is a deprecated command line option and does not work in combination with -O/--overwrite-output."
                " To specify a format please specify it after a colon at the end of the"
                " output URI (i.e. -O <URI>:<FORMAT>)."
                " Example working in the tutorial: "
                "scrapy crawl quotes -O quotes.json:json"
            )
        output = overwrite_output
        overwrite = True

    if output_format:
        if len(output) == 1:
            check_valid_format(output_format)
            message = (
                "The -t/--output-format command line option is deprecated in favor of "
                "specifying the output format within the output URI using the -o/--output or the"
                " -O/--overwrite-output option (i.e. -o/-O <URI>:<FORMAT>). See the documentation"
                " of the -o or -O option or the following examples for more information. "
                "Examples working in the tutorial: "
                "scrapy crawl quotes -o quotes.csv:csv   or   "
                "scrapy crawl quotes -O quotes.json:json"
            )
            warnings.warn(message, ScrapyDeprecationWarning, stacklevel=2)
            return {output[0]: {"format": output_format}}
        raise UsageError(
            "The -t command-line option cannot be used if multiple output URIs are specified"
        )

    result: Dict[str, Dict[str, Any]] = {}
    for element in output:
        try:
            feed_uri, feed_format = element.rsplit(":", 1)
        except ValueError:
            feed_uri = element
            feed_format = Path(element).suffix.replace(".", "")
        else:
            if feed_uri == "-":
                feed_uri = "stdout:"
        check_valid_format(feed_format)
        result[feed_uri] = {"format": feed_format}
        if overwrite:
            result[feed_uri]["overwrite"] = True

    result.update(settings.getdict("FEEDS"))

    return result
