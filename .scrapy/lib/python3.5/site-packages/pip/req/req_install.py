from __future__ import absolute_import

import logging
import os
import re
import shutil
import sys
import tempfile
import warnings
import zipfile

from distutils.util import change_root
from distutils import sysconfig
from email.parser import FeedParser

from pip._vendor import pkg_resources, six
from pip._vendor.distlib.markers import interpret as markers_interpret
from pip._vendor.six.moves import configparser

import pip.wheel

from pip.compat import native_str, WINDOWS
from pip.download import is_url, url_to_path, path_to_url, is_archive_file
from pip.exceptions import (
    InstallationError, UninstallationError, UnsupportedWheel,
)
from pip.locations import (
    bin_py, running_under_virtualenv, PIP_DELETE_MARKER_FILENAME, bin_user,
)
from pip.utils import (
    display_path, rmtree, ask_path_exists, backup_dir, is_installable_dir,
    dist_in_usersite, dist_in_site_packages, egg_link_path, make_path_relative,
    call_subprocess, read_text_file, FakeFile, _make_build_dir, ensure_dir,
    get_installed_version
)
from pip.utils.deprecation import RemovedInPip8Warning
from pip.utils.logging import indent_log
from pip.req.req_uninstall import UninstallPathSet
from pip.vcs import vcs
from pip.wheel import move_wheel_files, Wheel
from pip._vendor.packaging.version import Version


logger = logging.getLogger(__name__)


def _strip_extras(path):
    m = re.match(r'^(.+)(\[[^\]]+\])$', path)
    extras = None
    if m:
        path_no_extras = m.group(1)
        extras = m.group(2)
    else:
        path_no_extras = path

    return path_no_extras, extras


