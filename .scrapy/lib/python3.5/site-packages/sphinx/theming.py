# -*- coding: utf-8 -*-
"""
    sphinx.theming
    ~~~~~~~~~~~~~~

    Theming support for HTML builders.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import os
import shutil
import zipfile
import tempfile
from os import path

from six import string_types, iteritems
from six.moves import configparser

try:
    import pkg_resources
except ImportError:
    pkg_resources = False

from sphinx import package_dir
from sphinx.errors import ThemeError

NODEFAULT = object()
THEMECONF = 'theme.conf'


class Theme(object):
    """
    Represents the theme chosen in the configuration.
    """
    themes = {}

    @classmethod
    def init_themes(cls, confdir, theme_path, warn=None):
        """Search all theme paths for available themes."""
        cls.themepath = list(theme_path)
        cls.themepath.append(path.join(package_dir, 'themes'))

        for themedir in cls.themepath[::-1]:
            themedir = path.join(confdir, themedir)
            if not path.isdir(themedir):
                continue
            for theme in os.listdir(themedir):
                if theme.lower().endswith('.zip'):
                    try:
                        zfile = zipfile.ZipFile(path.join(themedir, theme))
                        if THEMECONF not in zfile.namelist():
                            continue
                        tname = theme[:-4]
                        tinfo = zfile
                    except Exception:
                        if warn:
                            warn('file %r on theme path is not a valid '
                                 'zipfile or contains no theme' % theme)
                        continue
                else:
                    if not path.isfile(path.join(themedir, theme, THEMECONF)):
                        continue
                    tname = theme
                    tinfo = None
                cls.themes[tname] = (path.join(themedir, theme), tinfo)

    @classmethod
    def load_extra_theme(cls, name):
        themes = ['alabaster']
        try:
            import sphinx_rtd_theme
            themes.append('sphinx_rtd_theme')
        except ImportError:
            pass
        if name in themes:
            if name == 'alabaster':
                import alabaster
                themedir = alabaster.get_path()
                # alabaster theme also requires 'alabaster' extension, it will be loaded
                # at sphinx.application module.
            elif name == 'sphinx_rtd_theme':
                themedir = sphinx_rtd_theme.get_html_theme_path()
            else:
                raise NotImplementedError('Programming Error')

        else:
            for themedir in load_theme_plugins():
                if path.isfile(path.join(themedir, name, THEMECONF)):
                    break
            else:
                # specified theme is not found
                return

        cls.themepath.append(themedir)
        cls.themes[name] = (path.join(themedir, name), None)
        return

    def __init__(self, name, warn=None):
        if name not in self.themes:
            self.load_extra_theme(name)
            if name not in self.themes:
                if name == 'sphinx_rtd_theme':
                    raise ThemeError('sphinx_rtd_theme is no longer a hard dependency '
                                     'since version 1.4.0. Please install it manually.'
                                     '(pip install sphinx_rtd_theme)')
                else:
                    raise ThemeError('no theme named %r found '
                                     '(missing theme.conf?)' % name)
        self.name = name

        # Do not warn yet -- to be compatible with old Sphinxes, people *have*
        # to use "default".
        # if name == 'default' and warn:
        #     warn("'default' html theme has been renamed to 'classic'. "
        #          "Please change your html_theme setting either to "
        #          "the new 'alabaster' default theme, or to 'classic' "
        #          "to keep using the old default.")

        tdir, tinfo = self.themes[name]
        if tinfo is None:
            # already a directory, do nothing
            self.themedir = tdir
            self.themedir_created = False
        else:
            # extract the theme to a temp directory
            self.themedir = tempfile.mkdtemp('sxt')
            self.themedir_created = True
            for name in tinfo.namelist():
                if name.endswith('/'):
                    continue
                dirname = path.dirname(name)
                if not path.isdir(path.join(self.themedir, dirname)):
                    os.makedirs(path.join(self.themedir, dirname))
                fp = open(path.join(self.themedir, name), 'wb')
                fp.write(tinfo.read(name))
                fp.close()

        self.themeconf = configparser.RawConfigParser()
        self.themeconf.read(path.join(self.themedir, THEMECONF))

        try:
            inherit = self.themeconf.get('theme', 'inherit')
        except configparser.NoOptionError:
            raise ThemeError('theme %r doesn\'t have "inherit" setting' % name)

        # load inherited theme automatically #1794, #1884, #1885
        self.load_extra_theme(inherit)

        if inherit == 'none':
            self.base = None
        elif inherit not in self.themes:
            raise ThemeError('no theme named %r found, inherited by %r' %
                             (inherit, name))
        else:
            self.base = Theme(inherit, warn=warn)

    def get_confstr(self, section, name, default=NODEFAULT):
        """Return the value for a theme configuration setting, searching the
        base theme chain.
        """
        try:
            return self.themeconf.get(section, name)
        except (configparser.NoOptionError, configparser.NoSectionError):
            if self.base is not None:
                return self.base.get_confstr(section, name, default)
            if default is NODEFAULT:
                raise ThemeError('setting %s.%s occurs in none of the '
                                 'searched theme configs' % (section, name))
            else:
                return default

    def get_options(self, overrides):
        """Return a dictionary of theme options and their values."""
        chain = [self.themeconf]
        base = self.base
        while base is not None:
            chain.append(base.themeconf)
            base = base.base
        options = {}
        for conf in reversed(chain):
            try:
                options.update(conf.items('options'))
            except configparser.NoSectionError:
                pass
        for option, value in iteritems(overrides):
            if option not in options:
                raise ThemeError('unsupported theme option %r given' % option)
            options[option] = value
        return options

    def get_dirchain(self):
        """Return a list of theme directories, beginning with this theme's,
        then the base theme's, then that one's base theme's, etc.
        """
        chain = [self.themedir]
        base = self.base
        while base is not None:
            chain.append(base.themedir)
            base = base.base
        return chain

    def cleanup(self):
        """Remove temporary directories."""
        if self.themedir_created:
            try:
                shutil.rmtree(self.themedir)
            except Exception:
                pass
        if self.base:
            self.base.cleanup()


def load_theme_plugins():
    """load plugins by using``sphinx_themes`` section in setuptools entry_points.
    This API will return list of directory that contain some theme directory.
    """

    if not pkg_resources:
        return []

    theme_paths = []

    for plugin in pkg_resources.iter_entry_points('sphinx_themes'):
        func_or_path = plugin.load()
        try:
            path = func_or_path()
        except Exception:
            path = func_or_path

        if isinstance(path, string_types):
            theme_paths.append(path)
        else:
            raise ThemeError('Plugin %r does not response correctly.' %
                             plugin.module_name)

    return theme_paths
