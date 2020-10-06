import os
import pickle
import warnings

from importlib import import_module
from os.path import join, dirname, abspath, isabs, exists

from scrapy.utils.conf import closest_scrapy_cfg, get_config, init_env
from scrapy.settings import Settings
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning


ENVVAR = 'SCRAPY_SETTINGS_MODULE'
DATADIR_CFG_SECTION = 'datadir'


def inside_project():
    scrapy_module = os.environ.get('SCRAPY_SETTINGS_MODULE')
    if scrapy_module is not None:
        try:
            import_module(scrapy_module)
        except ImportError as exc:
            warnings.warn(f"Cannot import scrapy settings module {scrapy_module}: {exc}")
        else:
            return True
    return bool(closest_scrapy_cfg())


def project_data_dir(project='default'):
    """Return the current project data dir, creating it if it doesn't exist"""
    if not inside_project():
        raise NotConfigured("Not inside a project")
    cfg = get_config()
    if cfg.has_option(DATADIR_CFG_SECTION, project):
        d = cfg.get(DATADIR_CFG_SECTION, project)
    else:
        scrapy_cfg = closest_scrapy_cfg()
        if not scrapy_cfg:
            raise NotConfigured("Unable to find scrapy.cfg file to infer project data dir")
        d = abspath(join(dirname(scrapy_cfg), '.scrapy'))
    if not exists(d):
        os.makedirs(d)
    return d


def data_path(path, createdir=False):
    """
    Return the given path joined with the .scrapy data directory.
    If given an absolute path, return it unmodified.
    """
    if not isabs(path):
        if inside_project():
            path = join(project_data_dir(), path)
        else:
            path = join('.scrapy', path)
    if createdir and not exists(path):
        os.makedirs(path)
    return path


def get_project_settings():
    if ENVVAR not in os.environ:
        project = os.environ.get('SCRAPY_PROJECT', 'default')
        init_env(project)

    settings = Settings()
    settings_module_path = os.environ.get(ENVVAR)
    if settings_module_path:
        settings.setmodule(settings_module_path, priority='project')

    pickled_settings = os.environ.get("SCRAPY_PICKLED_SETTINGS_TO_OVERRIDE")
    if pickled_settings:
        warnings.warn("Use of environment variable "
                      "'SCRAPY_PICKLED_SETTINGS_TO_OVERRIDE' "
                      "is deprecated.", ScrapyDeprecationWarning)
        settings.setdict(pickle.loads(pickled_settings), priority='project')

    scrapy_envvars = {k[7:]: v for k, v in os.environ.items() if
                      k.startswith('SCRAPY_')}
    valid_envvars = {
        'CHECK',
        'PICKLED_SETTINGS_TO_OVERRIDE',
        'PROJECT',
        'PYTHON_SHELL',
        'SETTINGS_MODULE',
    }
    setting_envvars = {k for k in scrapy_envvars if k not in valid_envvars}
    if setting_envvars:
        setting_envvar_list = ', '.join(sorted(setting_envvars))
        warnings.warn(
            'Use of environment variables prefixed with SCRAPY_ to override '
            'settings is deprecated. The following environment variables are '
            f'currently defined: {setting_envvar_list}',
            ScrapyDeprecationWarning
        )
    settings.setdict(scrapy_envvars, priority='project')

    return settings