class InstallRequirement(object):

    def __init__(self, req, comes_from, source_dir=None, editable=False,
                 link=None, as_egg=False, update=True, editable_options=None,
                 pycompile=True, markers=None, isolated=False, options=None,
                 wheel_cache=None, constraint=False):
        self.extras = ()
        if isinstance(req, six.string_types):
            req = pkg_resources.Requirement.parse(req)
            self.extras = req.extras

        self.req = req
        self.comes_from = comes_from
        self.constraint = constraint
        self.source_dir = source_dir
        self.editable = editable

        if editable_options is None:
            editable_options = {}

        self.editable_options = editable_options
        self._wheel_cache = wheel_cache
        self.link = link
        self.as_egg = as_egg
        self.markers = markers
        self._egg_info_path = None
        # This holds the pkg_resources.Distribution object if this requirement
        # is already available:
        self.satisfied_by = None
        # This hold the pkg_resources.Distribution object if this requirement
        # conflicts with another installed distribution:
        self.conflicts_with = None
        # Temporary build location
        self._temp_build_dir = None
        # Used to store the global directory where the _temp_build_dir should
        # have been created. Cf _correct_build_location method.
        self._ideal_global_dir = None
        # True if the editable should be updated:
        self.update = update
        # Set to True after successful installation
        self.install_succeeded = None
        # UninstallPathSet of uninstalled distribution (for possible rollback)
        self.uninstalled = None
        self.use_user_site = False
        self.target_dir = None
        self.options = options if options else {}
        self.pycompile = pycompile
        # Set to True after successful preparation of this requirement
        self.prepared = False

        self.isolated = isolated

    @classmethod
    def from_editable(cls, editable_req, comes_from=None, default_vcs=None,
                      isolated=False, options=None, wheel_cache=None,
                      constraint=False):
        from pip.index import Link

        name, url, extras_override, editable_options = parse_editable(
            editable_req, default_vcs)
        if url.startswith('file:'):
            source_dir = url_to_path(url)
        else:
            source_dir = None

        res = cls(name, comes_from, source_dir=source_dir,
                  editable=True,
                  link=Link(url),
                  constraint=constraint,
                  editable_options=editable_options,
                  isolated=isolated,
                  options=options if options else {},
                  wheel_cache=wheel_cache)

        if extras_override is not None:
            res.extras = extras_override

        return res

    @classmethod
    def from_line(
            cls, name, comes_from=None, isolated=False, options=None,
            wheel_cache=None, constraint=False):
        """Creates an InstallRequirement from a name, which might be a
        requirement, directory containing 'setup.py', filename, or URL.
        """
        from pip.index import Link

        if is_url(name):
            marker_sep = '; '
        else:
            marker_sep = ';'
        if marker_sep in name:
            name, markers = name.split(marker_sep, 1)
            markers = markers.strip()
            if not markers:
                markers = None
        else:
            markers = None
        name = name.strip()
        req = None
        path = os.path.normpath(os.path.abspath(name))
        link = None
        extras = None

        if is_url(name):
            link = Link(name)
        else:
            p, extras = _strip_extras(path)
            if (os.path.isdir(p) and
                    (os.path.sep in name or name.startswith('.'))):

                if not is_installable_dir(p):
                    raise InstallationError(
                        "Directory %r is not installable. File 'setup.py' "
                        "not found." % name
                    )
                link = Link(path_to_url(p))
            elif is_archive_file(p):
                if not os.path.isfile(p):
                    logger.warning(
                        'Requirement %r looks like a filename, but the '
                        'file does not exist',
                        name
                    )
                link = Link(path_to_url(p))

        # it's a local file, dir, or url
        if link:
            # Handle relative file URLs
            if link.scheme == 'file' and re.search(r'\.\./', link.url):
                link = Link(
                    path_to_url(os.path.normpath(os.path.abspath(link.path))))
            # wheel file
            if link.is_wheel:
                wheel = Wheel(link.filename)  # can raise InvalidWheelFilename
                if not wheel.supported():
                    raise UnsupportedWheel(
                        "%s is not a supported wheel on this platform." %
                        wheel.filename
                    )
                req = "%s==%s" % (wheel.name, wheel.version)
            else:
                # set the req to the egg fragment.  when it's not there, this
                # will become an 'unnamed' requirement
                req = link.egg_fragment

        # a requirement specifier
        else:
            req = name

        options = options if options else {}
        res = cls(req, comes_from, link=link, markers=markers,
                  isolated=isolated, options=options,
                  wheel_cache=wheel_cache, constraint=constraint)

        if extras:
            res.extras = pkg_resources.Requirement.parse('__placeholder__' +
                                                         extras).extras

        return res

    def __str__(self):
        if self.req:
            s = str(self.req)
            if self.link:
                s += ' from %s' % self.link.url
        else:
            s = self.link.url if self.link else None
        if self.satisfied_by is not None:
            s += ' in %s' % display_path(self.satisfied_by.location)
        if self.comes_from:
            if isinstance(self.comes_from, six.string_types):
                comes_from = self.comes_from
            else:
                comes_from = self.comes_from.from_path()
            if comes_from:
                s += ' (from %s)' % comes_from
        return s

    def __repr__(self):
        return '<%s object: %s editable=%r>' % (
            self.__class__.__name__, str(self), self.editable)

    def populate_link(self, finder, upgrade):
        """Ensure that if a link can be found for this, that it is found.

        Note that self.link may still be None - if Upgrade is False and the
        requirement is already installed.
        """
        if self.link is None:
            self.link = finder.find_requirement(self, upgrade)

    @property
    def link(self):
        return self._link

    @link.setter
    def link(self, link):
        # Lookup a cached wheel, if possible.
        if self._wheel_cache is None:
            self._link = link
        else:
            self._link = self._wheel_cache.cached_wheel(link, self.name)
            if self._link != link:
                logger.debug('Using cached wheel link: %s', self._link)

    @property
    def specifier(self):
        return self.req.specifier

    def from_path(self):
        if self.req is None:
            return None
        s = str(self.req)
        if self.comes_from:
            if isinstance(self.comes_from, six.string_types):
                comes_from = self.comes_from
            else:
                comes_from = self.comes_from.from_path()
            if comes_from:
                s += '->' + comes_from
        return s

    def build_location(self, build_dir):
        if self._temp_build_dir is not None:
            return self._temp_build_dir
        if self.req is None:
            # for requirement via a path to a directory: the name of the
            # package is not available yet so we create a temp directory
            # Once run_egg_info will have run, we'll be able
            # to fix it via _correct_build_location
            self._temp_build_dir = tempfile.mkdtemp('-build', 'pip-')
            self._ideal_build_dir = build_dir
            return self._temp_build_dir
        if self.editable:
            name = self.name.lower()
        else:
            name = self.name
        # FIXME: Is there a better place to create the build_dir? (hg and bzr
        # need this)
        if not os.path.exists(build_dir):
            logger.debug('Creating directory %s', build_dir)
            _make_build_dir(build_dir)
        return os.path.join(build_dir, name)

    def _correct_build_location(self):
        """Move self._temp_build_dir to self._ideal_build_dir/self.req.name

        For some requirements (e.g. a path to a directory), the name of the
        package is not available until we run egg_info, so the build_location
        will return a temporary directory and store the _ideal_build_dir.

        This is only called by self.egg_info_path to fix the temporary build
        directory.
        """
        if self.source_dir is not None:
            return
        assert self.req is not None
        assert self._temp_build_dir
        assert self._ideal_build_dir
        old_location = self._temp_build_dir
        self._temp_build_dir = None
        new_location = self.build_location(self._ideal_build_dir)
        if os.path.exists(new_location):
            raise InstallationError(
                'A package already exists in %s; please remove it to continue'
                % display_path(new_location))
        logger.debug(
            'Moving package %s from %s to new location %s',
            self, display_path(old_location), display_path(new_location),
        )
        shutil.move(old_location, new_location)
        self._temp_build_dir = new_location
        self._ideal_build_dir = None
        self.source_dir = new_location
        self._egg_info_path = None

    @property
    def name(self):
        if self.req is None:
            return None
        return native_str(self.req.project_name)

    @property
    def setup_py(self):
        assert self.source_dir, "No source dir for %s" % self
        try:
            import setuptools  # noqa
        except ImportError:
            # Setuptools is not available
            raise InstallationError(
                "setuptools must be installed to install from a source "
                "distribution"
            )

        setup_file = 'setup.py'

        if self.editable_options and 'subdirectory' in self.editable_options:
            setup_py = os.path.join(self.source_dir,
                                    self.editable_options['subdirectory'],
                                    setup_file)

        else:
            setup_py = os.path.join(self.source_dir, setup_file)

        # Python2 __file__ should not be unicode
        if six.PY2 and isinstance(setup_py, six.text_type):
            setup_py = setup_py.encode(sys.getfilesystemencoding())

        return setup_py

    def run_egg_info(self):
        assert self.source_dir
        if self.name:
            logger.debug(
                'Running setup.py (path:%s) egg_info for package %s',
                self.setup_py, self.name,
            )
        else:
            logger.debug(
                'Running setup.py (path:%s) egg_info for package from %s',
                self.setup_py, self.link,
            )

        with indent_log():
            script = self._run_setup_py
            script = script.replace('__SETUP_PY__', repr(self.setup_py))
            script = script.replace('__PKG_NAME__', repr(self.name))
            base_cmd = [sys.executable, '-c', script]
            if self.isolated:
                base_cmd += ["--no-user-cfg"]
            egg_info_cmd = base_cmd + ['egg_info']
            # We can't put the .egg-info files at the root, because then the
            # source code will be mistaken for an installed egg, causing
            # problems
            if self.editable:
                egg_base_option = []
            else:
                egg_info_dir = os.path.join(self.source_dir, 'pip-egg-info')
                ensure_dir(egg_info_dir)
                egg_base_option = ['--egg-base', 'pip-egg-info']
            cwd = self.source_dir
            if self.editable_options and \
                    'subdirectory' in self.editable_options:
                cwd = os.path.join(cwd, self.editable_options['subdirectory'])
            call_subprocess(
                egg_info_cmd + egg_base_option,
                cwd=cwd,
                show_stdout=False,
                command_level=logging.DEBUG,
                command_desc='python setup.py egg_info')

        if not self.req:
            if isinstance(
                    pkg_resources.parse_version(self.pkg_info()["Version"]),
                    Version):
                op = "=="
            else:
                op = "==="
            self.req = pkg_resources.Requirement.parse(
                "".join([
                    self.pkg_info()["Name"],
                    op,
                    self.pkg_info()["Version"],
                ]))
            self._correct_build_location()

    # FIXME: This is a lame hack, entirely for PasteScript which has
    # a self-provided entry point that causes this awkwardness
    _run_setup_py = """
__file__ = __SETUP_PY__
from setuptools.command import egg_info
import pkg_resources
import os
import tokenize
def replacement_run(self):
    self.mkpath(self.egg_info)
    installer = self.distribution.fetch_build_egg
    for ep in pkg_resources.iter_entry_points('egg_info.writers'):
        # require=False is the change we're making:
        writer = ep.load(require=False)
        if writer:
            writer(self, ep.name, os.path.join(self.egg_info,ep.name))
    self.find_sources()
egg_info.egg_info.run = replacement_run
exec(compile(
    getattr(tokenize, 'open', open)(__file__).read().replace('\\r\\n', '\\n'),
    __file__,
    'exec'
))
"""

    def egg_info_data(self, filename):
        if self.satisfied_by is not None:
            if not self.satisfied_by.has_metadata(filename):
                return None
            return self.satisfied_by.get_metadata(filename)
        assert self.source_dir
        filename = self.egg_info_path(filename)
        if not os.path.exists(filename):
            return None
        data = read_text_file(filename)
        return data

    def egg_info_path(self, filename):
        if self._egg_info_path is None:
            if self.editable:
                base = self.source_dir
            else:
                base = os.path.join(self.source_dir, 'pip-egg-info')
            filenames = os.listdir(base)
            if self.editable:
                filenames = []
                for root, dirs, files in os.walk(base):
                    for dir in vcs.dirnames:
                        if dir in dirs:
                            dirs.remove(dir)
                    # Iterate over a copy of ``dirs``, since mutating
                    # a list while iterating over it can cause trouble.
                    # (See https://github.com/pypa/pip/pull/462.)
                    for dir in list(dirs):
                        # Don't search in anything that looks like a virtualenv
                        # environment
                        if (
                                os.path.exists(
                                    os.path.join(root, dir, 'bin', 'python')
                                ) or
                                os.path.exists(
                                    os.path.join(
                                        root, dir, 'Scripts', 'Python.exe'
                                    )
                                )):
                            dirs.remove(dir)
                        # Also don't search through tests
                        elif dir == 'test' or dir == 'tests':
                            dirs.remove(dir)
                    filenames.extend([os.path.join(root, dir)
                                     for dir in dirs])
                filenames = [f for f in filenames if f.endswith('.egg-info')]

            if not filenames:
                raise InstallationError(
                    'No files/directories in %s (from %s)' % (base, filename)
                )
            assert filenames, \
                "No files/directories in %s (from %s)" % (base, filename)

            # if we have more than one match, we pick the toplevel one.  This
            # can easily be the case if there is a dist folder which contains
            # an extracted tarball for testing purposes.
            if len(filenames) > 1:
                filenames.sort(
                    key=lambda x: x.count(os.path.sep) +
                    (os.path.altsep and x.count(os.path.altsep) or 0)
                )
            self._egg_info_path = os.path.join(base, filenames[0])
        return os.path.join(self._egg_info_path, filename)

    def pkg_info(self):
        p = FeedParser()
        data = self.egg_info_data('PKG-INFO')
        if not data:
            logger.warning(
                'No PKG-INFO file found in %s',
                display_path(self.egg_info_path('PKG-INFO')),
            )
        p.feed(data or '')
        return p.close()

    _requirements_section_re = re.compile(r'\[(.*?)\]')

    @property
    def installed_version(self):
        return get_installed_version(self.name)

    def assert_source_matches_version(self):
        assert self.source_dir
        version = self.pkg_info()['version']
        if version not in self.req:
            logger.warning(
                'Requested %s, but installing version %s',
                self,
                self.installed_version,
            )
        else:
            logger.debug(
                'Source in %s has version %s, which satisfies requirement %s',
                display_path(self.source_dir),
                version,
                self,
            )

    def update_editable(self, obtain=True):
        if not self.link:
            logger.debug(
                "Cannot update repository at %s; repository location is "
                "unknown",
                self.source_dir,
            )
            return
        assert self.editable
        assert self.source_dir
        if self.link.scheme == 'file':
            # Static paths don't get updated
            return
        assert '+' in self.link.url, "bad url: %r" % self.link.url
        if not self.update:
            return
        vc_type, url = self.link.url.split('+', 1)
        backend = vcs.get_backend(vc_type)
        if backend:
            vcs_backend = backend(self.link.url)
            if obtain:
                vcs_backend.obtain(self.source_dir)
            else:
                vcs_backend.export(self.source_dir)
        else:
            assert 0, (
                'Unexpected version control type (in %s): %s'
                % (self.link, vc_type))

    def uninstall(self, auto_confirm=False):
        """
        Uninstall the distribution currently satisfying this requirement.

        Prompts before removing or modifying files unless
        ``auto_confirm`` is True.

        Refuses to delete or modify files outside of ``sys.prefix`` -
        thus uninstallation within a virtual environment can only
        modify that virtual environment, even if the virtualenv is
        linked to global site-packages.

        """
        if not self.check_if_exists():
            raise UninstallationError(
                "Cannot uninstall requirement %s, not installed" % (self.name,)
            )
        dist = self.satisfied_by or self.conflicts_with

        paths_to_remove = UninstallPathSet(dist)
        develop_egg_link = egg_link_path(dist)
        develop_egg_link_egg_info = '{0}.egg-info'.format(
            pkg_resources.to_filename(dist.project_name))
        egg_info_exists = dist.egg_info and os.path.exists(dist.egg_info)
        # Special case for distutils installed package
        distutils_egg_info = getattr(dist._provider, 'path', None)

        # Uninstall cases order do matter as in the case of 2 installs of the
        # same package, pip needs to uninstall the currently detected version
        if (egg_info_exists and dist.egg_info.endswith('.egg-info') and
                not dist.egg_info.endswith(develop_egg_link_egg_info)):
            # if dist.egg_info.endswith(develop_egg_link_egg_info), we
            # are in fact in the develop_egg_link case
            paths_to_remove.add(dist.egg_info)
            if dist.has_metadata('installed-files.txt'):
                for installed_file in dist.get_metadata(
                        'installed-files.txt').splitlines():
                    path = os.path.normpath(
                        os.path.join(dist.egg_info, installed_file)
                    )
                    paths_to_remove.add(path)
            # FIXME: need a test for this elif block
            # occurs with --single-version-externally-managed/--record outside
            # of pip
            elif dist.has_metadata('top_level.txt'):
                if dist.has_metadata('namespace_packages.txt'):
                    namespaces = dist.get_metadata('namespace_packages.txt')
                else:
                    namespaces = []
                for top_level_pkg in [
                        p for p
                        in dist.get_metadata('top_level.txt').splitlines()
                        if p and p not in namespaces]:
                    path = os.path.join(dist.location, top_level_pkg)
                    paths_to_remove.add(path)
                    paths_to_remove.add(path + '.py')
                    paths_to_remove.add(path + '.pyc')

        elif distutils_egg_info:
            warnings.warn(
                "Uninstalling a distutils installed project ({0}) has been "
                "deprecated and will be removed in a future version. This is "
                "due to the fact that uninstalling a distutils project will "
                "only partially uninstall the project.".format(self.name),
                RemovedInPip8Warning,
            )
            paths_to_remove.add(distutils_egg_info)

        elif dist.location.endswith('.egg'):
            # package installed by easy_install
            # We cannot match on dist.egg_name because it can slightly vary
            # i.e. setuptools-0.6c11-py2.6.egg vs setuptools-0.6rc11-py2.6.egg
            paths_to_remove.add(dist.location)
            easy_install_egg = os.path.split(dist.location)[1]
            easy_install_pth = os.path.join(os.path.dirname(dist.location),
                                            'easy-install.pth')
            paths_to_remove.add_pth(easy_install_pth, './' + easy_install_egg)

        elif develop_egg_link:
            # develop egg
            with open(develop_egg_link, 'r') as fh:
                link_pointer = os.path.normcase(fh.readline().strip())
            assert (link_pointer == dist.location), (
                'Egg-link %s does not match installed location of %s '
                '(at %s)' % (link_pointer, self.name, dist.location)
            )
            paths_to_remove.add(develop_egg_link)
            easy_install_pth = os.path.join(os.path.dirname(develop_egg_link),
                                            'easy-install.pth')
            paths_to_remove.add_pth(easy_install_pth, dist.location)

        elif egg_info_exists and dist.egg_info.endswith('.dist-info'):
            for path in pip.wheel.uninstallation_paths(dist):
                paths_to_remove.add(path)

        else:
            logger.debug(
                'Not sure how to uninstall: %s - Check: %s',
                dist, dist.location)

        # find distutils scripts= scripts
        if dist.has_metadata('scripts') and dist.metadata_isdir('scripts'):
            for script in dist.metadata_listdir('scripts'):
                if dist_in_usersite(dist):
                    bin_dir = bin_user
                else:
                    bin_dir = bin_py
                paths_to_remove.add(os.path.join(bin_dir, script))
                if WINDOWS:
                    paths_to_remove.add(os.path.join(bin_dir, script) + '.bat')

        # find console_scripts
        if dist.has_metadata('entry_points.txt'):
            config = configparser.SafeConfigParser()
            config.readfp(
                FakeFile(dist.get_metadata_lines('entry_points.txt'))
            )
            if config.has_section('console_scripts'):
                for name, value in config.items('console_scripts'):
                    if dist_in_usersite(dist):
                        bin_dir = bin_user
                    else:
                        bin_dir = bin_py
                    paths_to_remove.add(os.path.join(bin_dir, name))
                    if WINDOWS:
                        paths_to_remove.add(
                            os.path.join(bin_dir, name) + '.exe'
                        )
                        paths_to_remove.add(
                            os.path.join(bin_dir, name) + '.exe.manifest'
                        )
                        paths_to_remove.add(
                            os.path.join(bin_dir, name) + '-script.py'
                        )

        paths_to_remove.remove(auto_confirm)
        self.uninstalled = paths_to_remove

    def rollback_uninstall(self):
        if self.uninstalled:
            self.uninstalled.rollback()
        else:
            logger.error(
                "Can't rollback %s, nothing uninstalled.", self.project_name,
            )

    def commit_uninstall(self):
        if self.uninstalled:
            self.uninstalled.commit()
        else:
            logger.error(
                "Can't commit %s, nothing uninstalled.", self.project_name,
            )

    def archive(self, build_dir):
        assert self.source_dir
        create_archive = True
        archive_name = '%s-%s.zip' % (self.name, self.pkg_info()["version"])
        archive_path = os.path.join(build_dir, archive_name)
        if os.path.exists(archive_path):
            response = ask_path_exists(
                'The file %s exists. (i)gnore, (w)ipe, (b)ackup ' %
                display_path(archive_path), ('i', 'w', 'b'))
            if response == 'i':
                create_archive = False
            elif response == 'w':
                logger.warning('Deleting %s', display_path(archive_path))
                os.remove(archive_path)
            elif response == 'b':
                dest_file = backup_dir(archive_path)
                logger.warning(
                    'Backing up %s to %s',
                    display_path(archive_path),
                    display_path(dest_file),
                )
                shutil.move(archive_path, dest_file)
        if create_archive:
            zip = zipfile.ZipFile(
                archive_path, 'w', zipfile.ZIP_DEFLATED,
                allowZip64=True
            )
            dir = os.path.normcase(os.path.abspath(self.source_dir))
            for dirpath, dirnames, filenames in os.walk(dir):
                if 'pip-egg-info' in dirnames:
                    dirnames.remove('pip-egg-info')
                for dirname in dirnames:
                    dirname = os.path.join(dirpath, dirname)
                    name = self._clean_zip_name(dirname, dir)
                    zipdir = zipfile.ZipInfo(self.name + '/' + name + '/')
                    zipdir.external_attr = 0x1ED << 16  # 0o755
                    zip.writestr(zipdir, '')
                for filename in filenames:
                    if filename == PIP_DELETE_MARKER_FILENAME:
                        continue
                    filename = os.path.join(dirpath, filename)
                    name = self._clean_zip_name(filename, dir)
                    zip.write(filename, self.name + '/' + name)
            zip.close()
            logger.info('Saved %s', display_path(archive_path))

    def _clean_zip_name(self, name, prefix):
        assert name.startswith(prefix + os.path.sep), (
            "name %r doesn't start with prefix %r" % (name, prefix)
        )
        name = name[len(prefix) + 1:]
        name = name.replace(os.path.sep, '/')
        return name

    def match_markers(self):
        if self.markers is not None:
            return markers_interpret(self.markers)
        else:
            return True

    def install(self, install_options, global_options=[], root=None):
        if self.editable:
            self.install_editable(install_options, global_options)
            return
        if self.is_wheel:
            version = pip.wheel.wheel_version(self.source_dir)
            pip.wheel.check_compatibility(version, self.name)

            self.move_wheel_files(self.source_dir, root=root)
            self.install_succeeded = True
            return

        # Extend the list of global and install options passed on to
        # the setup.py call with the ones from the requirements file.
        # Options specified in requirements file override those
        # specified on the command line, since the last option given
        # to setup.py is the one that is used.
        global_options += self.options.get('global_options', [])
        install_options += self.options.get('install_options', [])

        if self.isolated:
            global_options = list(global_options) + ["--no-user-cfg"]

        temp_location = tempfile.mkdtemp('-record', 'pip-')
        record_filename = os.path.join(temp_location, 'install-record.txt')
        try:
            install_args = [sys.executable]
            install_args.append('-c')
            install_args.append(
                "import setuptools, tokenize;__file__=%r;"
                "exec(compile(getattr(tokenize, 'open', open)(__file__).read()"
                ".replace('\\r\\n', '\\n'), __file__, 'exec'))" % self.setup_py
            )
            install_args += list(global_options) + \
                ['install', '--record', record_filename]

            if not self.as_egg:
                install_args += ['--single-version-externally-managed']

            if root is not None:
                install_args += ['--root', root]

            if self.pycompile:
                install_args += ["--compile"]
            else:
                install_args += ["--no-compile"]

            if running_under_virtualenv():
                py_ver_str = 'python' + sysconfig.get_python_version()
                install_args += ['--install-headers',
                                 os.path.join(sys.prefix, 'include', 'site',
                                              py_ver_str, self.name)]
            logger.info('Running setup.py install for %s', self.name)
            with indent_log():
                call_subprocess(
                    install_args + install_options,
                    cwd=self.source_dir,
                    show_stdout=False,
                )

            if not os.path.exists(record_filename):
                logger.debug('Record file %s not found', record_filename)
                return
            self.install_succeeded = True
            if self.as_egg:
                # there's no --always-unzip option we can pass to install
                # command so we unable to save the installed-files.txt
                return

            def prepend_root(path):
                if root is None or not os.path.isabs(path):
                    return path
                else:
                    return change_root(root, path)

            with open(record_filename) as f:
                for line in f:
                    directory = os.path.dirname(line)
                    if directory.endswith('.egg-info'):
                        egg_info_dir = prepend_root(directory)
                        break
                else:
                    logger.warning(
                        'Could not find .egg-info directory in install record'
                        ' for %s',
                        self,
                    )
                    # FIXME: put the record somewhere
                    # FIXME: should this be an error?
                    return
            new_lines = []
            with open(record_filename) as f:
                for line in f:
                    filename = line.strip()
                    if os.path.isdir(filename):
                        filename += os.path.sep
                    new_lines.append(
                        make_path_relative(
                            prepend_root(filename), egg_info_dir)
                    )
            inst_files_path = os.path.join(egg_info_dir, 'installed-files.txt')
            with open(inst_files_path, 'w') as f:
                f.write('\n'.join(new_lines) + '\n')
        finally:
            if os.path.exists(record_filename):
                os.remove(record_filename)
            rmtree(temp_location)

    def ensure_has_source_dir(self, parent_dir):
        """Ensure that a source_dir is set.

        This will create a temporary build dir if the name of the requirement
        isn't known yet.

        :param parent_dir: The ideal pip parent_dir for the source_dir.
            Generally src_dir for editables and build_dir for sdists.
        :return: self.source_dir
        """
        if self.source_dir is None:
            self.source_dir = self.build_location(parent_dir)
        return self.source_dir

    def remove_temporary_source(self):
        """Remove the source files from this requirement, if they are marked
        for deletion"""
        if self.source_dir and os.path.exists(
                os.path.join(self.source_dir, PIP_DELETE_MARKER_FILENAME)):
            logger.debug('Removing source in %s', self.source_dir)
            rmtree(self.source_dir)
        self.source_dir = None
        if self._temp_build_dir and os.path.exists(self._temp_build_dir):
            rmtree(self._temp_build_dir)
        self._temp_build_dir = None

    def install_editable(self, install_options, global_options=()):
        logger.info('Running setup.py develop for %s', self.name)

        if self.isolated:
            global_options = list(global_options) + ["--no-user-cfg"]

        with indent_log():
            # FIXME: should we do --install-headers here too?
            cwd = self.source_dir
            if self.editable_options and \
                    'subdirectory' in self.editable_options:
                cwd = os.path.join(cwd, self.editable_options['subdirectory'])
            call_subprocess(
                [
                    sys.executable,
                    '-c',
                    "import setuptools, tokenize; __file__=%r; exec(compile("
                    "getattr(tokenize, 'open', open)(__file__).read().replace"
                    "('\\r\\n', '\\n'), __file__, 'exec'))" % self.setup_py
                ] +
                list(global_options) +
                ['develop', '--no-deps'] +
                list(install_options),

                cwd=cwd,
                show_stdout=False)

        self.install_succeeded = True

    def check_if_exists(self):
        """Find an installed distribution that satisfies or conflicts
        with this requirement, and set self.satisfied_by or
        self.conflicts_with appropriately.
        """
        if self.req is None:
            return False
        try:
            self.satisfied_by = pkg_resources.get_distribution(self.req)
        except pkg_resources.DistributionNotFound:
            return False
        except pkg_resources.VersionConflict:
            existing_dist = pkg_resources.get_distribution(
                self.req.project_name
            )
            if self.use_user_site:
                if dist_in_usersite(existing_dist):
                    self.conflicts_with = existing_dist
                elif (running_under_virtualenv() and
                        dist_in_site_packages(existing_dist)):
                    raise InstallationError(
                        "Will not install to the user site because it will "
                        "lack sys.path precedence to %s in %s" %
                        (existing_dist.project_name, existing_dist.location)
                    )
            else:
                self.conflicts_with = existing_dist
        return True

    @property
    def is_wheel(self):
        return self.link and self.link.is_wheel

    def move_wheel_files(self, wheeldir, root=None):
        move_wheel_files(
            self.name, self.req, wheeldir,
            user=self.use_user_site,
            home=self.target_dir,
            root=root,
            pycompile=self.pycompile,
            isolated=self.isolated,
        )

    def get_dist(self):
        """Return a pkg_resources.Distribution built from self.egg_info_path"""
        egg_info = self.egg_info_path('').rstrip('/')
        base_dir = os.path.dirname(egg_info)
        metadata = pkg_resources.PathMetadata(base_dir, egg_info)
        dist_name = os.path.splitext(os.path.basename(egg_info))[0]
        return pkg_resources.Distribution(
            os.path.dirname(egg_info),
            project_name=dist_name,
            metadata=metadata)


