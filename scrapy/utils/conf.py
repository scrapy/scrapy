import numbers
import os
import sys
import warnings
from configparser import ConfigParser
from operator import itemgetter

from scrapy.exceptions import ScrapyDeprecationWarning, UsageError

from scrapy.settings import BaseSettings
from scrapy.utils.deprecate import update_classpath
from scrapy.utils.python import without_none_values


def build_component_list(compdict, custom=None, convert=update_classpath):
    """Compose a component list from a { class: order } dictionary."""

    def _check_components(complist):
        if len({convert(c) for c in complist}) != len(complist):
            raise ValueError(f'Some paths in {complist!r} convert to the same object, '
                             'please update your settings')

    def _map_keys(compdict):
        if isinstance(compdict, BaseSettings):
            compbs = BaseSettings()
            for k, v in compdict.items():
                prio = compdict.getpriority(k)
                if compbs.getpriority(convert(k)) == prio:
                    raise ValueError(f'Some paths in {list(compdict.keys())!r} '
                                     'convert to the same '
                                     'object, please update your settings'
                                     )
                else:
                    compbs.set(convert(k), v, priority=prio)
            return compbs
        else:
            _check_components(compdict)
            return {convert(k): v for k, v in compdict.items()}

    def _validate_values(compdict):
        """Fail if a value in the components dict is not a real number or None."""
        for name, value in compdict.items():
            if value is not None and not isinstance(value, numbers.Real):
                raise ValueError(f'Invalid value {value} for component {name}, '
                                 'please provide a real number or None instead')

    # BEGIN Backward compatibility for old (base, custom) call signature
    if isinstance(custom, (list, tuple)):
        _check_components(custom)
        return type(custom)(convert(c) for c in custom)

    if custom is not None:
        compdict.update(custom)
    # END Backward compatibility

    _validate_values(compdict)
    compdict = without_none_values(_map_keys(compdict))
    return [k for k, v in sorted(compdict.items(), key=itemgetter(1))]


def arglist_to_dict(arglist):
    """Convert a list of arguments like ['arg1=val1', 'arg2=val2', ...] to a
    dict
    """
    return dict(x.split('=', 1) for x in arglist)


def closest_scrapy_cfg(path='.', prevpath=None):
    """Return the path to the closest scrapy.cfg file by traversing the current
    directory and its parents
    """
    if path == prevpath:
        return ''
    path = os.path.abspath(path)
    cfgfile = os.path.join(path, 'scrapy.cfg')
    if os.path.exists(cfgfile):
        return cfgfile
    return closest_scrapy_cfg(os.path.dirname(path), path)


def init_env(project='default', set_syspath=True):
    """Initialize environment to use command-line tool from inside a project
    dir. This sets the Scrapy settings module and modifies the Python path to
    be able to locate the project module.
    """
    cfg = get_config()
    if cfg.has_option('settings', project):
        os.environ['SCRAPY_SETTINGS_MODULE'] = cfg.get('settings', project)
    closest = closest_scrapy_cfg()
    if closest:
        projdir = os.path.dirname(closest)
        if set_syspath and projdir not in sys.path:
            sys.path.append(projdir)


def get_config(use_closest=True):
    """Get Scrapy config file as a ConfigParser"""
    sources = get_sources(use_closest)
    cfg = ConfigParser()
    cfg.read(sources)
    return cfg


def get_sources(use_closest=True):
    xdg_config_home = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    sources = [
        '/etc/scrapy.cfg',
        r'c:\scrapy\scrapy.cfg',
        xdg_config_home + '/scrapy.cfg',
        os.path.expanduser('~/.scrapy.cfg'),
    ]
    if use_closest:
        sources.append(closest_scrapy_cfg())
    return sources


def feed_complete_default_values_from_settings(feed, settings):
    out = feed.copy()
    out.setdefault("batch_item_count", settings.getint('FEED_EXPORT_BATCH_ITEM_COUNT'))
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


def feed_process_params_from_cli(settings, output, output_format=None,
                                 overwrite_output=None):
    """
    Receives feed export params (from the 'crawl' or 'runspider' commands),
    checks for inconsistencies in their quantities and returns a dictionary
    suitable to be used as the FEEDS setting.
    """
    valid_output_formats = without_none_values(
        settings.getwithbase('FEED_EXPORTERS')
    ).keys()

    def check_valid_format(output_format):
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

    if output_format:
        if len(output) == 1:
            check_valid_format(output_format)
            message = (
                'The -t command line option is deprecated in favor of '
                'specifying the output format within the output URI. See the '
                'documentation of the -o and -O options for more information.'
            )
            warnings.warn(message, ScrapyDeprecationWarning, stacklevel=2)
            return {output[0]: {'format': output_format}}
        else:
            raise UsageError(
                'The -t command-line option cannot be used if multiple output '
                'URIs are specified'
            )

    result = {}
    for element in output:
        try:
            feed_uri, feed_format = element.rsplit(':', 1)
        except ValueError:
            feed_uri = element
            feed_format = os.path.splitext(element)[1].replace('.', '')
        else:
            if feed_uri == '-':
                feed_uri = 'stdout:'
        check_valid_format(feed_format)
        result[feed_uri] = {'format': feed_format}
        if overwrite:
            result[feed_uri]['overwrite'] = True

    # FEEDS setting should take precedence over the matching CLI options
    result.update(settings.getdict('FEEDS'))

    return result
