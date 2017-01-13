# -*- coding: utf-8 -*-
"""
    sphinx.environment
    ~~~~~~~~~~~~~~~~~~

    Global creation environment.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import re
import os
import sys
import time
import types
import bisect
import codecs
import string
import fnmatch
import unicodedata
from os import path
from glob import glob
from itertools import groupby

from six import iteritems, itervalues, text_type, class_types, next
from six.moves import cPickle as pickle
from docutils import nodes
from docutils.io import NullOutput
from docutils.core import Publisher
from docutils.utils import Reporter, relative_path, get_source_line
from docutils.parsers.rst import roles, directives
from docutils.parsers.rst.languages import en as english
from docutils.parsers.rst.directives.html import MetaBody
from docutils.frontend import OptionParser

from sphinx import addnodes
from sphinx.io import SphinxStandaloneReader, SphinxDummyWriter, SphinxFileInput
from sphinx.util import url_re, get_matching_docs, docname_join, split_into, \
    FilenameUniqDict, split_index_msg
from sphinx.util.nodes import clean_astext, make_refnode, WarningStream, is_translatable
from sphinx.util.osutil import SEP, getcwd, fs_encoding, ensuredir
from sphinx.util.images import guess_mimetype
from sphinx.util.i18n import find_catalog_files, get_image_filename_for_language, \
    search_image_for_language
from sphinx.util.console import bold, purple
from sphinx.util.matching import compile_matchers
from sphinx.util.parallel import ParallelTasks, parallel_available, make_chunks
from sphinx.util.websupport import is_commentable
from sphinx.errors import SphinxError, ExtensionError
from sphinx.locale import _
from sphinx.versioning import add_uids, merge_doctrees
from sphinx.transforms import SphinxContentsFilter

orig_role_function = roles.role
orig_directive_function = directives.directive


class ElementLookupError(Exception):
    pass


default_settings = {
    'embed_stylesheet': False,
    'cloak_email_addresses': True,
    'pep_base_url': 'https://www.python.org/dev/peps/',
    'rfc_base_url': 'https://tools.ietf.org/html/',
    'input_encoding': 'utf-8-sig',
    'doctitle_xform': False,
    'sectsubtitle_xform': False,
    'halt_level': 5,
    'file_insertion_enabled': True,
}

# This is increased every time an environment attribute is added
# or changed to properly invalidate pickle files.
#
# NOTE: increase base version by 2 to have distinct numbers for Py2 and 3
ENV_VERSION = 49 + (sys.version_info[0] - 2)


dummy_reporter = Reporter('', 4, 4)

versioning_conditions = {
    'none': False,
    'text': is_translatable,
    'commentable': is_commentable,
}


class NoUri(Exception):
    """Raised by get_relative_uri if there is no URI available."""
    pass


class BuildEnvironment:
    """
    The environment in which the ReST files are translated.
    Stores an inventory of cross-file targets and provides doctree
    transformations to resolve links to them.
    """

    # --------- ENVIRONMENT PERSISTENCE ----------------------------------------

    @staticmethod
    def frompickle(srcdir, config, filename):
        picklefile = open(filename, 'rb')
        try:
            env = pickle.load(picklefile)
        finally:
            picklefile.close()
        if env.version != ENV_VERSION:
            raise IOError('build environment version not current')
        if env.srcdir != srcdir:
            raise IOError('source directory has changed')
        env.config.values = config.values
        return env

    def topickle(self, filename):
        # remove unpicklable attributes
        warnfunc = self._warnfunc
        self.set_warnfunc(None)
        values = self.config.values
        del self.config.values
        domains = self.domains
        del self.domains
        picklefile = open(filename, 'wb')
        # remove potentially pickling-problematic values from config
        for key, val in list(vars(self.config).items()):
            if key.startswith('_') or \
               isinstance(val, types.ModuleType) or \
               isinstance(val, types.FunctionType) or \
               isinstance(val, class_types):
                del self.config[key]
        try:
            pickle.dump(self, picklefile, pickle.HIGHEST_PROTOCOL)
        finally:
            picklefile.close()
        # reset attributes
        self.domains = domains
        self.config.values = values
        self.set_warnfunc(warnfunc)

    # --------- ENVIRONMENT INITIALIZATION -------------------------------------

    def __init__(self, srcdir, doctreedir, config):
        self.doctreedir = doctreedir
        self.srcdir = srcdir
        self.config = config

        # the method of doctree versioning; see set_versioning_method
        self.versioning_condition = None
        self.versioning_compare = None

        # the application object; only set while update() runs
        self.app = None

        # all the registered domains, set by the application
        self.domains = {}

        # the docutils settings for building
        self.settings = default_settings.copy()
        self.settings['env'] = self

        # the function to write warning messages with
        self._warnfunc = None

        # this is to invalidate old pickles
        self.version = ENV_VERSION

        # All "docnames" here are /-separated and relative and exclude
        # the source suffix.

        self.found_docs = set()     # contains all existing docnames
        self.all_docs = {}          # docname -> mtime at the time of reading
                                    # contains all read docnames
        self.dependencies = {}      # docname -> set of dependent file
                                    # names, relative to documentation root
        self.included = set()       # docnames included from other documents
        self.reread_always = set()  # docnames to re-read unconditionally on
                                    # next build

        # File metadata
        self.metadata = {}          # docname -> dict of metadata items

        # TOC inventory
        self.titles = {}            # docname -> title node
        self.longtitles = {}        # docname -> title node; only different if
                                    # set differently with title directive
        self.tocs = {}              # docname -> table of contents nodetree
        self.toc_num_entries = {}   # docname -> number of real entries
        # used to determine when to show the TOC
        # in a sidebar (don't show if it's only one item)
        self.toc_secnumbers = {}    # docname -> dict of sectionid -> number
        self.toc_fignumbers = {}    # docname -> dict of figtype ->
                                    # dict of figureid -> number

        self.toctree_includes = {}  # docname -> list of toctree includefiles
        self.files_to_rebuild = {}  # docname -> set of files
                                    # (containing its TOCs) to rebuild too
        self.glob_toctrees = set()  # docnames that have :glob: toctrees
        self.numbered_toctrees = set()  # docnames that have :numbered: toctrees

        # domain-specific inventories, here to be pickled
        self.domaindata = {}        # domainname -> domain-specific dict

        # Other inventories
        self.citations = {}         # citation name -> docname, labelid
        self.indexentries = {}      # docname -> list of
                                    # (type, string, target, aliasname)
        self.versionchanges = {}    # version -> list of (type, docname,
                                    # lineno, module, descname, content)

        # these map absolute path -> (docnames, unique filename)
        self.images = FilenameUniqDict()
        self.dlfiles = FilenameUniqDict()

        # temporary data storage while reading a document
        self.temp_data = {}
        # context for cross-references (e.g. current module or class)
        # this is similar to temp_data, but will for example be copied to
        # attributes of "any" cross references
        self.ref_context = {}

    def set_warnfunc(self, func):
        self._warnfunc = func
        self.settings['warning_stream'] = WarningStream(func)

    def set_versioning_method(self, method, compare):
        """This sets the doctree versioning method for this environment.

        Versioning methods are a builder property; only builders with the same
        versioning method can share the same doctree directory.  Therefore, we
        raise an exception if the user tries to use an environment with an
        incompatible versioning method.
        """
        if method not in versioning_conditions:
            raise ValueError('invalid versioning method: %r' % method)
        condition = versioning_conditions[method]
        if self.versioning_condition not in (None, condition):
            raise SphinxError('This environment is incompatible with the '
                              'selected builder, please choose another '
                              'doctree directory.')
        self.versioning_condition = condition
        self.versioning_compare = compare

    def warn(self, docname, msg, lineno=None, **kwargs):
        """Emit a warning.

        This differs from using ``app.warn()`` in that the warning may not
        be emitted instantly, but collected for emitting all warnings after
        the update of the environment.
        """
        # strange argument order is due to backwards compatibility
        self._warnfunc(msg, (docname, lineno), **kwargs)

    def warn_node(self, msg, node, **kwargs):
        """Like :meth:`warn`, but with source information taken from *node*."""
        self._warnfunc(msg, '%s:%s' % get_source_line(node), **kwargs)

    def clear_doc(self, docname):
        """Remove all traces of a source file in the inventory."""
        if docname in self.all_docs:
            self.all_docs.pop(docname, None)
            self.reread_always.discard(docname)
            self.metadata.pop(docname, None)
            self.dependencies.pop(docname, None)
            self.titles.pop(docname, None)
            self.longtitles.pop(docname, None)
            self.tocs.pop(docname, None)
            self.toc_secnumbers.pop(docname, None)
            self.toc_fignumbers.pop(docname, None)
            self.toc_num_entries.pop(docname, None)
            self.toctree_includes.pop(docname, None)
            self.indexentries.pop(docname, None)
            self.glob_toctrees.discard(docname)
            self.numbered_toctrees.discard(docname)
            self.images.purge_doc(docname)
            self.dlfiles.purge_doc(docname)

            for subfn, fnset in list(self.files_to_rebuild.items()):
                fnset.discard(docname)
                if not fnset:
                    del self.files_to_rebuild[subfn]
            for key, (fn, _ignore) in list(self.citations.items()):
                if fn == docname:
                    del self.citations[key]
            for version, changes in self.versionchanges.items():
                new = [change for change in changes if change[1] != docname]
                changes[:] = new

        for domain in self.domains.values():
            domain.clear_doc(docname)

    def merge_info_from(self, docnames, other, app):
        """Merge global information gathered about *docnames* while reading them
        from the *other* environment.

        This possibly comes from a parallel build process.
        """
        docnames = set(docnames)
        for docname in docnames:
            self.all_docs[docname] = other.all_docs[docname]
            if docname in other.reread_always:
                self.reread_always.add(docname)
            self.metadata[docname] = other.metadata[docname]
            if docname in other.dependencies:
                self.dependencies[docname] = other.dependencies[docname]
            self.titles[docname] = other.titles[docname]
            self.longtitles[docname] = other.longtitles[docname]
            self.tocs[docname] = other.tocs[docname]
            self.toc_num_entries[docname] = other.toc_num_entries[docname]
            # toc_secnumbers and toc_fignumbers are not assigned during read
            if docname in other.toctree_includes:
                self.toctree_includes[docname] = other.toctree_includes[docname]
            self.indexentries[docname] = other.indexentries[docname]
            if docname in other.glob_toctrees:
                self.glob_toctrees.add(docname)
            if docname in other.numbered_toctrees:
                self.numbered_toctrees.add(docname)

        self.images.merge_other(docnames, other.images)
        self.dlfiles.merge_other(docnames, other.dlfiles)

        for subfn, fnset in other.files_to_rebuild.items():
            self.files_to_rebuild.setdefault(subfn, set()).update(fnset & docnames)
        for key, data in other.citations.items():
            # XXX duplicates?
            if data[0] in docnames:
                self.citations[key] = data
        for version, changes in other.versionchanges.items():
            self.versionchanges.setdefault(version, []).extend(
                change for change in changes if change[1] in docnames)

        for domainname, domain in self.domains.items():
            domain.merge_domaindata(docnames, other.domaindata[domainname])
        app.emit('env-merge-info', self, docnames, other)

    def path2doc(self, filename):
        """Return the docname for the filename if the file is document.

        *filename* should be absolute or relative to the source directory.
        """
        if filename.startswith(self.srcdir):
            filename = filename[len(self.srcdir) + 1:]
        for suffix in self.config.source_suffix:
            if fnmatch.fnmatch(filename, '*' + suffix):
                return filename[:-len(suffix)]
        else:
            # the file does not have docname
            return None

    def doc2path(self, docname, base=True, suffix=None):
        """Return the filename for the document name.

        If *base* is True, return absolute path under self.srcdir.
        If *base* is None, return relative path to self.srcdir.
        If *base* is a path string, return absolute path under that.
        If *suffix* is not None, add it instead of config.source_suffix.
        """
        docname = docname.replace(SEP, path.sep)
        if suffix is None:
            for candidate_suffix in self.config.source_suffix:
                if path.isfile(path.join(self.srcdir, docname) +
                               candidate_suffix):
                    suffix = candidate_suffix
                    break
            else:
                # document does not exist
                suffix = self.config.source_suffix[0]
        if base is True:
            return path.join(self.srcdir, docname) + suffix
        elif base is None:
            return docname + suffix
        else:
            return path.join(base, docname) + suffix

    def relfn2path(self, filename, docname=None):
        """Return paths to a file referenced from a document, relative to
        documentation root and absolute.

        In the input "filename", absolute filenames are taken as relative to the
        source dir, while relative filenames are relative to the dir of the
        containing document.
        """
        if filename.startswith('/') or filename.startswith(os.sep):
            rel_fn = filename[1:]
        else:
            docdir = path.dirname(self.doc2path(docname or self.docname,
                                                base=None))
            rel_fn = path.join(docdir, filename)
        try:
            # the path.abspath() might seem redundant, but otherwise artifacts
            # such as ".." will remain in the path
            return rel_fn, path.abspath(path.join(self.srcdir, rel_fn))
        except UnicodeDecodeError:
            # the source directory is a bytestring with non-ASCII characters;
            # let's try to encode the rel_fn in the file system encoding
            enc_rel_fn = rel_fn.encode(sys.getfilesystemencoding())
            return rel_fn, path.abspath(path.join(self.srcdir, enc_rel_fn))

    def find_files(self, config):
        """Find all source files in the source dir and put them in
        self.found_docs.
        """
        matchers = compile_matchers(
            config.exclude_patterns[:] +
            config.templates_path +
            config.html_extra_path +
            ['**/_sources', '.#*', '**/.#*', '*.lproj/**']
        )
        self.found_docs = set()
        for docname in get_matching_docs(self.srcdir, config.source_suffix,
                                         exclude_matchers=matchers):
            if os.access(self.doc2path(docname), os.R_OK):
                self.found_docs.add(docname)
            else:
                self.warn(docname, "document not readable. Ignored.")

        # add catalog mo file dependency
        for docname in self.found_docs:
            catalog_files = find_catalog_files(
                docname,
                self.srcdir,
                self.config.locale_dirs,
                self.config.language,
                self.config.gettext_compact)
            for filename in catalog_files:
                self.dependencies.setdefault(docname, set()).add(filename)

    def get_outdated_files(self, config_changed):
        """Return (added, changed, removed) sets."""
        # clear all files no longer present
        removed = set(self.all_docs) - self.found_docs

        added = set()
        changed = set()

        if config_changed:
            # config values affect e.g. substitutions
            added = self.found_docs
        else:
            for docname in self.found_docs:
                if docname not in self.all_docs:
                    added.add(docname)
                    continue
                # if the doctree file is not there, rebuild
                if not path.isfile(self.doc2path(docname, self.doctreedir,
                                                 '.doctree')):
                    changed.add(docname)
                    continue
                # check the "reread always" list
                if docname in self.reread_always:
                    changed.add(docname)
                    continue
                # check the mtime of the document
                mtime = self.all_docs[docname]
                newmtime = path.getmtime(self.doc2path(docname))
                if newmtime > mtime:
                    changed.add(docname)
                    continue
                # finally, check the mtime of dependencies
                for dep in self.dependencies.get(docname, ()):
                    try:
                        # this will do the right thing when dep is absolute too
                        deppath = path.join(self.srcdir, dep)
                        if not path.isfile(deppath):
                            changed.add(docname)
                            break
                        depmtime = path.getmtime(deppath)
                        if depmtime > mtime:
                            changed.add(docname)
                            break
                    except EnvironmentError:
                        # give it another chance
                        changed.add(docname)
                        break

        return added, changed, removed

    def update(self, config, srcdir, doctreedir, app):
        """(Re-)read all files new or changed since last update.

        Store all environment docnames in the canonical format (ie using SEP as
        a separator in place of os.path.sep).
        """
        config_changed = False
        if self.config is None:
            msg = '[new config] '
            config_changed = True
        else:
            # check if a config value was changed that affects how
            # doctrees are read
            for key, descr in iteritems(config.values):
                if descr[1] != 'env':
                    continue
                if self.config[key] != config[key]:
                    msg = '[config changed] '
                    config_changed = True
                    break
            else:
                msg = ''
            # this value is not covered by the above loop because it is handled
            # specially by the config class
            if self.config.extensions != config.extensions:
                msg = '[extensions changed] '
                config_changed = True
        # the source and doctree directories may have been relocated
        self.srcdir = srcdir
        self.doctreedir = doctreedir
        self.find_files(config)
        self.config = config

        # this cache also needs to be updated every time
        self._nitpick_ignore = set(self.config.nitpick_ignore)

        app.info(bold('updating environment: '), nonl=1)

        added, changed, removed = self.get_outdated_files(config_changed)

        # allow user intervention as well
        for docs in app.emit('env-get-outdated', self, added, changed, removed):
            changed.update(set(docs) & self.found_docs)

        # if files were added or removed, all documents with globbed toctrees
        # must be reread
        if added or removed:
            # ... but not those that already were removed
            changed.update(self.glob_toctrees & self.found_docs)

        msg += '%s added, %s changed, %s removed' % (len(added), len(changed),
                                                     len(removed))
        app.info(msg)

        self.app = app

        # clear all files no longer present
        for docname in removed:
            app.emit('env-purge-doc', self, docname)
            self.clear_doc(docname)

        # read all new and changed files
        docnames = sorted(added | changed)
        # allow changing and reordering the list of docs to read
        app.emit('env-before-read-docs', self, docnames)

        # check if we should do parallel or serial read
        par_ok = False
        if parallel_available and len(docnames) > 5 and app.parallel > 1:
            par_ok = True
            for extname, md in app._extension_metadata.items():
                ext_ok = md.get('parallel_read_safe')
                if ext_ok:
                    continue
                if ext_ok is None:
                    app.warn('the %s extension does not declare if it '
                             'is safe for parallel reading, assuming it '
                             'isn\'t - please ask the extension author to '
                             'check and make it explicit' % extname)
                    app.warn('doing serial read')
                else:
                    app.warn('the %s extension is not safe for parallel '
                             'reading, doing serial read' % extname)
                par_ok = False
                break
        if par_ok:
            self._read_parallel(docnames, app, nproc=app.parallel)
        else:
            self._read_serial(docnames, app)

        if config.master_doc not in self.all_docs:
            raise SphinxError('master file %s not found' %
                              self.doc2path(config.master_doc))

        self.app = None

        for retval in app.emit('env-updated', self):
            if retval is not None:
                docnames.extend(retval)

        return sorted(docnames)

    def _read_serial(self, docnames, app):
        for docname in app.status_iterator(docnames, 'reading sources... ',
                                           purple, len(docnames)):
            # remove all inventory entries for that file
            app.emit('env-purge-doc', self, docname)
            self.clear_doc(docname)
            self.read_doc(docname, app)

    def _read_parallel(self, docnames, app, nproc):
        # clear all outdated docs at once
        for docname in docnames:
            app.emit('env-purge-doc', self, docname)
            self.clear_doc(docname)

        def read_process(docs):
            self.app = app
            self.warnings = []
            self.set_warnfunc(lambda *args, **kwargs: self.warnings.append((args, kwargs)))
            for docname in docs:
                self.read_doc(docname, app)
            # allow pickling self to send it back
            self.set_warnfunc(None)
            del self.app
            del self.domains
            del self.config.values
            del self.config
            return self

        def merge(docs, otherenv):
            warnings.extend(otherenv.warnings)
            self.merge_info_from(docs, otherenv, app)

        tasks = ParallelTasks(nproc)
        chunks = make_chunks(docnames, nproc)

        warnings = []
        for chunk in app.status_iterator(
                chunks, 'reading sources... ', purple, len(chunks)):
            tasks.add_task(read_process, chunk, merge)

        # make sure all threads have finished
        app.info(bold('waiting for workers...'))
        tasks.join()

        for warning, kwargs in warnings:
            self._warnfunc(*warning, **kwargs)

    def check_dependents(self, already):
        to_rewrite = self.assign_section_numbers() + self.assign_figure_numbers()
        for docname in set(to_rewrite):
            if docname not in already:
                yield docname

    # --------- SINGLE FILE READING --------------------------------------------

    def warn_and_replace(self, error):
        """Custom decoding error handler that warns and replaces."""
        linestart = error.object.rfind(b'\n', 0, error.start)
        lineend = error.object.find(b'\n', error.start)
        if lineend == -1:
            lineend = len(error.object)
        lineno = error.object.count(b'\n', 0, error.start) + 1
        self.warn(self.docname, 'undecodable source characters, '
                  'replacing with "?": %r' %
                  (error.object[linestart+1:error.start] + b'>>>' +
                   error.object[error.start:error.end] + b'<<<' +
                   error.object[error.end:lineend]), lineno)
        return (u'?', error.end)

    def lookup_domain_element(self, type, name):
        """Lookup a markup element (directive or role), given its name which can
        be a full name (with domain).
        """
        name = name.lower()
        # explicit domain given?
        if ':' in name:
            domain_name, name = name.split(':', 1)
            if domain_name in self.domains:
                domain = self.domains[domain_name]
                element = getattr(domain, type)(name)
                if element is not None:
                    return element, []
        # else look in the default domain
        else:
            def_domain = self.temp_data.get('default_domain')
            if def_domain is not None:
                element = getattr(def_domain, type)(name)
                if element is not None:
                    return element, []
        # always look in the std domain
        element = getattr(self.domains['std'], type)(name)
        if element is not None:
            return element, []
        raise ElementLookupError

    def patch_lookup_functions(self):
        """Monkey-patch directive and role dispatch, so that domain-specific
        markup takes precedence.
        """
        def directive(name, lang_module, document):
            try:
                return self.lookup_domain_element('directive', name)
            except ElementLookupError:
                return orig_directive_function(name, lang_module, document)

        def role(name, lang_module, lineno, reporter):
            try:
                return self.lookup_domain_element('role', name)
            except ElementLookupError:
                return orig_role_function(name, lang_module, lineno, reporter)

        directives.directive = directive
        roles.role = role

    def read_doc(self, docname, app=None):
        """Parse a file and add/update inventory entries for the doctree."""

        self.temp_data['docname'] = docname
        # defaults to the global default, but can be re-set in a document
        self.temp_data['default_domain'] = \
            self.domains.get(self.config.primary_domain)

        self.settings['input_encoding'] = self.config.source_encoding
        self.settings['trim_footnote_reference_space'] = \
            self.config.trim_footnote_reference_space
        self.settings['gettext_compact'] = self.config.gettext_compact

        self.patch_lookup_functions()

        docutilsconf = path.join(self.srcdir, 'docutils.conf')
        # read docutils.conf from source dir, not from current dir
        OptionParser.standard_config_files[1] = docutilsconf
        if path.isfile(docutilsconf):
            self.note_dependency(docutilsconf)

        if self.config.default_role:
            role_fn, messages = roles.role(self.config.default_role, english,
                                           0, dummy_reporter)
            if role_fn:
                roles._roles[''] = role_fn
            else:
                self.warn(docname, 'default role %s not found' %
                          self.config.default_role)

        codecs.register_error('sphinx', self.warn_and_replace)

        # publish manually
        reader = SphinxStandaloneReader(self.app, parsers=self.config.source_parsers)
        pub = Publisher(reader=reader,
                        writer=SphinxDummyWriter(),
                        destination_class=NullOutput)
        pub.set_components(None, 'restructuredtext', None)
        pub.process_programmatic_settings(None, self.settings, None)
        src_path = self.doc2path(docname)
        source = SphinxFileInput(app, self, source=None, source_path=src_path,
                                 encoding=self.config.source_encoding)
        pub.source = source
        pub.settings._source = src_path
        pub.set_destination(None, None)
        pub.publish()
        doctree = pub.document

        # post-processing
        self.filter_messages(doctree)
        self.process_dependencies(docname, doctree)
        self.process_images(docname, doctree)
        self.process_downloads(docname, doctree)
        self.process_metadata(docname, doctree)
        self.process_refonly_bullet_lists(docname, doctree)
        self.create_title_from(docname, doctree)
        self.note_indexentries_from(docname, doctree)
        self.note_citations_from(docname, doctree)
        self.build_toc_from(docname, doctree)
        for domain in itervalues(self.domains):
            domain.process_doc(self, docname, doctree)

        # allow extension-specific post-processing
        if app:
            app.emit('doctree-read', doctree)

        # store time of reading, for outdated files detection
        # (Some filesystems have coarse timestamp resolution;
        # therefore time.time() can be older than filesystem's timestamp.
        # For example, FAT32 has 2sec timestamp resolution.)
        self.all_docs[docname] = max(
            time.time(), path.getmtime(self.doc2path(docname)))

        if self.versioning_condition:
            old_doctree = None
            if self.versioning_compare:
                # get old doctree
                try:
                    f = open(self.doc2path(docname,
                                           self.doctreedir, '.doctree'), 'rb')
                    try:
                        old_doctree = pickle.load(f)
                    finally:
                        f.close()
                except EnvironmentError:
                    pass

            # add uids for versioning
            if not self.versioning_compare or old_doctree is None:
                list(add_uids(doctree, self.versioning_condition))
            else:
                list(merge_doctrees(
                    old_doctree, doctree, self.versioning_condition))

        # make it picklable
        doctree.reporter = None
        doctree.transformer = None
        doctree.settings.warning_stream = None
        doctree.settings.env = None
        doctree.settings.record_dependencies = None
        for metanode in doctree.traverse(MetaBody.meta):
            # docutils' meta nodes aren't picklable because the class is nested
            metanode.__class__ = addnodes.meta

        # cleanup
        self.temp_data.clear()
        self.ref_context.clear()
        roles._roles.pop('', None)  # if a document has set a local default role

        # save the parsed doctree
        doctree_filename = self.doc2path(docname, self.doctreedir,
                                         '.doctree')
        ensuredir(path.dirname(doctree_filename))
        f = open(doctree_filename, 'wb')
        try:
            pickle.dump(doctree, f, pickle.HIGHEST_PROTOCOL)
        finally:
            f.close()

    # utilities to use while reading a document

    @property
    def docname(self):
        """Returns the docname of the document currently being parsed."""
        return self.temp_data['docname']

    @property
    def currmodule(self):
        """Backwards compatible alias.  Will be removed."""
        self.warn(self.docname, 'env.currmodule is being referenced by an '
                  'extension; this API will be removed in the future')
        return self.ref_context.get('py:module')

    @property
    def currclass(self):
        """Backwards compatible alias.  Will be removed."""
        self.warn(self.docname, 'env.currclass is being referenced by an '
                  'extension; this API will be removed in the future')
        return self.ref_context.get('py:class')

    def new_serialno(self, category=''):
        """Return a serial number, e.g. for index entry targets.

        The number is guaranteed to be unique in the current document.
        """
        key = category + 'serialno'
        cur = self.temp_data.get(key, 0)
        self.temp_data[key] = cur + 1
        return cur

    def note_dependency(self, filename):
        """Add *filename* as a dependency of the current document.

        This means that the document will be rebuilt if this file changes.

        *filename* should be absolute or relative to the source directory.
        """
        self.dependencies.setdefault(self.docname, set()).add(filename)

    def note_included(self, filename):
        """Add *filename* as a included from other document.

        This means the document is not orphaned.

        *filename* should be absolute or relative to the source directory.
        """
        self.included.add(self.path2doc(filename))

    def note_reread(self):
        """Add the current document to the list of documents that will
        automatically be re-read at the next build.
        """
        self.reread_always.add(self.docname)

    def note_versionchange(self, type, version, node, lineno):
        self.versionchanges.setdefault(version, []).append(
            (type, self.temp_data['docname'], lineno,
             self.ref_context.get('py:module'),
             self.temp_data.get('object'), node.astext()))

    # post-processing of read doctrees

    def filter_messages(self, doctree):
        """Filter system messages from a doctree."""
        filterlevel = self.config.keep_warnings and 2 or 5
        for node in doctree.traverse(nodes.system_message):
            if node['level'] < filterlevel:
                self.app.debug('%s [filtered system message]', node.astext())
                node.parent.remove(node)

    def process_dependencies(self, docname, doctree):
        """Process docutils-generated dependency info."""
        cwd = getcwd()
        frompath = path.join(path.normpath(self.srcdir), 'dummy')
        deps = doctree.settings.record_dependencies
        if not deps:
            return
        for dep in deps.list:
            # the dependency path is relative to the working dir, so get
            # one relative to the srcdir
            if isinstance(dep, bytes):
                dep = dep.decode(fs_encoding)
            relpath = relative_path(frompath,
                                    path.normpath(path.join(cwd, dep)))
            self.dependencies.setdefault(docname, set()).add(relpath)

    def process_downloads(self, docname, doctree):
        """Process downloadable file paths. """
        for node in doctree.traverse(addnodes.download_reference):
            targetname = node['reftarget']
            rel_filename, filename = self.relfn2path(targetname, docname)
            self.dependencies.setdefault(docname, set()).add(rel_filename)
            if not os.access(filename, os.R_OK):
                self.warn_node('download file not readable: %s' % filename,
                               node)
                continue
            uniquename = self.dlfiles.add_file(docname, filename)
            node['filename'] = uniquename

    def process_images(self, docname, doctree):
        """Process and rewrite image URIs."""
        def collect_candidates(imgpath, candidates):
            globbed = {}
            for filename in glob(imgpath):
                new_imgpath = relative_path(path.join(self.srcdir, 'dummy'),
                                            filename)
                try:
                    mimetype = guess_mimetype(filename)
                    if mimetype not in candidates:
                        globbed.setdefault(mimetype, []).append(new_imgpath)
                except (OSError, IOError) as err:
                    self.warn_node('image file %s not readable: %s' %
                                   (filename, err), node)
            for key, files in iteritems(globbed):
                candidates[key] = sorted(files, key=len)[0]  # select by similarity

        for node in doctree.traverse(nodes.image):
            # Map the mimetype to the corresponding image.  The writer may
            # choose the best image from these candidates.  The special key * is
            # set if there is only single candidate to be used by a writer.
            # The special key ? is set for nonlocal URIs.
            node['candidates'] = candidates = {}
            imguri = node['uri']
            if imguri.startswith('data:'):
                self.warn_node('image data URI found. some builders might not support', node,
                               type='image', subtype='data_uri')
                candidates['?'] = imguri
                continue
            elif imguri.find('://') != -1:
                self.warn_node('nonlocal image URI found: %s' % imguri, node,
                               type='image', subtype='nonlocal_uri')
                candidates['?'] = imguri
                continue
            rel_imgpath, full_imgpath = self.relfn2path(imguri, docname)
            if self.config.language:
                # substitute figures (ex. foo.png -> foo.en.png)
                i18n_full_imgpath = search_image_for_language(full_imgpath, self)
                if i18n_full_imgpath != full_imgpath:
                    full_imgpath = i18n_full_imgpath
                    rel_imgpath = relative_path(path.join(self.srcdir, 'dummy'),
                                                i18n_full_imgpath)
            # set imgpath as default URI
            node['uri'] = rel_imgpath
            if rel_imgpath.endswith(os.extsep + '*'):
                if self.config.language:
                    # Search language-specific figures at first
                    i18n_imguri = get_image_filename_for_language(imguri, self)
                    _, full_i18n_imgpath = self.relfn2path(i18n_imguri, docname)
                    collect_candidates(full_i18n_imgpath, candidates)

                collect_candidates(full_imgpath, candidates)
            else:
                candidates['*'] = rel_imgpath

            # map image paths to unique image names (so that they can be put
            # into a single directory)
            for imgpath in itervalues(candidates):
                self.dependencies.setdefault(docname, set()).add(imgpath)
                if not os.access(path.join(self.srcdir, imgpath), os.R_OK):
                    self.warn_node('image file not readable: %s' % imgpath,
                                   node)
                    continue
                self.images.add_file(docname, imgpath)

    def process_metadata(self, docname, doctree):
        """Process the docinfo part of the doctree as metadata.

        Keep processing minimal -- just return what docutils says.
        """
        self.metadata[docname] = md = {}
        try:
            docinfo = doctree[0]
        except IndexError:
            # probably an empty document
            return
        if docinfo.__class__ is not nodes.docinfo:
            # nothing to see here
            return
        for node in docinfo:
            # nodes are multiply inherited...
            if isinstance(node, nodes.authors):
                md['authors'] = [author.astext() for author in node]
            elif isinstance(node, nodes.TextElement):  # e.g. author
                md[node.__class__.__name__] = node.astext()
            else:
                name, body = node
                md[name.astext()] = body.astext()
        for name, value in md.items():
            if name in ('tocdepth',):
                try:
                    value = int(value)
                except ValueError:
                    value = 0
                md[name] = value

        del doctree[0]

    def process_refonly_bullet_lists(self, docname, doctree):
        """Change refonly bullet lists to use compact_paragraphs.

        Specifically implemented for 'Indices and Tables' section, which looks
        odd when html_compact_lists is false.
        """
        if self.config.html_compact_lists:
            return

        class RefOnlyListChecker(nodes.GenericNodeVisitor):
            """Raise `nodes.NodeFound` if non-simple list item is encountered.

            Here 'simple' means a list item containing only a paragraph with a
            single reference in it.
            """

            def default_visit(self, node):
                raise nodes.NodeFound

            def visit_bullet_list(self, node):
                pass

            def visit_list_item(self, node):
                children = []
                for child in node.children:
                    if not isinstance(child, nodes.Invisible):
                        children.append(child)
                if len(children) != 1:
                    raise nodes.NodeFound
                if not isinstance(children[0], nodes.paragraph):
                    raise nodes.NodeFound
                para = children[0]
                if len(para) != 1:
                    raise nodes.NodeFound
                if not isinstance(para[0], addnodes.pending_xref):
                    raise nodes.NodeFound
                raise nodes.SkipChildren

            def invisible_visit(self, node):
                """Invisible nodes should be ignored."""
                pass

        def check_refonly_list(node):
            """Check for list with only references in it."""
            visitor = RefOnlyListChecker(doctree)
            try:
                node.walk(visitor)
            except nodes.NodeFound:
                return False
            else:
                return True

        for node in doctree.traverse(nodes.bullet_list):
            if check_refonly_list(node):
                for item in node.traverse(nodes.list_item):
                    para = item[0]
                    ref = para[0]
                    compact_para = addnodes.compact_paragraph()
                    compact_para += ref
                    item.replace(para, compact_para)

    def create_title_from(self, docname, document):
        """Add a title node to the document (just copy the first section title),
        and store that title in the environment.
        """
        titlenode = nodes.title()
        longtitlenode = titlenode
        # explicit title set with title directive; use this only for
        # the <title> tag in HTML output
        if 'title' in document:
            longtitlenode = nodes.title()
            longtitlenode += nodes.Text(document['title'])
        # look for first section title and use that as the title
        for node in document.traverse(nodes.section):
            visitor = SphinxContentsFilter(document)
            node[0].walkabout(visitor)
            titlenode += visitor.get_entry_text()
            break
        else:
            # document has no title
            titlenode += nodes.Text('<no title>')
        self.titles[docname] = titlenode
        self.longtitles[docname] = longtitlenode

    def note_indexentries_from(self, docname, document):
        entries = self.indexentries[docname] = []
        for node in document.traverse(addnodes.index):
            try:
                for entry in node['entries']:
                    split_index_msg(entry[0], entry[1])
            except ValueError as exc:
                self.warn_node(exc, node)
                node.parent.remove(node)
            else:
                for entry in node['entries']:
                    if len(entry) == 5:
                        # Since 1.4: new index structure including index_key (5th column)
                        entries.append(entry)
                    else:
                        entries.append(entry + (None,))

    def note_citations_from(self, docname, document):
        for node in document.traverse(nodes.citation):
            label = node[0].astext()
            if label in self.citations:
                self.warn_node('duplicate citation %s, ' % label +
                               'other instance in %s' % self.doc2path(
                                   self.citations[label][0]), node)
            self.citations[label] = (docname, node['ids'][0])

    def note_toctree(self, docname, toctreenode):
        """Note a TOC tree directive in a document and gather information about
        file relations from it.
        """
        if toctreenode['glob']:
            self.glob_toctrees.add(docname)
        if toctreenode.get('numbered'):
            self.numbered_toctrees.add(docname)
        includefiles = toctreenode['includefiles']
        for includefile in includefiles:
            # note that if the included file is rebuilt, this one must be
            # too (since the TOC of the included file could have changed)
            self.files_to_rebuild.setdefault(includefile, set()).add(docname)
        self.toctree_includes.setdefault(docname, []).extend(includefiles)

    def build_toc_from(self, docname, document):
        """Build a TOC from the doctree and store it in the inventory."""
        numentries = [0]  # nonlocal again...

        def traverse_in_section(node, cls):
            """Like traverse(), but stay within the same section."""
            result = []
            if isinstance(node, cls):
                result.append(node)
            for child in node.children:
                if isinstance(child, nodes.section):
                    continue
                result.extend(traverse_in_section(child, cls))
            return result

        def build_toc(node, depth=1):
            entries = []
            for sectionnode in node:
                # find all toctree nodes in this section and add them
                # to the toc (just copying the toctree node which is then
                # resolved in self.get_and_resolve_doctree)
                if isinstance(sectionnode, addnodes.only):
                    onlynode = addnodes.only(expr=sectionnode['expr'])
                    blist = build_toc(sectionnode, depth)
                    if blist:
                        onlynode += blist.children
                        entries.append(onlynode)
                    continue
                if not isinstance(sectionnode, nodes.section):
                    for toctreenode in traverse_in_section(sectionnode,
                                                           addnodes.toctree):
                        item = toctreenode.copy()
                        entries.append(item)
                        # important: do the inventory stuff
                        self.note_toctree(docname, toctreenode)
                    continue
                title = sectionnode[0]
                # copy the contents of the section title, but without references
                # and unnecessary stuff
                visitor = SphinxContentsFilter(document)
                title.walkabout(visitor)
                nodetext = visitor.get_entry_text()
                if not numentries[0]:
                    # for the very first toc entry, don't add an anchor
                    # as it is the file's title anyway
                    anchorname = ''
                else:
                    anchorname = '#' + sectionnode['ids'][0]
                numentries[0] += 1
                # make these nodes:
                # list_item -> compact_paragraph -> reference
                reference = nodes.reference(
                    '', '', internal=True, refuri=docname,
                    anchorname=anchorname, *nodetext)
                para = addnodes.compact_paragraph('', '', reference)
                item = nodes.list_item('', para)
                sub_item = build_toc(sectionnode, depth + 1)
                item += sub_item
                entries.append(item)
            if entries:
                return nodes.bullet_list('', *entries)
            return []
        toc = build_toc(document)
        if toc:
            self.tocs[docname] = toc
        else:
            self.tocs[docname] = nodes.bullet_list('')
        self.toc_num_entries[docname] = numentries[0]

    def get_toc_for(self, docname, builder):
        """Return a TOC nodetree -- for use on the same page only!"""
        tocdepth = self.metadata[docname].get('tocdepth', 0)
        try:
            toc = self.tocs[docname].deepcopy()
            self._toctree_prune(toc, 2, tocdepth)
        except KeyError:
            # the document does not exist anymore: return a dummy node that
            # renders to nothing
            return nodes.paragraph()
        self.process_only_nodes(toc, builder, docname)
        for node in toc.traverse(nodes.reference):
            node['refuri'] = node['anchorname'] or '#'
        return toc

    def get_toctree_for(self, docname, builder, collapse, **kwds):
        """Return the global TOC nodetree."""
        doctree = self.get_doctree(self.config.master_doc)
        toctrees = []
        if 'includehidden' not in kwds:
            kwds['includehidden'] = True
        if 'maxdepth' not in kwds:
            kwds['maxdepth'] = 0
        kwds['collapse'] = collapse
        for toctreenode in doctree.traverse(addnodes.toctree):
            toctree = self.resolve_toctree(docname, builder, toctreenode,
                                           prune=True, **kwds)
            if toctree:
                toctrees.append(toctree)
        if not toctrees:
            return None
        result = toctrees[0]
        for toctree in toctrees[1:]:
            result.extend(toctree.children)
        return result

    def get_domain(self, domainname):
        """Return the domain instance with the specified name.

        Raises an ExtensionError if the domain is not registered.
        """
        try:
            return self.domains[domainname]
        except KeyError:
            raise ExtensionError('Domain %r is not registered' % domainname)

    # --------- RESOLVING REFERENCES AND TOCTREES ------------------------------

    def get_doctree(self, docname):
        """Read the doctree for a file from the pickle and return it."""
        doctree_filename = self.doc2path(docname, self.doctreedir, '.doctree')
        f = open(doctree_filename, 'rb')
        try:
            doctree = pickle.load(f)
        finally:
            f.close()
        doctree.settings.env = self
        doctree.reporter = Reporter(self.doc2path(docname), 2, 5,
                                    stream=WarningStream(self._warnfunc))
        return doctree

    def get_and_resolve_doctree(self, docname, builder, doctree=None,
                                prune_toctrees=True, includehidden=False):
        """Read the doctree from the pickle, resolve cross-references and
        toctrees and return it.
        """
        if doctree is None:
            doctree = self.get_doctree(docname)

        # resolve all pending cross-references
        self.resolve_references(doctree, docname, builder)

        # now, resolve all toctree nodes
        for toctreenode in doctree.traverse(addnodes.toctree):
            result = self.resolve_toctree(docname, builder, toctreenode,
                                          prune=prune_toctrees,
                                          includehidden=includehidden)
            if result is None:
                toctreenode.replace_self([])
            else:
                toctreenode.replace_self(result)

        return doctree

    def _toctree_prune(self, node, depth, maxdepth, collapse=False):
        """Utility: Cut a TOC at a specified depth."""
        for subnode in node.children[:]:
            if isinstance(subnode, (addnodes.compact_paragraph,
                                    nodes.list_item)):
                # for <p> and <li>, just recurse
                self._toctree_prune(subnode, depth, maxdepth, collapse)
            elif isinstance(subnode, nodes.bullet_list):
                # for <ul>, determine if the depth is too large or if the
                # entry is to be collapsed
                if maxdepth > 0 and depth > maxdepth:
                    subnode.parent.replace(subnode, [])
                else:
                    # cull sub-entries whose parents aren't 'current'
                    if (collapse and depth > 1 and
                            'iscurrent' not in subnode.parent):
                        subnode.parent.remove(subnode)
                    else:
                        # recurse on visible children
                        self._toctree_prune(subnode, depth+1, maxdepth,  collapse)

    def get_toctree_ancestors(self, docname):
        parent = {}
        for p, children in iteritems(self.toctree_includes):
            for child in children:
                parent[child] = p
        ancestors = []
        d = docname
        while d in parent and d not in ancestors:
            ancestors.append(d)
            d = parent[d]
        return ancestors

    def resolve_toctree(self, docname, builder, toctree, prune=True, maxdepth=0,
                        titles_only=False, collapse=False, includehidden=False):
        """Resolve a *toctree* node into individual bullet lists with titles
        as items, returning None (if no containing titles are found) or
        a new node.

        If *prune* is True, the tree is pruned to *maxdepth*, or if that is 0,
        to the value of the *maxdepth* option on the *toctree* node.
        If *titles_only* is True, only toplevel document titles will be in the
        resulting tree.
        If *collapse* is True, all branches not containing docname will
        be collapsed.
        """
        if toctree.get('hidden', False) and not includehidden:
            return None

        # For reading the following two helper function, it is useful to keep
        # in mind the node structure of a toctree (using HTML-like node names
        # for brevity):
        #
        # <ul>
        #   <li>
        #     <p><a></p>
        #     <p><a></p>
        #     ...
        #     <ul>
        #       ...
        #     </ul>
        #   </li>
        # </ul>
        #
        # The transformation is made in two passes in order to avoid
        # interactions between marking and pruning the tree (see bug #1046).

        toctree_ancestors = self.get_toctree_ancestors(docname)

        def _toctree_add_classes(node, depth):
            """Add 'toctree-l%d' and 'current' classes to the toctree."""
            for subnode in node.children:
                if isinstance(subnode, (addnodes.compact_paragraph,
                                        nodes.list_item)):
                    # for <p> and <li>, indicate the depth level and recurse
                    subnode['classes'].append('toctree-l%d' % (depth-1))
                    _toctree_add_classes(subnode, depth)
                elif isinstance(subnode, nodes.bullet_list):
                    # for <ul>, just recurse
                    _toctree_add_classes(subnode, depth+1)
                elif isinstance(subnode, nodes.reference):
                    # for <a>, identify which entries point to the current
                    # document and therefore may not be collapsed
                    if subnode['refuri'] == docname:
                        if not subnode['anchorname']:
                            # give the whole branch a 'current' class
                            # (useful for styling it differently)
                            branchnode = subnode
                            while branchnode:
                                branchnode['classes'].append('current')
                                branchnode = branchnode.parent
                        # mark the list_item as "on current page"
                        if subnode.parent.parent.get('iscurrent'):
                            # but only if it's not already done
                            return
                        while subnode:
                            subnode['iscurrent'] = True
                            subnode = subnode.parent

        def _entries_from_toctree(toctreenode, parents,
                                  separate=False, subtree=False):
            """Return TOC entries for a toctree node."""
            refs = [(e[0], e[1]) for e in toctreenode['entries']]
            entries = []
            for (title, ref) in refs:
                try:
                    refdoc = None
                    if url_re.match(ref):
                        if title is None:
                            title = ref
                        reference = nodes.reference('', '', internal=False,
                                                    refuri=ref, anchorname='',
                                                    *[nodes.Text(title)])
                        para = addnodes.compact_paragraph('', '', reference)
                        item = nodes.list_item('', para)
                        toc = nodes.bullet_list('', item)
                    elif ref == 'self':
                        # 'self' refers to the document from which this
                        # toctree originates
                        ref = toctreenode['parent']
                        if not title:
                            title = clean_astext(self.titles[ref])
                        reference = nodes.reference('', '', internal=True,
                                                    refuri=ref,
                                                    anchorname='',
                                                    *[nodes.Text(title)])
                        para = addnodes.compact_paragraph('', '', reference)
                        item = nodes.list_item('', para)
                        # don't show subitems
                        toc = nodes.bullet_list('', item)
                    else:
                        if ref in parents:
                            self.warn(ref, 'circular toctree references '
                                      'detected, ignoring: %s <- %s' %
                                      (ref, ' <- '.join(parents)))
                            continue
                        refdoc = ref
                        toc = self.tocs[ref].deepcopy()
                        maxdepth = self.metadata[ref].get('tocdepth', 0)
                        if ref not in toctree_ancestors or (prune and maxdepth > 0):
                            self._toctree_prune(toc, 2, maxdepth, collapse)
                        self.process_only_nodes(toc, builder, ref)
                        if title and toc.children and len(toc.children) == 1:
                            child = toc.children[0]
                            for refnode in child.traverse(nodes.reference):
                                if refnode['refuri'] == ref and \
                                   not refnode['anchorname']:
                                    refnode.children = [nodes.Text(title)]
                    if not toc.children:
                        # empty toc means: no titles will show up in the toctree
                        self.warn_node(
                            'toctree contains reference to document %r that '
                            'doesn\'t have a title: no link will be generated'
                            % ref, toctreenode)
                except KeyError:
                    # this is raised if the included file does not exist
                    self.warn_node(
                        'toctree contains reference to nonexisting document %r'
                        % ref, toctreenode)
                else:
                    # if titles_only is given, only keep the main title and
                    # sub-toctrees
                    if titles_only:
                        # delete everything but the toplevel title(s)
                        # and toctrees
                        for toplevel in toc:
                            # nodes with length 1 don't have any children anyway
                            if len(toplevel) > 1:
                                subtrees = toplevel.traverse(addnodes.toctree)
                                if subtrees:
                                    toplevel[1][:] = subtrees
                                else:
                                    toplevel.pop(1)
                    # resolve all sub-toctrees
                    for subtocnode in toc.traverse(addnodes.toctree):
                        if not (subtocnode.get('hidden', False) and
                                not includehidden):
                            i = subtocnode.parent.index(subtocnode) + 1
                            for item in _entries_from_toctree(
                                    subtocnode, [refdoc] + parents,
                                    subtree=True):
                                subtocnode.parent.insert(i, item)
                                i += 1
                            subtocnode.parent.remove(subtocnode)
                    if separate:
                        entries.append(toc)
                    else:
                        entries.extend(toc.children)
            if not subtree and not separate:
                ret = nodes.bullet_list()
                ret += entries
                return [ret]
            return entries

        maxdepth = maxdepth or toctree.get('maxdepth', -1)
        if not titles_only and toctree.get('titlesonly', False):
            titles_only = True
        if not includehidden and toctree.get('includehidden', False):
            includehidden = True

        # NOTE: previously, this was separate=True, but that leads to artificial
        # separation when two or more toctree entries form a logical unit, so
        # separating mode is no longer used -- it's kept here for history's sake
        tocentries = _entries_from_toctree(toctree, [], separate=False)
        if not tocentries:
            return None

        newnode = addnodes.compact_paragraph('', '')
        caption = toctree.attributes.get('caption')
        if caption:
            newnode += nodes.caption(caption, '', *[nodes.Text(caption)])
        newnode.extend(tocentries)
        newnode['toctree'] = True

        # prune the tree to maxdepth, also set toc depth and current classes
        _toctree_add_classes(newnode, 1)
        self._toctree_prune(newnode, 1, prune and maxdepth or 0, collapse)

        if len(newnode[-1]) == 0:  # No titles found
            return None

        # set the target paths in the toctrees (they are not known at TOC
        # generation time)
        for refnode in newnode.traverse(nodes.reference):
            if not url_re.match(refnode['refuri']):
                refnode['refuri'] = builder.get_relative_uri(
                    docname, refnode['refuri']) + refnode['anchorname']
        return newnode

    def resolve_references(self, doctree, fromdocname, builder):
        for node in doctree.traverse(addnodes.pending_xref):
            contnode = node[0].deepcopy()
            newnode = None

            typ = node['reftype']
            target = node['reftarget']
            refdoc = node.get('refdoc', fromdocname)
            domain = None

            try:
                if 'refdomain' in node and node['refdomain']:
                    # let the domain try to resolve the reference
                    try:
                        domain = self.domains[node['refdomain']]
                    except KeyError:
                        raise NoUri
                    newnode = domain.resolve_xref(self, refdoc, builder,
                                                  typ, target, node, contnode)
                # really hardwired reference types
                elif typ == 'any':
                    newnode = self._resolve_any_reference(builder, node, contnode)
                elif typ == 'doc':
                    newnode = self._resolve_doc_reference(builder, node, contnode)
                elif typ == 'citation':
                    newnode = self._resolve_citation(builder, refdoc, node, contnode)
                # no new node found? try the missing-reference event
                if newnode is None:
                    newnode = builder.app.emit_firstresult(
                        'missing-reference', self, node, contnode)
                    # still not found? warn if node wishes to be warned about or
                    # we are in nit-picky mode
                    if newnode is None:
                        self._warn_missing_reference(refdoc, typ, target, node, domain)
            except NoUri:
                newnode = contnode
            node.replace_self(newnode or contnode)

        # remove only-nodes that do not belong to our builder
        self.process_only_nodes(doctree, builder, fromdocname)

        # allow custom references to be resolved
        builder.app.emit('doctree-resolved', doctree, fromdocname)

    def _warn_missing_reference(self, refdoc, typ, target, node, domain):
        warn = node.get('refwarn')
        if self.config.nitpicky:
            warn = True
            if self._nitpick_ignore:
                dtype = domain and '%s:%s' % (domain.name, typ) or typ
                if (dtype, target) in self._nitpick_ignore:
                    warn = False
                # for "std" types also try without domain name
                if (not domain or domain.name == 'std') and \
                   (typ, target) in self._nitpick_ignore:
                    warn = False
        if not warn:
            return
        if domain and typ in domain.dangling_warnings:
            msg = domain.dangling_warnings[typ]
        elif typ == 'doc':
            msg = 'unknown document: %(target)s'
        elif typ == 'citation':
            msg = 'citation not found: %(target)s'
        elif node.get('refdomain', 'std') not in ('', 'std'):
            msg = '%s:%s reference target not found: %%(target)s' % \
                  (node['refdomain'], typ)
        else:
            msg = '%r reference target not found: %%(target)s' % typ
        self.warn_node(msg % {'target': target}, node, type='ref', subtype=typ)

    def _resolve_doc_reference(self, builder, node, contnode):
        # directly reference to document by source name;
        # can be absolute or relative
        docname = docname_join(node['refdoc'], node['reftarget'])
        if docname in self.all_docs:
            if node['refexplicit']:
                # reference with explicit title
                caption = node.astext()
            else:
                caption = clean_astext(self.titles[docname])
            innernode = nodes.inline(caption, caption)
            innernode['classes'].append('doc')
            newnode = nodes.reference('', '', internal=True)
            newnode['refuri'] = builder.get_relative_uri(node['refdoc'], docname)
            newnode.append(innernode)
            return newnode

    def _resolve_citation(self, builder, fromdocname, node, contnode):
        docname, labelid = self.citations.get(node['reftarget'], ('', ''))
        if docname:
            try:
                newnode = make_refnode(builder, fromdocname,
                                       docname, labelid, contnode)
                return newnode
            except NoUri:
                # remove the ids we added in the CitationReferences
                # transform since they can't be transfered to
                # the contnode (if it's a Text node)
                if not isinstance(contnode, nodes.Element):
                    del node['ids'][:]
                raise
        elif 'ids' in node:
            # remove ids attribute that annotated at
            # transforms.CitationReference.apply.
            del node['ids'][:]

    def _resolve_any_reference(self, builder, node, contnode):
        """Resolve reference generated by the "any" role."""
        refdoc = node['refdoc']
        target = node['reftarget']
        results = []
        # first, try resolving as :doc:
        doc_ref = self._resolve_doc_reference(builder, node, contnode)
        if doc_ref:
            results.append(('doc', doc_ref))
        # next, do the standard domain (makes this a priority)
        results.extend(self.domains['std'].resolve_any_xref(
            self, refdoc, builder, target, node, contnode))
        for domain in self.domains.values():
            if domain.name == 'std':
                continue  # we did this one already
            try:
                results.extend(domain.resolve_any_xref(self, refdoc, builder,
                                                       target, node, contnode))
            except NotImplementedError:
                # the domain doesn't yet support the new interface
                # we have to manually collect possible references (SLOW)
                for role in domain.roles:
                    res = domain.resolve_xref(self, refdoc, builder, role, target,
                                              node, contnode)
                    if res and isinstance(res[0], nodes.Element):
                        results.append(('%s:%s' % (domain.name, role), res))
        # now, see how many matches we got...
        if not results:
            return None
        if len(results) > 1:
            nice_results = ' or '.join(':%s:' % r[0] for r in results)
            self.warn_node('more than one target found for \'any\' cross-'
                           'reference %r: could be %s' % (target, nice_results),
                           node)
        res_role, newnode = results[0]
        # Override "any" class with the actual role type to get the styling
        # approximately correct.
        res_domain = res_role.split(':')[0]
        if newnode and newnode[0].get('classes'):
            newnode[0]['classes'].append(res_domain)
            newnode[0]['classes'].append(res_role.replace(':', '-'))
        return newnode

    def process_only_nodes(self, doctree, builder, fromdocname=None):
        # A comment on the comment() nodes being inserted: replacing by [] would
        # result in a "Losing ids" exception if there is a target node before
        # the only node, so we make sure docutils can transfer the id to
        # something, even if it's just a comment and will lose the id anyway...
        for node in doctree.traverse(addnodes.only):
            try:
                ret = builder.tags.eval_condition(node['expr'])
            except Exception as err:
                self.warn_node('exception while evaluating only '
                               'directive expression: %s' % err, node)
                node.replace_self(node.children or nodes.comment())
            else:
                if ret:
                    node.replace_self(node.children or nodes.comment())
                else:
                    node.replace_self(nodes.comment())

    def assign_section_numbers(self):
        """Assign a section number to each heading under a numbered toctree."""
        # a list of all docnames whose section numbers changed
        rewrite_needed = []

        assigned = set()
        old_secnumbers = self.toc_secnumbers
        self.toc_secnumbers = {}

        def _walk_toc(node, secnums, depth, titlenode=None):
            # titlenode is the title of the document, it will get assigned a
            # secnumber too, so that it shows up in next/prev/parent rellinks
            for subnode in node.children:
                if isinstance(subnode, nodes.bullet_list):
                    numstack.append(0)
                    _walk_toc(subnode, secnums, depth-1, titlenode)
                    numstack.pop()
                    titlenode = None
                elif isinstance(subnode, nodes.list_item):
                    _walk_toc(subnode, secnums, depth, titlenode)
                    titlenode = None
                elif isinstance(subnode, addnodes.only):
                    # at this stage we don't know yet which sections are going
                    # to be included; just include all of them, even if it leads
                    # to gaps in the numbering
                    _walk_toc(subnode, secnums, depth, titlenode)
                    titlenode = None
                elif isinstance(subnode, addnodes.compact_paragraph):
                    numstack[-1] += 1
                    if depth > 0:
                        number = tuple(numstack)
                    else:
                        number = None
                    secnums[subnode[0]['anchorname']] = \
                        subnode[0]['secnumber'] = number
                    if titlenode:
                        titlenode['secnumber'] = number
                        titlenode = None
                elif isinstance(subnode, addnodes.toctree):
                    _walk_toctree(subnode, depth)

        def _walk_toctree(toctreenode, depth):
            if depth == 0:
                return
            for (title, ref) in toctreenode['entries']:
                if url_re.match(ref) or ref == 'self' or ref in assigned:
                    # don't mess with those
                    continue
                if ref in self.tocs:
                    secnums = self.toc_secnumbers[ref] = {}
                    assigned.add(ref)
                    _walk_toc(self.tocs[ref], secnums, depth,
                              self.titles.get(ref))
                    if secnums != old_secnumbers.get(ref):
                        rewrite_needed.append(ref)

        for docname in self.numbered_toctrees:
            assigned.add(docname)
            doctree = self.get_doctree(docname)
            for toctreenode in doctree.traverse(addnodes.toctree):
                depth = toctreenode.get('numbered', 0)
                if depth:
                    # every numbered toctree gets new numbering
                    numstack = [0]
                    _walk_toctree(toctreenode, depth)

        return rewrite_needed

    def assign_figure_numbers(self):
        """Assign a figure number to each figure under a numbered toctree."""

        rewrite_needed = []

        assigned = set()
        old_fignumbers = self.toc_fignumbers
        self.toc_fignumbers = {}
        fignum_counter = {}

        def get_section_number(docname, section):
            anchorname = '#' + section['ids'][0]
            secnumbers = self.toc_secnumbers.get(docname, {})
            if anchorname in secnumbers:
                secnum = secnumbers.get(anchorname)
            else:
                secnum = secnumbers.get('')

            return secnum or tuple()

        def get_next_fignumber(figtype, secnum):
            counter = fignum_counter.setdefault(figtype, {})

            secnum = secnum[:self.config.numfig_secnum_depth]
            counter[secnum] = counter.get(secnum, 0) + 1
            return secnum + (counter[secnum],)

        def register_fignumber(docname, secnum, figtype, fignode):
            self.toc_fignumbers.setdefault(docname, {})
            fignumbers = self.toc_fignumbers[docname].setdefault(figtype, {})
            figure_id = fignode['ids'][0]

            fignumbers[figure_id] = get_next_fignumber(figtype, secnum)

        def _walk_doctree(docname, doctree, secnum):
            for subnode in doctree.children:
                if isinstance(subnode, nodes.section):
                    next_secnum = get_section_number(docname, subnode)
                    if next_secnum:
                        _walk_doctree(docname, subnode, next_secnum)
                    else:
                        _walk_doctree(docname, subnode, secnum)
                    continue
                elif isinstance(subnode, addnodes.toctree):
                    for title, subdocname in subnode['entries']:
                        if url_re.match(subdocname) or subdocname == 'self':
                            # don't mess with those
                            continue

                        _walk_doc(subdocname, secnum)

                    continue

                figtype = self.domains['std'].get_figtype(subnode)
                if figtype and subnode['ids']:
                    register_fignumber(docname, secnum, figtype, subnode)

                _walk_doctree(docname, subnode, secnum)

        def _walk_doc(docname, secnum):
            if docname not in assigned:
                assigned.add(docname)
                doctree = self.get_doctree(docname)
                _walk_doctree(docname, doctree, secnum)

        if self.config.numfig:
            _walk_doc(self.config.master_doc, tuple())
            for docname, fignums in iteritems(self.toc_fignumbers):
                if fignums != old_fignumbers.get(docname):
                    rewrite_needed.append(docname)

        return rewrite_needed

    def create_index(self, builder, group_entries=True,
                     _fixre=re.compile(r'(.*) ([(][^()]*[)])')):
        """Create the real index from the collected index entries."""
        new = {}

        def add_entry(word, subword, link=True, dic=new, key=None):
            # Force the word to be unicode if it's a ASCII bytestring.
            # This will solve problems with unicode normalization later.
            # For instance the RFC role will add bytestrings at the moment
            word = text_type(word)
            entry = dic.get(word)
            if not entry:
                dic[word] = entry = [[], {}, key]
            if subword:
                add_entry(subword, '', link=link, dic=entry[1], key=key)
            elif link:
                try:
                    uri = builder.get_relative_uri('genindex', fn) + '#' + tid
                except NoUri:
                    pass
                else:
                    # maintain links in sorted/deterministic order
                    bisect.insort(entry[0], (main, uri))

        for fn, entries in iteritems(self.indexentries):
            # new entry types must be listed in directives/other.py!
            for type, value, tid, main, index_key in entries:
                try:
                    if type == 'single':
                        try:
                            entry, subentry = split_into(2, 'single', value)
                        except ValueError:
                            entry, = split_into(1, 'single', value)
                            subentry = ''
                        add_entry(entry, subentry, key=index_key)
                    elif type == 'pair':
                        first, second = split_into(2, 'pair', value)
                        add_entry(first, second, key=index_key)
                        add_entry(second, first, key=index_key)
                    elif type == 'triple':
                        first, second, third = split_into(3, 'triple', value)
                        add_entry(first, second+' '+third, key=index_key)
                        add_entry(second, third+', '+first, key=index_key)
                        add_entry(third, first+' '+second, key=index_key)
                    elif type == 'see':
                        first, second = split_into(2, 'see', value)
                        add_entry(first, _('see %s') % second, link=False,
                                  key=index_key)
                    elif type == 'seealso':
                        first, second = split_into(2, 'see', value)
                        add_entry(first, _('see also %s') % second, link=False,
                                  key=index_key)
                    else:
                        self.warn(fn, 'unknown index entry type %r' % type)
                except ValueError as err:
                    self.warn(fn, str(err))

        # sort the index entries; put all symbols at the front, even those
        # following the letters in ASCII, this is where the chr(127) comes from
        def keyfunc(entry, lcletters=string.ascii_lowercase + '_'):
            lckey = unicodedata.normalize('NFD', entry[0].lower())
            if lckey[0:1] in lcletters:
                lckey = chr(127) + lckey
            # ensure a determinstic order *within* letters by also sorting on
            # the entry itself
            return (lckey, entry[0])
        newlist = sorted(new.items(), key=keyfunc)

        if group_entries:
            # fixup entries: transform
            #   func() (in module foo)
            #   func() (in module bar)
            # into
            #   func()
            #     (in module foo)
            #     (in module bar)
            oldkey = ''
            oldsubitems = None
            i = 0
            while i < len(newlist):
                key, (targets, subitems, _key) = newlist[i]
                # cannot move if it has subitems; structure gets too complex
                if not subitems:
                    m = _fixre.match(key)
                    if m:
                        if oldkey == m.group(1):
                            # prefixes match: add entry as subitem of the
                            # previous entry
                            oldsubitems.setdefault(m.group(2), [[], {}, _key])[0].\
                                extend(targets)
                            del newlist[i]
                            continue
                        oldkey = m.group(1)
                    else:
                        oldkey = key
                oldsubitems = subitems
                i += 1

        # group the entries by letter
        def keyfunc2(item, letters=string.ascii_uppercase + '_'):
            # hack: mutating the subitems dicts to a list in the keyfunc
            k, v = item
            v[1] = sorted((si, se) for (si, (se, void, void)) in iteritems(v[1]))
            if v[2] is None:
                # now calculate the key
                letter = unicodedata.normalize('NFD', k[0])[0].upper()
                if letter in letters:
                    return letter
                else:
                    # get all other symbols under one heading
                    return _('Symbols')
            else:
                return v[2]
        return [(key_, list(group))
                for (key_, group) in groupby(newlist, keyfunc2)]

    def collect_relations(self):
        traversed = set()

        def traverse_toctree(parent, docname):
            if parent == docname:
                self.warn(docname, 'self referenced toctree found. Ignored.')
                return

            # traverse toctree by pre-order
            yield parent, docname
            traversed.add(docname)

            for child in (self.toctree_includes.get(docname) or []):
                for subparent, subdocname in traverse_toctree(docname, child):
                    if subdocname not in traversed:
                        yield subparent, subdocname
                        traversed.add(subdocname)

        relations = {}
        docnames = traverse_toctree(None, self.config.master_doc)
        prevdoc = None
        parent, docname = next(docnames)
        for nextparent, nextdoc in docnames:
            relations[docname] = [parent, prevdoc, nextdoc]
            prevdoc = docname
            docname = nextdoc
            parent = nextparent

        relations[docname] = [parent, prevdoc, None]

        return relations

    def check_consistency(self):
        """Do consistency checks."""
        for docname in sorted(self.all_docs):
            if docname not in self.files_to_rebuild:
                if docname == self.config.master_doc:
                    # the master file is not included anywhere ;)
                    continue
                if docname in self.included:
                    # the document is included from other documents
                    continue
                if 'orphan' in self.metadata[docname]:
                    continue
                self.warn(docname, 'document isn\'t included in any toctree')