def _strip_postfix(req):
    """
        Strip req postfix ( -dev, 0.2, etc )
    """
    # FIXME: use package_to_requirement?
    match = re.search(r'^(.*?)(?:-dev|-\d.*)$', req)
    if match:
        # Strip off -dev, -0.2, etc.
        req = match.group(1)
    return req


def _build_req_from_url(url):

    parts = [p for p in url.split('#', 1)[0].split('/') if p]

    req = None
    if parts[-2] in ('tags', 'branches', 'tag', 'branch'):
        req = parts[-3]
    elif parts[-1] == 'trunk':
        req = parts[-2]
    return req


def _build_editable_options(req):

    """
        This method generates a dictionary of the query string
        parameters contained in a given editable URL.
    """
    regexp = re.compile(r"[\?#&](?P<name>[^&=]+)=(?P<value>[^&=]+)")
    matched = regexp.findall(req)

    if matched:
        ret = dict()
        for option in matched:
            (name, value) = option
            if name in ret:
                raise Exception("%s option already defined" % name)
            ret[name] = value
        return ret
    return None


def parse_editable(editable_req, default_vcs=None):
    """Parses an editable requirement into:
        - a requirement name
        - an URL
        - extras
        - editable options
    Accepted requirements:
        svn+http://blahblah@rev#egg=Foobar[baz]&subdirectory=version_subdir
        .[some_extra]
    """

    url = editable_req
    extras = None

    # If a file path is specified with extras, strip off the extras.
    m = re.match(r'^(.+)(\[[^\]]+\])$', url)
    if m:
        url_no_extras = m.group(1)
        extras = m.group(2)
    else:
        url_no_extras = url

    if os.path.isdir(url_no_extras):
        if not os.path.exists(os.path.join(url_no_extras, 'setup.py')):
            raise InstallationError(
                "Directory %r is not installable. File 'setup.py' not found." %
                url_no_extras
            )
        # Treating it as code that has already been checked out
        url_no_extras = path_to_url(url_no_extras)

    if url_no_extras.lower().startswith('file:'):
        if extras:
            return (
                None,
                url_no_extras,
                pkg_resources.Requirement.parse(
                    '__placeholder__' + extras
                ).extras,
                {},
            )
        else:
            return None, url_no_extras, None, {}

    for version_control in vcs:
        if url.lower().startswith('%s:' % version_control):
            url = '%s+%s' % (version_control, url)
            break

    if '+' not in url:
        if default_vcs:
            url = default_vcs + '+' + url
        else:
            raise InstallationError(
                '%s should either be a path to a local project or a VCS url '
                'beginning with svn+, git+, hg+, or bzr+' %
                editable_req
            )

    vc_type = url.split('+', 1)[0].lower()

    if not vcs.get_backend(vc_type):
        error_message = 'For --editable=%s only ' % editable_req + \
            ', '.join([backend.name + '+URL' for backend in vcs.backends]) + \
            ' is currently supported'
        raise InstallationError(error_message)

    try:
        options = _build_editable_options(editable_req)
    except Exception as exc:
        raise InstallationError(
            '--editable=%s error in editable options:%s' % (editable_req, exc)
        )
    if not options or 'egg' not in options:
        req = _build_req_from_url(editable_req)
        if not req:
            raise InstallationError(
                '--editable=%s is not the right format; it must have '
                '#egg=Package' % editable_req
            )
    else:
        req = options['egg']

    package = _strip_postfix(req)
    return package, url, None, options
