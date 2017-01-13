# -*- coding: utf-8 -*-
"""
    sphinx.application
    ~~~~~~~~~~~~~~~~~~

    Sphinx application object.

    Gracefully adapted from the TextPress system by Armin.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""
from __future__ import print_function

import os
import sys
import types
import posixpath
import traceback
from os import path
from collections import deque

from six import iteritems, itervalues, text_type
from six.moves import cStringIO
from docutils import nodes
from docutils.parsers.rst import convert_directive_function, \
    directives, roles

import sphinx
from sphinx import package_dir, locale
from sphinx.roles import XRefRole
from sphinx.config import Config
from sphinx.errors import SphinxError, SphinxWarning, ExtensionError, \
    VersionRequirementError, ConfigError
from sphinx.domains import ObjType, BUILTIN_DOMAINS
from sphinx.domains.std import GenericObject, Target, StandardDomain
from sphinx.builders import BUILTIN_BUILDERS
from sphinx.environment import BuildEnvironment
from sphinx.io import SphinxStandaloneReader
from sphinx.util import pycompat  # noqa: F401
from sphinx.util import import_object
from sphinx.util.tags import Tags
from sphinx.util.osutil import ENOENT
from sphinx.util.logging import is_suppressed_warning
from sphinx.util.console import bold, lightgray, darkgray, darkgreen, \
    term_width_line
from sphinx.util.i18n import find_catalog_source_files

if hasattr(sys, 'intern'):
    intern = sys.intern

# List of all known core events. Maps name to arguments description.
events = {
    'builder-inited': '',
    'env-get-outdated': 'env, added, changed, removed',
    'env-purge-doc': 'env, docname',
    'env-before-read-docs': 'env, docnames',
    'source-read': 'docname, source text',
    'doctree-read': 'the doctree before being pickled',
    'env-merge-info': 'env, read docnames, other env instance',
    'missing-reference': 'env, node, contnode',
    'doctree-resolved': 'doctree, docname',
    'env-updated': 'env',
    'html-collect-pages': 'builder',
    'html-page-context': 'pagename, context, doctree or None',
    'build-finished': 'exception',
}

CONFIG_FILENAME = 'conf.py'
ENV_PICKLE_FILENAME = 'environment.pickle'

# list of deprecated extensions. Keys are extension name.
# Values are Sphinx version that merge the extension.
EXTENSION_BLACKLIST = {"sphinxjp.themecore": "1.2"}


class Sphinx(object):

    def __init__(self, srcdir, confdir, outdir, doctreedir, buildername,
                 confoverrides=None, status=sys.stdout, warning=sys.stderr,
                 freshenv=False, warningiserror=False, tags=None, verbosity=0,
                 parallel=0):
        self.verbosity = verbosity
        self.next_listener_id = 0
        self._extensions = {}
        self._extension_metadata = {}
        self._additional_source_parsers = {}
        self._listeners = {}
        self._setting_up_extension = ['?']
        self.domains = BUILTIN_DOMAINS.copy()
        self.buildername = buildername
        self.builderclasses = BUILTIN_BUILDERS.copy()
        self.builder = None
        self.env = None
        self.enumerable_nodes = {}

        self.srcdir = srcdir
        self.confdir = confdir
        self.outdir = outdir
        self.doctreedir = doctreedir

        self.parallel = parallel

        if status is None:
            self._status = cStringIO()
            self.quiet = True
        else:
            self._status = status
            self.quiet = False

        if warning is None:
            self._warning = cStringIO()
        else:
            self._warning = warning
        self._warncount = 0
        self.warningiserror = warningiserror

        self._events = events.copy()
        self._translators = {}

        # keep last few messages for traceback
        self.messagelog = deque(maxlen=10)

        # say hello to the world
        self.info(bold('Running Sphinx v%s' % sphinx.__display_version__))

        # status code for command-line application
        self.statuscode = 0

        if not path.isdir(outdir):
            self.info('making output directory...')
            os.makedirs(outdir)

        # read config
        self.tags = Tags(tags)
        self.config = Config(confdir, CONFIG_FILENAME,
                             confoverrides or {}, self.tags)
        self.config.check_unicode(self.warn)
        # defer checking types until i18n has been initialized

        # initialize some limited config variables before loading extensions
        self.config.pre_init_values(self.warn)

        # check the Sphinx version if requested
        if self.config.needs_sphinx and self.config.needs_sphinx > sphinx.__display_version__:
            raise VersionRequirementError(
                'This project needs at least Sphinx v%s and therefore cannot '
                'be built with this version.' % self.config.needs_sphinx)

        # set confdir to srcdir if -C given (!= no confdir); a few pieces
        # of code expect a confdir to be set
        if self.confdir is None:
            self.confdir = self.srcdir

        # extension loading support for alabaster theme
        # self.config.html_theme is not set from conf.py at here
        # for now, sphinx always load a 'alabaster' extension.
        if 'alabaster' not in self.config.extensions:
            self.config.extensions.append('alabaster')

        # load all user-given extension modules
        for extension in self.config.extensions:
            self.setup_extension(extension)
        # the config file itself can be an extension
        if self.config.setup:
            self._setting_up_extension = ['conf.py']
            # py31 doesn't have 'callable' function for below check
            if hasattr(self.config.setup, '__call__'):
                self.config.setup(self)
            else:
                raise ConfigError(
                    "'setup' that is specified in the conf.py has not been " +
                    "callable. Please provide a callable `setup` function " +
                    "in order to behave as a sphinx extension conf.py itself."
                )

        # now that we know all config values, collect them from conf.py
        self.config.init_values(self.warn)

        # check extension versions if requested
        if self.config.needs_extensions:
            for extname, needs_ver in self.config.needs_extensions.items():
                if extname not in self._extensions:
                    self.warn('needs_extensions config value specifies a '
                              'version requirement for extension %s, but it is '
                              'not loaded' % extname)
                    continue
                has_ver = self._extension_metadata[extname]['version']
                if has_ver == 'unknown version' or needs_ver > has_ver:
                    raise VersionRequirementError(
                        'This project needs the extension %s at least in '
                        'version %s and therefore cannot be built with the '
                        'loaded version (%s).' % (extname, needs_ver, has_ver))

        # set up translation infrastructure
        self._init_i18n()
        # check all configuration values for permissible types
        self.config.check_types(self.warn)
        # set up source_parsers
        self._init_source_parsers()
        # set up the build environment
        self._init_env(freshenv)
        # set up the builder
        self._init_builder(self.buildername)
        # set up the enumerable nodes
        self._init_enumerable_nodes()

    def _init_i18n(self):
        """Load translated strings from the configured localedirs if enabled in
        the configuration.
        """
        if self.config.language is not None:
            self.info(bold('loading translations [%s]... ' %
                           self.config.language), nonl=True)
            user_locale_dirs = [
                path.join(self.srcdir, x) for x in self.config.locale_dirs]
            # compile mo files if sphinx.po file in user locale directories are updated
            for catinfo in find_catalog_source_files(
                    user_locale_dirs, self.config.language, domains=['sphinx'],
                    charset=self.config.source_encoding):
                catinfo.write_mo(self.config.language)
            locale_dirs = [None, path.join(package_dir, 'locale')] + user_locale_dirs
        else:
            locale_dirs = []
        self.translator, has_translation = locale.init(locale_dirs, self.config.language)
        if self.config.language is not None:
            if has_translation or self.config.language == 'en':
                # "en" never needs to be translated
                self.info('done')
            else:
                self.info('not available for built-in messages')

    def _init_source_parsers(self):
        for suffix, parser in iteritems(self._additional_source_parsers):
            if suffix not in self.config.source_suffix:
                self.config.source_suffix.append(suffix)
            if suffix not in self.config.source_parsers:
                self.config.source_parsers[suffix] = parser

    def _init_env(self, freshenv):
        if freshenv:
            self.env = BuildEnvironment(self.srcdir, self.doctreedir, self.config)
            self.env.set_warnfunc(self.warn)
            self.env.find_files(self.config)
            for domain in self.domains.keys():
                self.env.domains[domain] = self.domains[domain](self.env)
        else:
            try:
                self.info(bold('loading pickled environment... '), nonl=True)
                self.env = BuildEnvironment.frompickle(
                    self.srcdir, self.config, path.join(self.doctreedir, ENV_PICKLE_FILENAME))
                self.env.set_warnfunc(self.warn)
                self.env.domains = {}
                for domain in self.domains.keys():
                    # this can raise if the data version doesn't fit
                    self.env.domains[domain] = self.domains[domain](self.env)
                self.info('done')
            except Exception as err:
                if isinstance(err, IOError) and err.errno == ENOENT:
                    self.info('not yet created')
                else:
                    self.info('failed: %s' % err)
                return self._init_env(freshenv=True)

    def _init_builder(self, buildername):
        if buildername is None:
            print('No builder selected, using default: html', file=self._status)
            buildername = 'html'
        if buildername not in self.builderclasses:
            raise SphinxError('Builder name %s not registered' % buildername)

        builderclass = self.builderclasses[buildername]
        if isinstance(builderclass, tuple):
            # builtin builder
            mod, cls = builderclass
            builderclass = getattr(
                __import__('sphinx.builders.' + mod, None, None, [cls]), cls)
        self.builder = builderclass(self)
        self.emit('builder-inited')

    def _init_enumerable_nodes(self):
        for node, settings in iteritems(self.enumerable_nodes):
            self.env.domains['std'].enumerable_nodes[node] = settings

    # ---- main "build" method -------------------------------------------------

    def build(self, force_all=False, filenames=None):
        try:
            if force_all:
                self.builder.compile_all_catalogs()
                self.builder.build_all()
            elif filenames:
                self.builder.compile_specific_catalogs(filenames)
                self.builder.build_specific(filenames)
            else:
                self.builder.compile_update_catalogs()
                self.builder.build_update()

            status = (self.statuscode == 0 and
                      'succeeded' or 'finished with problems')
            if self._warncount:
                self.info(bold('build %s, %s warning%s.' %
                               (status, self._warncount,
                                self._warncount != 1 and 's' or '')))
            else:
                self.info(bold('build %s.' % status))
        except Exception as err:
            # delete the saved env to force a fresh build next time
            envfile = path.join(self.doctreedir, ENV_PICKLE_FILENAME)
            if path.isfile(envfile):
                os.unlink(envfile)
            self.emit('build-finished', err)
            raise
        else:
            self.emit('build-finished', None)
        self.builder.cleanup()

    # ---- logging handling ----------------------------------------------------

    def _log(self, message, wfile, nonl=False):
        try:
            wfile.write(message)
        except UnicodeEncodeError:
            encoding = getattr(wfile, 'encoding', 'ascii') or 'ascii'
            wfile.write(message.encode(encoding, 'replace'))
        if not nonl:
            wfile.write('\n')
        if hasattr(wfile, 'flush'):
            wfile.flush()
        self.messagelog.append(message)

    def warn(self, message, location=None, prefix='WARNING: ', type=None, subtype=None):
        """Emit a warning.

        If *location* is given, it should either be a tuple of (docname, lineno)
        or a string describing the location of the warning as well as possible.

        *prefix* usually should not be changed.

        *type* and *subtype* are used to suppress warnings with :confval:`suppress_warnings`.

        .. note::

           For warnings emitted during parsing, you should use
           :meth:`.BuildEnvironment.warn` since that will collect all
           warnings during parsing for later output.
        """
        if is_suppressed_warning(type, subtype, self.config.suppress_warnings):
            return

        if isinstance(location, tuple):
            docname, lineno = location
            if docname:
                location = '%s:%s' % (self.env.doc2path(docname), lineno or '')
            else:
                location = None
        warntext = location and '%s: %s%s\n' % (location, prefix, message) or \
            '%s%s\n' % (prefix, message)
        if self.warningiserror:
            raise SphinxWarning(warntext)
        self._warncount += 1
        self._log(warntext, self._warning, True)

    def info(self, message='', nonl=False):
        """Emit an informational message.

        If *nonl* is true, don't emit a newline at the end (which implies that
        more info output will follow soon.)
        """
        self._log(message, self._status, nonl)

    def verbose(self, message, *args, **kwargs):
        """Emit a verbose informational message.

        The message will only be emitted for verbosity levels >= 1 (i.e. at
        least one ``-v`` option was given).

        The message can contain %-style interpolation placeholders, which is
        formatted with either the ``*args`` or ``**kwargs`` when output.
        """
        if self.verbosity < 1:
            return
        if args or kwargs:
            message = message % (args or kwargs)
        self._log(message, self._status)

    def debug(self, message, *args, **kwargs):
        """Emit a debug-level informational message.

        The message will only be emitted for verbosity levels >= 2 (i.e. at
        least two ``-v`` options were given).

        The message can contain %-style interpolation placeholders, which is
        formatted with either the ``*args`` or ``**kwargs`` when output.
        """
        if self.verbosity < 2:
            return
        if args or kwargs:
            message = message % (args or kwargs)
        self._log(darkgray(message), self._status)

    def debug2(self, message, *args, **kwargs):
        """Emit a lowlevel debug-level informational message.

        The message will only be emitted for verbosity level 3 (i.e. three
        ``-v`` options were given).

        The message can contain %-style interpolation placeholders, which is
        formatted with either the ``*args`` or ``**kwargs`` when output.
        """
        if self.verbosity < 3:
            return
        if args or kwargs:
            message = message % (args or kwargs)
        self._log(lightgray(message), self._status)

    def _display_chunk(chunk):
        if isinstance(chunk, (list, tuple)):
            if len(chunk) == 1:
                return text_type(chunk[0])
            return '%s .. %s' % (chunk[0], chunk[-1])
        return text_type(chunk)

    def old_status_iterator(self, iterable, summary, colorfunc=darkgreen,
                            stringify_func=_display_chunk):
        l = 0
        for item in iterable:
            if l == 0:
                self.info(bold(summary), nonl=1)
                l = 1
            self.info(colorfunc(stringify_func(item)) + ' ', nonl=1)
            yield item
        if l == 1:
            self.info()

    # new version with progress info
    def status_iterator(self, iterable, summary, colorfunc=darkgreen, length=0,
                        stringify_func=_display_chunk):
        if length == 0:
            for item in self.old_status_iterator(iterable, summary, colorfunc,
                                                 stringify_func):
                yield item
            return
        l = 0
        summary = bold(summary)
        for item in iterable:
            l += 1
            s = '%s[%3d%%] %s' % (summary, 100*l/length,
                                  colorfunc(stringify_func(item)))
            if self.verbosity:
                s += '\n'
            else:
                s = term_width_line(s)
            self.info(s, nonl=1)
            yield item
        if l > 0:
            self.info()

    # ---- general extensibility interface -------------------------------------

    def setup_extension(self, extension):
        """Import and setup a Sphinx extension module. No-op if called twice."""
        self.debug('[app] setting up extension: %r', extension)
        if extension in self._extensions:
            return
        if extension in EXTENSION_BLACKLIST:
            self.warn('the extension %r was already merged with Sphinx since version %s; '
                      'this extension is ignored.' % (
                          extension, EXTENSION_BLACKLIST[extension]))
            return
        self._setting_up_extension.append(extension)
        try:
            mod = __import__(extension, None, None, ['setup'])
        except ImportError as err:
            self.verbose('Original exception:\n' + traceback.format_exc())
            raise ExtensionError('Could not import extension %s' % extension,
                                 err)
        if not hasattr(mod, 'setup'):
            self.warn('extension %r has no setup() function; is it really '
                      'a Sphinx extension module?' % extension)
            ext_meta = None
        else:
            try:
                ext_meta = mod.setup(self)
            except VersionRequirementError as err:
                # add the extension name to the version required
                raise VersionRequirementError(
                    'The %s extension used by this project needs at least '
                    'Sphinx v%s; it therefore cannot be built with this '
                    'version.' % (extension, err))
        if ext_meta is None:
            ext_meta = {}
            # special-case for compatibility
            if extension == 'rst2pdf.pdfbuilder':
                ext_meta = {'parallel_read_safe': True}
        try:
            if not ext_meta.get('version'):
                ext_meta['version'] = 'unknown version'
        except Exception:
            self.warn('extension %r returned an unsupported object from '
                      'its setup() function; it should return None or a '
                      'metadata dictionary' % extension)
            ext_meta = {'version': 'unknown version'}
        self._extensions[extension] = mod
        self._extension_metadata[extension] = ext_meta
        self._setting_up_extension.pop()

    def require_sphinx(self, version):
        # check the Sphinx version if requested
        if version > sphinx.__display_version__[:3]:
            raise VersionRequirementError(version)

    def import_object(self, objname, source=None):
        """Import an object from a 'module.name' string."""
        return import_object(objname, source=None)

    # event interface

    def _validate_event(self, event):
        event = intern(event)
        if event not in self._events:
            raise ExtensionError('Unknown event name: %s' % event)

    def connect(self, event, callback):
        self._validate_event(event)
        listener_id = self.next_listener_id
        if event not in self._listeners:
            self._listeners[event] = {listener_id: callback}
        else:
            self._listeners[event][listener_id] = callback
        self.next_listener_id += 1
        self.debug('[app] connecting event %r: %r [id=%s]',
                   event, callback, listener_id)
        return listener_id

    def disconnect(self, listener_id):
        self.debug('[app] disconnecting event: [id=%s]', listener_id)
        for event in itervalues(self._listeners):
            event.pop(listener_id, None)

    def emit(self, event, *args):
        try:
            self.debug2('[app] emitting event: %r%s', event, repr(args)[:100])
        except Exception:
            # not every object likes to be repr()'d (think
            # random stuff coming via autodoc)
            pass
        results = []
        if event in self._listeners:
            for _, callback in iteritems(self._listeners[event]):
                results.append(callback(self, *args))
        return results

    def emit_firstresult(self, event, *args):
        for result in self.emit(event, *args):
            if result is not None:
                return result
        return None

    # registering addon parts

    def add_builder(self, builder):
        self.debug('[app] adding builder: %r', builder)
        if not hasattr(builder, 'name'):
            raise ExtensionError('Builder class %s has no "name" attribute'
                                 % builder)
        if builder.name in self.builderclasses:
            if isinstance(self.builderclasses[builder.name], tuple):
                raise ExtensionError('Builder %r is a builtin builder' %
                                     builder.name)
            else:
                raise ExtensionError(
                    'Builder %r already exists (in module %s)' % (
                        builder.name, self.builderclasses[builder.name].__module__))
        self.builderclasses[builder.name] = builder

    def add_config_value(self, name, default, rebuild, types=()):
        self.debug('[app] adding config value: %r',
                   (name, default, rebuild) + ((types,) if types else ()))
        if name in self.config.values:
            raise ExtensionError('Config value %r already present' % name)
        if rebuild in (False, True):
            rebuild = rebuild and 'env' or ''
        self.config.values[name] = (default, rebuild, types)

    def add_event(self, name):
        self.debug('[app] adding event: %r', name)
        if name in self._events:
            raise ExtensionError('Event %r already present' % name)
        self._events[name] = ''

    def set_translator(self, name, translator_class):
        self.info(bold('A Translator for the %s builder is changed.' % name))
        self._translators[name] = translator_class

    def add_node(self, node, **kwds):
        self.debug('[app] adding node: %r', (node, kwds))
        if not kwds.pop('override', False) and \
           hasattr(nodes.GenericNodeVisitor, 'visit_' + node.__name__):
            self.warn('while setting up extension %s: node class %r is '
                      'already registered, its visitors will be overridden' %
                      (self._setting_up_extension, node.__name__),
                      type='app', subtype='add_node')
        nodes._add_node_class_names([node.__name__])
        for key, val in iteritems(kwds):
            try:
                visit, depart = val
            except ValueError:
                raise ExtensionError('Value for key %r must be a '
                                     '(visit, depart) function tuple' % key)
            translator = self._translators.get(key)
            if translator is not None:
                pass
            elif key == 'html':
                from sphinx.writers.html import HTMLTranslator as translator
            elif key == 'latex':
                from sphinx.writers.latex import LaTeXTranslator as translator
            elif key == 'text':
                from sphinx.writers.text import TextTranslator as translator
            elif key == 'man':
                from sphinx.writers.manpage import ManualPageTranslator \
                    as translator
            elif key == 'texinfo':
                from sphinx.writers.texinfo import TexinfoTranslator \
                    as translator
            else:
                # ignore invalid keys for compatibility
                continue
            setattr(translator, 'visit_'+node.__name__, visit)
            if depart:
                setattr(translator, 'depart_'+node.__name__, depart)

    def add_enumerable_node(self, node, figtype, title_getter=None, **kwds):
        self.enumerable_nodes[node] = (figtype, title_getter)
        self.add_node(node, **kwds)

    def _directive_helper(self, obj, content=None, arguments=None, **options):
        if isinstance(obj, (types.FunctionType, types.MethodType)):
            obj.content = content
            obj.arguments = arguments or (0, 0, False)
            obj.options = options
            return convert_directive_function(obj)
        else:
            if content or arguments or options:
                raise ExtensionError('when adding directive classes, no '
                                     'additional arguments may be given')
            return obj

    def add_directive(self, name, obj, content=None, arguments=None, **options):
        self.debug('[app] adding directive: %r',
                   (name, obj, content, arguments, options))
        if name in directives._directives:
            self.warn('while setting up extension %s: directive %r is '
                      'already registered, it will be overridden' %
                      (self._setting_up_extension[-1], name),
                      type='app', subtype='add_directive')
        directives.register_directive(
            name, self._directive_helper(obj, content, arguments, **options))

    def add_role(self, name, role):
        self.debug('[app] adding role: %r', (name, role))
        if name in roles._roles:
            self.warn('while setting up extension %s: role %r is '
                      'already registered, it will be overridden' %
                      (self._setting_up_extension[-1], name),
                      type='app', subtype='add_role')
        roles.register_local_role(name, role)

    def add_generic_role(self, name, nodeclass):
        # don't use roles.register_generic_role because it uses
        # register_canonical_role
        self.debug('[app] adding generic role: %r', (name, nodeclass))
        if name in roles._roles:
            self.warn('while setting up extension %s: role %r is '
                      'already registered, it will be overridden' %
                      (self._setting_up_extension[-1], name),
                      type='app', subtype='add_generic_role')
        role = roles.GenericRole(name, nodeclass)
        roles.register_local_role(name, role)

    def add_domain(self, domain):
        self.debug('[app] adding domain: %r', domain)
        if domain.name in self.domains:
            raise ExtensionError('domain %s already registered' % domain.name)
        self.domains[domain.name] = domain

    def override_domain(self, domain):
        self.debug('[app] overriding domain: %r', domain)
        if domain.name not in self.domains:
            raise ExtensionError('domain %s not yet registered' % domain.name)
        if not issubclass(domain, self.domains[domain.name]):
            raise ExtensionError('new domain not a subclass of registered %s '
                                 'domain' % domain.name)
        self.domains[domain.name] = domain

    def add_directive_to_domain(self, domain, name, obj,
                                content=None, arguments=None, **options):
        self.debug('[app] adding directive to domain: %r',
                   (domain, name, obj, content, arguments, options))
        if domain not in self.domains:
            raise ExtensionError('domain %s not yet registered' % domain)
        self.domains[domain].directives[name] = \
            self._directive_helper(obj, content, arguments, **options)

    def add_role_to_domain(self, domain, name, role):
        self.debug('[app] adding role to domain: %r', (domain, name, role))
        if domain not in self.domains:
            raise ExtensionError('domain %s not yet registered' % domain)
        self.domains[domain].roles[name] = role

    def add_index_to_domain(self, domain, index):
        self.debug('[app] adding index to domain: %r', (domain, index))
        if domain not in self.domains:
            raise ExtensionError('domain %s not yet registered' % domain)
        self.domains[domain].indices.append(index)

    def add_object_type(self, directivename, rolename, indextemplate='',
                        parse_node=None, ref_nodeclass=None, objname='',
                        doc_field_types=[]):
        self.debug('[app] adding object type: %r',
                   (directivename, rolename, indextemplate, parse_node,
                    ref_nodeclass, objname, doc_field_types))
        StandardDomain.object_types[directivename] = \
            ObjType(objname or directivename, rolename)
        # create a subclass of GenericObject as the new directive
        new_directive = type(directivename, (GenericObject, object),
                             {'indextemplate': indextemplate,
                              'parse_node': staticmethod(parse_node),
                              'doc_field_types': doc_field_types})
        StandardDomain.directives[directivename] = new_directive
        # XXX support more options?
        StandardDomain.roles[rolename] = XRefRole(innernodeclass=ref_nodeclass)

    # backwards compatible alias
    add_description_unit = add_object_type

    def add_crossref_type(self, directivename, rolename, indextemplate='',
                          ref_nodeclass=None, objname=''):
        self.debug('[app] adding crossref type: %r',
                   (directivename, rolename, indextemplate, ref_nodeclass,
                    objname))
        StandardDomain.object_types[directivename] = \
            ObjType(objname or directivename, rolename)
        # create a subclass of Target as the new directive
        new_directive = type(directivename, (Target, object),
                             {'indextemplate': indextemplate})
        StandardDomain.directives[directivename] = new_directive
        # XXX support more options?
        StandardDomain.roles[rolename] = XRefRole(innernodeclass=ref_nodeclass)

    def add_transform(self, transform):
        self.debug('[app] adding transform: %r', transform)
        SphinxStandaloneReader.transforms.append(transform)

    def add_javascript(self, filename):
        self.debug('[app] adding javascript: %r', filename)
        from sphinx.builders.html import StandaloneHTMLBuilder
        if '://' in filename:
            StandaloneHTMLBuilder.script_files.append(filename)
        else:
            StandaloneHTMLBuilder.script_files.append(
                posixpath.join('_static', filename))

    def add_stylesheet(self, filename):
        self.debug('[app] adding stylesheet: %r', filename)
        from sphinx.builders.html import StandaloneHTMLBuilder
        if '://' in filename:
            StandaloneHTMLBuilder.css_files.append(filename)
        else:
            StandaloneHTMLBuilder.css_files.append(
                posixpath.join('_static', filename))

    def add_latex_package(self, packagename, options=None):
        self.debug('[app] adding latex package: %r', packagename)
        from sphinx.builders.latex import LaTeXBuilder
        LaTeXBuilder.usepackages.append((packagename, options))

    def add_lexer(self, alias, lexer):
        self.debug('[app] adding lexer: %r', (alias, lexer))
        from sphinx.highlighting import lexers
        if lexers is None:
            return
        lexers[alias] = lexer

    def add_autodocumenter(self, cls):
        self.debug('[app] adding autodocumenter: %r', cls)
        from sphinx.ext import autodoc
        autodoc.add_documenter(cls)
        self.add_directive('auto' + cls.objtype, autodoc.AutoDirective)

    def add_autodoc_attrgetter(self, type, getter):
        self.debug('[app] adding autodoc attrgetter: %r', (type, getter))
        from sphinx.ext import autodoc
        autodoc.AutoDirective._special_attrgetters[type] = getter

    def add_search_language(self, cls):
        self.debug('[app] adding search language: %r', cls)
        from sphinx.search import languages, SearchLanguage
        assert issubclass(cls, SearchLanguage)
        languages[cls.lang] = cls

    def add_source_parser(self, suffix, parser):
        self.debug('[app] adding search source_parser: %r, %r', (suffix, parser))
        if suffix in self._additional_source_parsers:
            self.warn('while setting up extension %s: source_parser for %r is '
                      'already registered, it will be overridden' %
                      (self._setting_up_extension[-1], suffix),
                      type='app', subtype='add_source_parser')
        self._additional_source_parsers[suffix] = parser


class TemplateBridge(object):
    """
    This class defines the interface for a "template bridge", that is, a class
    that renders templates given a template name and a context.
    """

    def init(self, builder, theme=None, dirs=None):
        """Called by the builder to initialize the template system.

        *builder* is the builder object; you'll probably want to look at the
        value of ``builder.config.templates_path``.

        *theme* is a :class:`sphinx.theming.Theme` object or None; in the latter
        case, *dirs* can be list of fixed directories to look for templates.
        """
        raise NotImplementedError('must be implemented in subclasses')

    def newest_template_mtime(self):
        """Called by the builder to determine if output files are outdated
        because of template changes.  Return the mtime of the newest template
        file that was changed.  The default implementation returns ``0``.
        """
        return 0

    def render(self, template, context):
        """Called by the builder to render a template given as a filename with
        a specified context (a Python dictionary).
        """
        raise NotImplementedError('must be implemented in subclasses')

    def render_string(self, template, context):
        """Called by the builder to render a template given as a string with a
        specified context (a Python dictionary).
        """
        raise NotImplementedError('must be implemented in subclasses')
