# -*- coding: utf-8 -*-
"""
    sphinx.builders
    ~~~~~~~~~~~~~~~

    Builder superclass for all builders.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import os
from os import path

try:
    import multiprocessing
except ImportError:
    multiprocessing = None

from docutils import nodes

from sphinx.util import i18n, path_stabilize
from sphinx.util.osutil import SEP, relative_uri
from sphinx.util.i18n import find_catalog
from sphinx.util.console import bold, darkgreen
from sphinx.util.parallel import ParallelTasks, SerialTasks, make_chunks, \
    parallel_available

# side effect: registers roles and directives
from sphinx import roles       # noqa
from sphinx import directives  # noqa


class Builder(object):
    """
    Builds target formats from the reST sources.
    """

    # builder's name, for the -b command line options
    name = ''
    # builder's output format, or '' if no document output is produced
    format = ''
    # doctree versioning method
    versioning_method = 'none'
    versioning_compare = False
    # allow parallel write_doc() calls
    allow_parallel = False

    def __init__(self, app):
        self.env = app.env
        self.env.set_versioning_method(self.versioning_method,
                                       self.versioning_compare)
        self.srcdir = app.srcdir
        self.confdir = app.confdir
        self.outdir = app.outdir
        self.doctreedir = app.doctreedir
        if not path.isdir(self.doctreedir):
            os.makedirs(self.doctreedir)

        self.app = app
        self.warn = app.warn
        self.info = app.info
        self.config = app.config
        self.tags = app.tags
        self.tags.add(self.format)
        self.tags.add(self.name)
        self.tags.add("format_%s" % self.format)
        self.tags.add("builder_%s" % self.name)
        # compatibility aliases
        self.status_iterator = app.status_iterator
        self.old_status_iterator = app.old_status_iterator

        # images that need to be copied over (source -> dest)
        self.images = {}
        # basename of images directory
        self.imagedir = ""
        # relative path to image directory from current docname (used at writing docs)
        self.imgpath = ""

        # these get set later
        self.parallel_ok = False
        self.finish_tasks = None

        # load default translator class
        self.translator_class = app._translators.get(self.name)

        self.init()

    # helper methods
    def init(self):
        """Load necessary templates and perform initialization.  The default
        implementation does nothing.
        """
        pass

    def create_template_bridge(self):
        """Return the template bridge configured."""
        if self.config.template_bridge:
            self.templates = self.app.import_object(
                self.config.template_bridge, 'template_bridge setting')()
        else:
            from sphinx.jinja2glue import BuiltinTemplateLoader
            self.templates = BuiltinTemplateLoader()

    def get_target_uri(self, docname, typ=None):
        """Return the target URI for a document name.

        *typ* can be used to qualify the link characteristic for individual
        builders.
        """
        raise NotImplementedError

    def get_relative_uri(self, from_, to, typ=None):
        """Return a relative URI between two source filenames.

        May raise environment.NoUri if there's no way to return a sensible URI.
        """
        return relative_uri(self.get_target_uri(from_),
                            self.get_target_uri(to, typ))

    def get_outdated_docs(self):
        """Return an iterable of output files that are outdated, or a string
        describing what an update build will build.

        If the builder does not output individual files corresponding to
        source files, return a string here.  If it does, return an iterable
        of those files that need to be written.
        """
        raise NotImplementedError

    supported_image_types = []

    def post_process_images(self, doctree):
        """Pick the best candidate for all image URIs."""
        for node in doctree.traverse(nodes.image):
            if '?' in node['candidates']:
                # don't rewrite nonlocal image URIs
                continue
            if '*' not in node['candidates']:
                for imgtype in self.supported_image_types:
                    candidate = node['candidates'].get(imgtype, None)
                    if candidate:
                        break
                else:
                    self.warn(
                        'no matching candidate for image URI %r' % node['uri'],
                        '%s:%s' % (node.source, getattr(node, 'line', '')))
                    continue
                node['uri'] = candidate
            else:
                candidate = node['uri']
            if candidate not in self.env.images:
                # non-existing URI; let it alone
                continue
            self.images[candidate] = self.env.images[candidate][1]

    # compile po methods

    def compile_catalogs(self, catalogs, message):
        if not self.config.gettext_auto_build:
            return

        def cat2relpath(cat):
            return path.relpath(cat.mo_path, self.env.srcdir).replace(path.sep, SEP)

        self.info(bold('building [mo]: ') + message)
        for catalog in self.app.status_iterator(
                catalogs, 'writing output... ', darkgreen, len(catalogs),
                cat2relpath):
            catalog.write_mo(self.config.language)

    def compile_all_catalogs(self):
        catalogs = i18n.find_catalog_source_files(
            [path.join(self.srcdir, x) for x in self.config.locale_dirs],
            self.config.language,
            charset=self.config.source_encoding,
            gettext_compact=self.config.gettext_compact,
            force_all=True)
        message = 'all of %d po files' % len(catalogs)
        self.compile_catalogs(catalogs, message)

    def compile_specific_catalogs(self, specified_files):
        def to_domain(fpath):
            docname, _ = path.splitext(path_stabilize(fpath))
            dom = find_catalog(docname, self.config.gettext_compact)
            return dom

        specified_domains = set(map(to_domain, specified_files))
        catalogs = i18n.find_catalog_source_files(
            [path.join(self.srcdir, x) for x in self.config.locale_dirs],
            self.config.language,
            domains=list(specified_domains),
            charset=self.config.source_encoding,
            gettext_compact=self.config.gettext_compact)
        message = 'targets for %d po files that are specified' % len(catalogs)
        self.compile_catalogs(catalogs, message)

    def compile_update_catalogs(self):
        catalogs = i18n.find_catalog_source_files(
            [path.join(self.srcdir, x) for x in self.config.locale_dirs],
            self.config.language,
            charset=self.config.source_encoding,
            gettext_compact=self.config.gettext_compact)
        message = 'targets for %d po files that are out of date' % len(catalogs)
        self.compile_catalogs(catalogs, message)

    # build methods

    def build_all(self):
        """Build all source files."""
        self.build(None, summary='all source files', method='all')

    def build_specific(self, filenames):
        """Only rebuild as much as needed for changes in the *filenames*."""
        # bring the filenames to the canonical format, that is,
        # relative to the source directory and without source_suffix.
        dirlen = len(self.srcdir) + 1
        to_write = []
        suffixes = tuple(self.config.source_suffix)
        for filename in filenames:
            filename = path.normpath(path.abspath(filename))
            if not filename.startswith(self.srcdir):
                self.warn('file %r given on command line is not under the '
                          'source directory, ignoring' % filename)
                continue
            if not (path.isfile(filename) or
                    any(path.isfile(filename + suffix) for suffix in suffixes)):
                self.warn('file %r given on command line does not exist, '
                          'ignoring' % filename)
                continue
            filename = filename[dirlen:]
            for suffix in suffixes:
                if filename.endswith(suffix):
                    filename = filename[:-len(suffix)]
                    break
            filename = filename.replace(path.sep, SEP)
            to_write.append(filename)
        self.build(to_write, method='specific',
                   summary='%d source files given on command '
                   'line' % len(to_write))

    def build_update(self):
        """Only rebuild what was changed or added since last build."""
        to_build = self.get_outdated_docs()
        if isinstance(to_build, str):
            self.build(['__all__'], to_build)
        else:
            to_build = list(to_build)
            self.build(to_build,
                       summary='targets for %d source files that are '
                       'out of date' % len(to_build))

    def build(self, docnames, summary=None, method='update'):
        """Main build method.

        First updates the environment, and then calls :meth:`write`.
        """
        if summary:
            self.info(bold('building [%s]' % self.name) + ': ' + summary)

        # while reading, collect all warnings from docutils
        warnings = []
        self.env.set_warnfunc(lambda *args, **kwargs: warnings.append((args, kwargs)))
        updated_docnames = set(self.env.update(self.config, self.srcdir,
                                               self.doctreedir, self.app))
        self.env.set_warnfunc(self.warn)
        for warning, kwargs in warnings:
            self.warn(*warning, **kwargs)

        doccount = len(updated_docnames)
        self.info(bold('looking for now-outdated files... '), nonl=1)
        for docname in self.env.check_dependents(updated_docnames):
            updated_docnames.add(docname)
        outdated = len(updated_docnames) - doccount
        if outdated:
            self.info('%d found' % outdated)
        else:
            self.info('none found')

        if updated_docnames:
            # save the environment
            from sphinx.application import ENV_PICKLE_FILENAME
            self.info(bold('pickling environment... '), nonl=True)
            self.env.topickle(path.join(self.doctreedir, ENV_PICKLE_FILENAME))
            self.info('done')

            # global actions
            self.info(bold('checking consistency... '), nonl=True)
            self.env.check_consistency()
            self.info('done')
        else:
            if method == 'update' and not docnames:
                self.info(bold('no targets are out of date.'))
                return

        # filter "docnames" (list of outdated files) by the updated
        # found_docs of the environment; this will remove docs that
        # have since been removed
        if docnames and docnames != ['__all__']:
            docnames = set(docnames) & self.env.found_docs

        # determine if we can write in parallel
        self.parallel_ok = False
        if parallel_available and self.app.parallel > 1 and self.allow_parallel:
            self.parallel_ok = True
            for extname, md in self.app._extension_metadata.items():
                par_ok = md.get('parallel_write_safe', True)
                if not par_ok:
                    self.app.warn('the %s extension is not safe for parallel '
                                  'writing, doing serial write' % extname)
                    self.parallel_ok = False
                    break

        #  create a task executor to use for misc. "finish-up" tasks
        # if self.parallel_ok:
        #     self.finish_tasks = ParallelTasks(self.app.parallel)
        # else:
        # for now, just execute them serially
        self.finish_tasks = SerialTasks()

        # write all "normal" documents (or everything for some builders)
        self.write(docnames, list(updated_docnames), method)

        # finish (write static files etc.)
        self.finish()

        # wait for all tasks
        self.finish_tasks.join()

    def write(self, build_docnames, updated_docnames, method='update'):
        if build_docnames is None or build_docnames == ['__all__']:
            # build_all
            build_docnames = self.env.found_docs
        if method == 'update':
            # build updated ones as well
            docnames = set(build_docnames) | set(updated_docnames)
        else:
            docnames = set(build_docnames)
        self.app.debug('docnames to write: %s', ', '.join(sorted(docnames)))

        # add all toctree-containing files that may have changed
        for docname in list(docnames):
            for tocdocname in self.env.files_to_rebuild.get(docname, []):
                if tocdocname in self.env.found_docs:
                    docnames.add(tocdocname)
        docnames.add(self.config.master_doc)

        self.info(bold('preparing documents... '), nonl=True)
        self.prepare_writing(docnames)
        self.info('done')

        warnings = []
        self.env.set_warnfunc(lambda *args, **kwargs: warnings.append((args, kwargs)))
        if self.parallel_ok:
            # number of subprocesses is parallel-1 because the main process
            # is busy loading doctrees and doing write_doc_serialized()
            self._write_parallel(sorted(docnames), warnings,
                                 nproc=self.app.parallel - 1)
        else:
            self._write_serial(sorted(docnames), warnings)
        self.env.set_warnfunc(self.warn)

    def _write_serial(self, docnames, warnings):
        for docname in self.app.status_iterator(
                docnames, 'writing output... ', darkgreen, len(docnames)):
            doctree = self.env.get_and_resolve_doctree(docname, self)
            self.write_doc_serialized(docname, doctree)
            self.write_doc(docname, doctree)
        for warning, kwargs in warnings:
            self.warn(*warning, **kwargs)

    def _write_parallel(self, docnames, warnings, nproc):
        def write_process(docs):
            local_warnings = []

            def warnfunc(*args, **kwargs):
                local_warnings.append((args, kwargs))
            self.env.set_warnfunc(warnfunc)
            for docname, doctree in docs:
                self.write_doc(docname, doctree)
            return local_warnings

        def add_warnings(docs, wlist):
            warnings.extend(wlist)

        # warm up caches/compile templates using the first document
        firstname, docnames = docnames[0], docnames[1:]
        doctree = self.env.get_and_resolve_doctree(firstname, self)
        self.write_doc_serialized(firstname, doctree)
        self.write_doc(firstname, doctree)

        tasks = ParallelTasks(nproc)
        chunks = make_chunks(docnames, nproc)

        for chunk in self.app.status_iterator(
                chunks, 'writing output... ', darkgreen, len(chunks)):
            arg = []
            for i, docname in enumerate(chunk):
                doctree = self.env.get_and_resolve_doctree(docname, self)
                self.write_doc_serialized(docname, doctree)
                arg.append((docname, doctree))
            tasks.add_task(write_process, arg, add_warnings)

        # make sure all threads have finished
        self.info(bold('waiting for workers...'))
        tasks.join()

        for warning, kwargs in warnings:
            self.warn(*warning, **kwargs)

    def prepare_writing(self, docnames):
        """A place where you can add logic before :meth:`write_doc` is run"""
        raise NotImplementedError

    def write_doc(self, docname, doctree):
        """Where you actually write something to the filesystem."""
        raise NotImplementedError

    def write_doc_serialized(self, docname, doctree):
        """Handle parts of write_doc that must be called in the main process
        if parallel build is active.
        """
        pass

    def finish(self):
        """Finish the building process.

        The default implementation does nothing.
        """
        pass

    def cleanup(self):
        """Cleanup any resources.

        The default implementation does nothing.
        """
        pass

    def get_builder_config(self, option, default):
        """Return a builder specific option.

        This method allows customization of common builder settings by
        inserting the name of the current builder in the option key.
        If the key does not exist, use default as builder name.
        """
        # At the moment, only XXX_use_index is looked up this way.
        # Every new builder variant must be registered in Config.config_values.
        try:
            optname = '%s_%s' % (self.name, option)
            return getattr(self.config, optname)
        except AttributeError:
            optname = '%s_%s' % (default, option)
            return getattr(self.config, optname)

BUILTIN_BUILDERS = {
    'dummy':      ('dummy', 'DummyBuilder'),
    'html':       ('html', 'StandaloneHTMLBuilder'),
    'dirhtml':    ('html', 'DirectoryHTMLBuilder'),
    'singlehtml': ('html', 'SingleFileHTMLBuilder'),
    'pickle':     ('html', 'PickleHTMLBuilder'),
    'json':       ('html', 'JSONHTMLBuilder'),
    'web':        ('html', 'PickleHTMLBuilder'),
    'htmlhelp':   ('htmlhelp', 'HTMLHelpBuilder'),
    'devhelp':    ('devhelp', 'DevhelpBuilder'),
    'qthelp':     ('qthelp', 'QtHelpBuilder'),
    'applehelp':  ('applehelp', 'AppleHelpBuilder'),
    'epub':       ('epub', 'EpubBuilder'),
    'epub3':      ('epub3', 'Epub3Builder'),
    'latex':      ('latex', 'LaTeXBuilder'),
    'text':       ('text', 'TextBuilder'),
    'man':        ('manpage', 'ManualPageBuilder'),
    'texinfo':    ('texinfo', 'TexinfoBuilder'),
    'changes':    ('changes', 'ChangesBuilder'),
    'linkcheck':  ('linkcheck', 'CheckExternalLinksBuilder'),
    'websupport': ('websupport', 'WebSupportBuilder'),
    'gettext':    ('gettext', 'MessageCatalogBuilder'),
    'xml':        ('xml', 'XMLBuilder'),
    'pseudoxml':  ('xml', 'PseudoXMLBuilder'),
}
