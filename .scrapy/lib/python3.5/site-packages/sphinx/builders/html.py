# -*- coding: utf-8 -*-
"""
    sphinx.builders.html
    ~~~~~~~~~~~~~~~~~~~~

    Several HTML builders.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import os
import sys
import zlib
import codecs
import posixpath
from os import path
from hashlib import md5

from six import iteritems, text_type, string_types
from six.moves import cPickle as pickle
from docutils import nodes
from docutils.io import DocTreeInput, StringOutput
from docutils.core import Publisher
from docutils.utils import new_document, relative_path
from docutils.frontend import OptionParser
from docutils.readers.doctree import Reader as DoctreeReader

from sphinx import package_dir, __display_version__
from sphinx.util import jsonimpl, copy_static_entry, copy_extra_entry
from sphinx.util.i18n import format_date
from sphinx.util.osutil import SEP, os_path, relative_uri, ensuredir, \
    movefile, copyfile
from sphinx.util.nodes import inline_all_toctrees
from sphinx.util.matching import patmatch, compile_matchers
from sphinx.locale import _
from sphinx.search import js_index
from sphinx.theming import Theme
from sphinx.builders import Builder
from sphinx.application import ENV_PICKLE_FILENAME
from sphinx.highlighting import PygmentsBridge
from sphinx.util.console import bold, darkgreen, brown
from sphinx.writers.html import HTMLWriter, HTMLTranslator, \
    SmartyPantsHTMLTranslator

#: the filename for the inventory of objects
INVENTORY_FILENAME = 'objects.inv'
#: the filename for the "last build" file (for serializing builders)
LAST_BUILD_FILENAME = 'last_build'


def get_stable_hash(obj):
    """
    Return a stable hash for a Python data structure.  We can't just use
    the md5 of str(obj) since for example dictionary items are enumerated
    in unpredictable order due to hash randomization in newer Pythons.
    """
    if isinstance(obj, dict):
        return get_stable_hash(list(obj.items()))
    elif isinstance(obj, (list, tuple)):
        obj = sorted(get_stable_hash(o) for o in obj)
    return md5(text_type(obj).encode('utf8')).hexdigest()


class StandaloneHTMLBuilder(Builder):
    """
    Builds standalone HTML docs.
    """
    name = 'html'
    format = 'html'
    copysource = True
    allow_parallel = True
    out_suffix = '.html'
    link_suffix = '.html'  # defaults to matching out_suffix
    indexer_format = js_index
    indexer_dumps_unicode = True
    # create links to original images from images [True/False]
    html_scaled_image_link = True
    supported_image_types = ['image/svg+xml', 'image/png',
                             'image/gif', 'image/jpeg']
    searchindex_filename = 'searchindex.js'
    add_permalinks = True
    embedded = False  # for things like HTML help or Qt help: suppresses sidebar
    search = True  # for things like HTML help and Apple help: suppress search

    # This is a class attribute because it is mutated by Sphinx.add_javascript.
    script_files = ['_static/jquery.js', '_static/underscore.js',
                    '_static/doctools.js']
    # Dito for this one.
    css_files = []

    default_sidebars = ['localtoc.html', 'relations.html',
                        'sourcelink.html', 'searchbox.html']

    # cached publisher object for snippets
    _publisher = None

    def init(self):
        # a hash of all config values that, if changed, cause a full rebuild
        self.config_hash = ''
        self.tags_hash = ''
        # basename of images directory
        self.imagedir = '_images'
        # section numbers for headings in the currently visited document
        self.secnumbers = {}
        # currently written docname
        self.current_docname = None

        self.init_templates()
        self.init_highlighter()
        self.init_translator_class()
        if self.config.html_file_suffix is not None:
            self.out_suffix = self.config.html_file_suffix

        if self.config.html_link_suffix is not None:
            self.link_suffix = self.config.html_link_suffix
        else:
            self.link_suffix = self.out_suffix

        if self.config.language is not None:
            if self._get_translations_js():
                self.script_files.append('_static/translations.js')

    def _get_translations_js(self):
        candidates = [path.join(package_dir, 'locale', self.config.language,
                                'LC_MESSAGES', 'sphinx.js'),
                      path.join(sys.prefix, 'share/sphinx/locale',
                                self.config.language, 'sphinx.js')] + \
                     [path.join(dir, self.config.language,
                                'LC_MESSAGES', 'sphinx.js')
                      for dir in self.config.locale_dirs]
        for jsfile in candidates:
            if path.isfile(jsfile):
                return jsfile
        return None

    def get_theme_config(self):
        return self.config.html_theme, self.config.html_theme_options

    def init_templates(self):
        Theme.init_themes(self.confdir, self.config.html_theme_path,
                          warn=self.warn)
        themename, themeoptions = self.get_theme_config()
        self.theme = Theme(themename, warn=self.warn)
        self.theme_options = themeoptions.copy()
        self.create_template_bridge()
        self.templates.init(self, self.theme)

    def init_highlighter(self):
        # determine Pygments style and create the highlighter
        if self.config.pygments_style is not None:
            style = self.config.pygments_style
        elif self.theme:
            style = self.theme.get_confstr('theme', 'pygments_style', 'none')
        else:
            style = 'sphinx'
        self.highlighter = PygmentsBridge('html', style,
                                          self.config.trim_doctest_flags)

    def init_translator_class(self):
        if self.translator_class is not None:
            pass
        elif self.config.html_translator_class:
            self.translator_class = self.app.import_object(
                self.config.html_translator_class,
                'html_translator_class setting')
        elif self.config.html_use_smartypants:
            self.translator_class = SmartyPantsHTMLTranslator
        else:
            self.translator_class = HTMLTranslator

    def get_outdated_docs(self):
        cfgdict = dict((name, self.config[name])
                       for (name, desc) in iteritems(self.config.values)
                       if desc[1] == 'html')
        self.config_hash = get_stable_hash(cfgdict)
        self.tags_hash = get_stable_hash(sorted(self.tags))
        old_config_hash = old_tags_hash = ''
        try:
            fp = open(path.join(self.outdir, '.buildinfo'))
            try:
                version = fp.readline()
                if version.rstrip() != '# Sphinx build info version 1':
                    raise ValueError
                fp.readline()  # skip commentary
                cfg, old_config_hash = fp.readline().strip().split(': ')
                if cfg != 'config':
                    raise ValueError
                tag, old_tags_hash = fp.readline().strip().split(': ')
                if tag != 'tags':
                    raise ValueError
            finally:
                fp.close()
        except ValueError:
            self.warn('unsupported build info format in %r, building all' %
                      path.join(self.outdir, '.buildinfo'))
        except Exception:
            pass
        if old_config_hash != self.config_hash or \
           old_tags_hash != self.tags_hash:
            for docname in self.env.found_docs:
                yield docname
            return

        if self.templates:
            template_mtime = self.templates.newest_template_mtime()
        else:
            template_mtime = 0
        for docname in self.env.found_docs:
            if docname not in self.env.all_docs:
                yield docname
                continue
            targetname = self.get_outfilename(docname)
            try:
                targetmtime = path.getmtime(targetname)
            except Exception:
                targetmtime = 0
            try:
                srcmtime = max(path.getmtime(self.env.doc2path(docname)),
                               template_mtime)
                if srcmtime > targetmtime:
                    yield docname
            except EnvironmentError:
                # source doesn't exist anymore
                pass

    def render_partial(self, node):
        """Utility: Render a lone doctree node."""
        if node is None:
            return {'fragment': ''}
        doc = new_document(b'<partial node>')
        doc.append(node)

        if self._publisher is None:
            self._publisher = Publisher(
                source_class = DocTreeInput,
                destination_class=StringOutput)
            self._publisher.set_components('standalone',
                                           'restructuredtext', 'pseudoxml')

        pub = self._publisher

        pub.reader = DoctreeReader()
        pub.writer = HTMLWriter(self)
        pub.process_programmatic_settings(
            None, {'output_encoding': 'unicode'}, None)
        pub.set_source(doc, None)
        pub.set_destination(None, None)
        pub.publish()
        return pub.writer.parts

    def prepare_writing(self, docnames):
        # create the search indexer
        self.indexer = None
        if self.search:
            from sphinx.search import IndexBuilder, languages
            lang = self.config.html_search_language or self.config.language
            if not lang or lang not in languages:
                lang = 'en'
            self.indexer = IndexBuilder(self.env, lang,
                                        self.config.html_search_options,
                                        self.config.html_search_scorer)
            self.load_indexer(docnames)

        self.docwriter = HTMLWriter(self)
        self.docsettings = OptionParser(
            defaults=self.env.settings,
            components=(self.docwriter,),
            read_config_files=True).get_default_values()
        self.docsettings.compact_lists = bool(self.config.html_compact_lists)

        # determine the additional indices to include
        self.domain_indices = []
        # html_domain_indices can be False/True or a list of index names
        indices_config = self.config.html_domain_indices
        if indices_config:
            for domain_name in sorted(self.env.domains):
                domain = self.env.domains[domain_name]
                for indexcls in domain.indices:
                    indexname = '%s-%s' % (domain.name, indexcls.name)
                    if isinstance(indices_config, list):
                        if indexname not in indices_config:
                            continue
                    # deprecated config value
                    if indexname == 'py-modindex' and \
                       not self.config.html_use_modindex:
                        continue
                    content, collapse = indexcls(domain).generate()
                    if content:
                        self.domain_indices.append(
                            (indexname, indexcls, content, collapse))

        # format the "last updated on" string, only once is enough since it
        # typically doesn't include the time of day
        lufmt = self.config.html_last_updated_fmt
        if lufmt is not None:
            self.last_updated = format_date(lufmt or _('%b %d, %Y'),
                                            language=self.config.language,
                                            warn=self.warn)
        else:
            self.last_updated = None

        logo = self.config.html_logo and \
            path.basename(self.config.html_logo) or ''

        favicon = self.config.html_favicon and \
            path.basename(self.config.html_favicon) or ''
        if favicon and os.path.splitext(favicon)[1] != '.ico':
            self.warn('html_favicon is not an .ico file')

        if not isinstance(self.config.html_use_opensearch, string_types):
            self.warn('html_use_opensearch config value must now be a string')

        self.relations = self.env.collect_relations()

        rellinks = []
        if self.get_builder_config('use_index', 'html'):
            rellinks.append(('genindex', _('General Index'), 'I', _('index')))
        for indexname, indexcls, content, collapse in self.domain_indices:
            # if it has a short name
            if indexcls.shortname:
                rellinks.append((indexname, indexcls.localname,
                                 '', indexcls.shortname))

        if self.config.html_style is not None:
            stylename = self.config.html_style
        elif self.theme:
            stylename = self.theme.get_confstr('theme', 'stylesheet')
        else:
            stylename = 'default.css'

        self.globalcontext = dict(
            embedded = self.embedded,
            project = self.config.project,
            release = self.config.release,
            version = self.config.version,
            last_updated = self.last_updated,
            copyright = self.config.copyright,
            master_doc = self.config.master_doc,
            use_opensearch = self.config.html_use_opensearch,
            docstitle = self.config.html_title,
            shorttitle = self.config.html_short_title,
            show_copyright = self.config.html_show_copyright,
            show_sphinx = self.config.html_show_sphinx,
            has_source = self.config.html_copy_source,
            show_source = self.config.html_show_sourcelink,
            file_suffix = self.out_suffix,
            script_files = self.script_files,
            language = self.config.language,
            css_files = self.css_files,
            sphinx_version = __display_version__,
            style = stylename,
            rellinks = rellinks,
            builder = self.name,
            parents = [],
            logo = logo,
            favicon = favicon,
        )
        if self.theme:
            self.globalcontext.update(
                ('theme_' + key, val) for (key, val) in
                iteritems(self.theme.get_options(self.theme_options)))
        self.globalcontext.update(self.config.html_context)

    def get_doc_context(self, docname, body, metatags):
        """Collect items for the template context of a page."""
        # find out relations
        prev = next = None
        parents = []
        rellinks = self.globalcontext['rellinks'][:]
        related = self.relations.get(docname)
        titles = self.env.titles
        if related and related[2]:
            try:
                next = {
                    'link': self.get_relative_uri(docname, related[2]),
                    'title': self.render_partial(titles[related[2]])['title']
                }
                rellinks.append((related[2], next['title'], 'N', _('next')))
            except KeyError:
                next = None
        if related and related[1]:
            try:
                prev = {
                    'link': self.get_relative_uri(docname, related[1]),
                    'title': self.render_partial(titles[related[1]])['title']
                }
                rellinks.append((related[1], prev['title'], 'P', _('previous')))
            except KeyError:
                # the relation is (somehow) not in the TOC tree, handle
                # that gracefully
                prev = None
        while related and related[0]:
            try:
                parents.append(
                    {'link': self.get_relative_uri(docname, related[0]),
                     'title': self.render_partial(titles[related[0]])['title']})
            except KeyError:
                pass
            related = self.relations.get(related[0])
        if parents:
            # remove link to the master file; we have a generic
            # "back to index" link already
            parents.pop()
        parents.reverse()

        # title rendered as HTML
        title = self.env.longtitles.get(docname)
        title = title and self.render_partial(title)['title'] or ''
        # the name for the copied source
        sourcename = self.config.html_copy_source and docname + '.txt' or ''

        # metadata for the document
        meta = self.env.metadata.get(docname)

        # Suffix for the document
        source_suffix = '.' + self.env.doc2path(docname).split('.')[-1]

        # local TOC and global TOC tree
        self_toc = self.env.get_toc_for(docname, self)
        toc = self.render_partial(self_toc)['fragment']

        return dict(
            parents = parents,
            prev = prev,
            next = next,
            title = title,
            meta = meta,
            body = body,
            metatags = metatags,
            rellinks = rellinks,
            sourcename = sourcename,
            toc = toc,
            # only display a TOC if there's more than one item to show
            display_toc = (self.env.toc_num_entries[docname] > 1),
            page_source_suffix = source_suffix,
        )

    def write_doc(self, docname, doctree):
        destination = StringOutput(encoding='utf-8')
        doctree.settings = self.docsettings

        self.secnumbers = self.env.toc_secnumbers.get(docname, {})
        self.fignumbers = self.env.toc_fignumbers.get(docname, {})
        self.imgpath = relative_uri(self.get_target_uri(docname), '_images')
        self.dlpath = relative_uri(self.get_target_uri(docname), '_downloads')
        self.current_docname = docname
        self.docwriter.write(doctree, destination)
        self.docwriter.assemble_parts()
        body = self.docwriter.parts['fragment']
        metatags = self.docwriter.clean_meta

        ctx = self.get_doc_context(docname, body, metatags)
        self.handle_page(docname, ctx, event_arg=doctree)

    def write_doc_serialized(self, docname, doctree):
        self.imgpath = relative_uri(self.get_target_uri(docname), self.imagedir)
        self.post_process_images(doctree)
        title = self.env.longtitles.get(docname)
        title = title and self.render_partial(title)['title'] or ''
        self.index_page(docname, doctree, title)

    def finish(self):
        self.finish_tasks.add_task(self.gen_indices)
        self.finish_tasks.add_task(self.gen_additional_pages)
        self.finish_tasks.add_task(self.copy_image_files)
        self.finish_tasks.add_task(self.copy_download_files)
        self.finish_tasks.add_task(self.copy_static_files)
        self.finish_tasks.add_task(self.copy_extra_files)
        self.finish_tasks.add_task(self.write_buildinfo)

        # dump the search index
        self.handle_finish()

    def gen_indices(self):
        self.info(bold('generating indices...'), nonl=1)

        # the global general index
        if self.get_builder_config('use_index', 'html'):
            self.write_genindex()

        # the global domain-specific indices
        self.write_domain_indices()

        self.info()

    def gen_additional_pages(self):
        # pages from extensions
        for pagelist in self.app.emit('html-collect-pages'):
            for pagename, context, template in pagelist:
                self.handle_page(pagename, context, template)

        self.info(bold('writing additional pages...'), nonl=1)

        # additional pages from conf.py
        for pagename, template in self.config.html_additional_pages.items():
            self.info(' '+pagename, nonl=1)
            self.handle_page(pagename, {}, template)

        # the search page
        if self.search:
            self.info(' search', nonl=1)
            self.handle_page('search', {}, 'search.html')

        # the opensearch xml file
        if self.config.html_use_opensearch and self.search:
            self.info(' opensearch', nonl=1)
            fn = path.join(self.outdir, '_static', 'opensearch.xml')
            self.handle_page('opensearch', {}, 'opensearch.xml', outfilename=fn)

        self.info()

    def write_genindex(self):
        # the total count of lines for each index letter, used to distribute
        # the entries into two columns
        genindex = self.env.create_index(self)
        indexcounts = []
        for _k, entries in genindex:
            indexcounts.append(sum(1 + len(subitems)
                                   for _, (_, subitems, _) in entries))

        genindexcontext = dict(
            genindexentries = genindex,
            genindexcounts = indexcounts,
            split_index = self.config.html_split_index,
        )
        self.info(' genindex', nonl=1)

        if self.config.html_split_index:
            self.handle_page('genindex', genindexcontext,
                             'genindex-split.html')
            self.handle_page('genindex-all', genindexcontext,
                             'genindex.html')
            for (key, entries), count in zip(genindex, indexcounts):
                ctx = {'key': key, 'entries': entries, 'count': count,
                       'genindexentries': genindex}
                self.handle_page('genindex-' + key, ctx,
                                 'genindex-single.html')
        else:
            self.handle_page('genindex', genindexcontext, 'genindex.html')

    def write_domain_indices(self):
        for indexname, indexcls, content, collapse in self.domain_indices:
            indexcontext = dict(
                indextitle = indexcls.localname,
                content = content,
                collapse_index = collapse,
            )
            self.info(' ' + indexname, nonl=1)
            self.handle_page(indexname, indexcontext, 'domainindex.html')

    def copy_image_files(self):
        # copy image files
        if self.images:
            ensuredir(path.join(self.outdir, self.imagedir))
            for src in self.app.status_iterator(self.images, 'copying images... ',
                                                brown, len(self.images)):
                dest = self.images[src]
                try:
                    copyfile(path.join(self.srcdir, src),
                             path.join(self.outdir, self.imagedir, dest))
                except Exception as err:
                    self.warn('cannot copy image file %r: %s' %
                              (path.join(self.srcdir, src), err))

    def copy_download_files(self):
        def to_relpath(f):
            return relative_path(self.srcdir, f)
        # copy downloadable files
        if self.env.dlfiles:
            ensuredir(path.join(self.outdir, '_downloads'))
            for src in self.app.status_iterator(self.env.dlfiles,
                                                'copying downloadable files... ',
                                                brown, len(self.env.dlfiles),
                                                stringify_func=to_relpath):
                dest = self.env.dlfiles[src][1]
                try:
                    copyfile(path.join(self.srcdir, src),
                             path.join(self.outdir, '_downloads', dest))
                except Exception as err:
                    self.warn('cannot copy downloadable file %r: %s' %
                              (path.join(self.srcdir, src), err))

    def copy_static_files(self):
        # copy static files
        self.info(bold('copying static files... '), nonl=True)
        ensuredir(path.join(self.outdir, '_static'))
        # first, create pygments style file
        f = open(path.join(self.outdir, '_static', 'pygments.css'), 'w')
        f.write(self.highlighter.get_stylesheet())
        f.close()
        # then, copy translations JavaScript file
        if self.config.language is not None:
            jsfile = self._get_translations_js()
            if jsfile:
                copyfile(jsfile, path.join(self.outdir, '_static',
                                           'translations.js'))

        # copy non-minified stemmer JavaScript file
        if self.indexer is not None:
            jsfile = self.indexer.get_js_stemmer_rawcode()
            if jsfile:
                copyfile(jsfile, path.join(self.outdir, '_static', '_stemmer.js'))

        ctx = self.globalcontext.copy()

        # add context items for search function used in searchtools.js_t
        if self.indexer is not None:
            ctx.update(self.indexer.context_for_searchtool())

        # then, copy over theme-supplied static files
        if self.theme:
            themeentries = [path.join(themepath, 'static')
                            for themepath in self.theme.get_dirchain()[::-1]]
            for entry in themeentries:
                copy_static_entry(entry, path.join(self.outdir, '_static'),
                                  self, ctx)
        # then, copy over all user-supplied static files
        staticentries = [path.join(self.confdir, spath)
                         for spath in self.config.html_static_path]
        matchers = compile_matchers(self.config.exclude_patterns)
        for entry in staticentries:
            if not path.exists(entry):
                self.warn('html_static_path entry %r does not exist' % entry)
                continue
            copy_static_entry(entry, path.join(self.outdir, '_static'), self,
                              ctx, exclude_matchers=matchers)
        # copy logo and favicon files if not already in static path
        if self.config.html_logo:
            logobase = path.basename(self.config.html_logo)
            logotarget = path.join(self.outdir, '_static', logobase)
            if not path.isfile(path.join(self.confdir, self.config.html_logo)):
                self.warn('logo file %r does not exist' % self.config.html_logo)
            elif not path.isfile(logotarget):
                copyfile(path.join(self.confdir, self.config.html_logo),
                         logotarget)
        if self.config.html_favicon:
            iconbase = path.basename(self.config.html_favicon)
            icontarget = path.join(self.outdir, '_static', iconbase)
            if not path.isfile(path.join(self.confdir, self.config.html_favicon)):
                self.warn('favicon file %r does not exist' % self.config.html_favicon)
            elif not path.isfile(icontarget):
                copyfile(path.join(self.confdir, self.config.html_favicon),
                         icontarget)
        self.info('done')

    def copy_extra_files(self):
        # copy html_extra_path files
        self.info(bold('copying extra files... '), nonl=True)
        extraentries = [path.join(self.confdir, epath)
                        for epath in self.config.html_extra_path]
        matchers = compile_matchers(self.config.exclude_patterns)
        for entry in extraentries:
            if not path.exists(entry):
                self.warn('html_extra_path entry %r does not exist' % entry)
                continue
            copy_extra_entry(entry, self.outdir, matchers)
        self.info('done')

    def write_buildinfo(self):
        # write build info file
        fp = open(path.join(self.outdir, '.buildinfo'), 'w')
        try:
            fp.write('# Sphinx build info version 1\n'
                     '# This file hashes the configuration used when building'
                     ' these files. When it is not found, a full rebuild will'
                     ' be done.\nconfig: %s\ntags: %s\n' %
                     (self.config_hash, self.tags_hash))
        finally:
            fp.close()

    def cleanup(self):
        # clean up theme stuff
        if self.theme:
            self.theme.cleanup()

    def post_process_images(self, doctree):
        """Pick the best candidate for an image and link down-scaled images to
        their high res version.
        """
        Builder.post_process_images(self, doctree)

        if self.config.html_scaled_image_link and self.html_scaled_image_link:
            for node in doctree.traverse(nodes.image):
                scale_keys = ('scale', 'width', 'height')
                if not any((key in node) for key in scale_keys) or \
                   isinstance(node.parent, nodes.reference):
                    # docutils does unfortunately not preserve the
                    # ``target`` attribute on images, so we need to check
                    # the parent node here.
                    continue
                uri = node['uri']
                reference = nodes.reference('', '', internal=True)
                if uri in self.images:
                    reference['refuri'] = posixpath.join(self.imgpath,
                                                         self.images[uri])
                else:
                    reference['refuri'] = uri
                node.replace_self(reference)
                reference.append(node)

    def load_indexer(self, docnames):
        keep = set(self.env.all_docs) - set(docnames)
        try:
            searchindexfn = path.join(self.outdir, self.searchindex_filename)
            if self.indexer_dumps_unicode:
                f = codecs.open(searchindexfn, 'r', encoding='utf-8')
            else:
                f = open(searchindexfn, 'rb')
            try:
                self.indexer.load(f, self.indexer_format)
            finally:
                f.close()
        except (IOError, OSError, ValueError):
            if keep:
                self.warn('search index couldn\'t be loaded, but not all '
                          'documents will be built: the index will be '
                          'incomplete.')
        # delete all entries for files that will be rebuilt
        self.indexer.prune(keep)

    def index_page(self, pagename, doctree, title):
        # only index pages with title
        if self.indexer is not None and title:
            self.indexer.feed(pagename, title, doctree)

    def _get_local_toctree(self, docname, collapse=True, **kwds):
        if 'includehidden' not in kwds:
            kwds['includehidden'] = False
        return self.render_partial(self.env.get_toctree_for(
            docname, self, collapse, **kwds))['fragment']

    def get_outfilename(self, pagename):
        return path.join(self.outdir, os_path(pagename) + self.out_suffix)

    def add_sidebars(self, pagename, ctx):
        def has_wildcard(pattern):
            return any(char in pattern for char in '*?[')
        sidebars = None
        matched = None
        customsidebar = None
        for pattern, patsidebars in iteritems(self.config.html_sidebars):
            if patmatch(pagename, pattern):
                if matched:
                    if has_wildcard(pattern):
                        # warn if both patterns contain wildcards
                        if has_wildcard(matched):
                            self.warn('page %s matches two patterns in '
                                      'html_sidebars: %r and %r' %
                                      (pagename, matched, pattern))
                        # else the already matched pattern is more specific
                        # than the present one, because it contains no wildcard
                        continue
                matched = pattern
                sidebars = patsidebars
        if sidebars is None:
            # keep defaults
            pass
        elif isinstance(sidebars, string_types):
            # 0.x compatible mode: insert custom sidebar before searchbox
            customsidebar = sidebars
            sidebars = None
        ctx['sidebars'] = sidebars
        ctx['customsidebar'] = customsidebar

    # --------- these are overwritten by the serialization builder

    def get_target_uri(self, docname, typ=None):
        return docname + self.link_suffix

    def handle_page(self, pagename, addctx, templatename='page.html',
                    outfilename=None, event_arg=None):
        ctx = self.globalcontext.copy()
        # current_page_name is backwards compatibility
        ctx['pagename'] = ctx['current_page_name'] = pagename
        default_baseuri = self.get_target_uri(pagename)
        # in the singlehtml builder, default_baseuri still contains an #anchor
        # part, which relative_uri doesn't really like...
        default_baseuri = default_baseuri.rsplit('#', 1)[0]

        def pathto(otheruri, resource=False, baseuri=default_baseuri):
            if resource and '://' in otheruri:
                # allow non-local resources given by scheme
                return otheruri
            elif not resource:
                otheruri = self.get_target_uri(otheruri)
            uri = relative_uri(baseuri, otheruri) or '#'
            return uri
        ctx['pathto'] = pathto

        def hasdoc(name):
            if name in self.env.all_docs:
                return True
            elif name == 'search' and self.search:
                return True
            elif name == 'genindex' and self.get_builder_config('use_index', 'html'):
                return True
            return False
        ctx['hasdoc'] = hasdoc

        if self.name != 'htmlhelp':
            ctx['encoding'] = encoding = self.config.html_output_encoding
        else:
            ctx['encoding'] = encoding = self.encoding
        ctx['toctree'] = lambda **kw: self._get_local_toctree(pagename, **kw)
        self.add_sidebars(pagename, ctx)
        ctx.update(addctx)

        newtmpl = self.app.emit_firstresult('html-page-context', pagename,
                                            templatename, ctx, event_arg)
        if newtmpl:
            templatename = newtmpl

        try:
            output = self.templates.render(templatename, ctx)
        except UnicodeError:
            self.warn("a Unicode error occurred when rendering the page %s. "
                      "Please make sure all config values that contain "
                      "non-ASCII content are Unicode strings." % pagename)
            return

        if not outfilename:
            outfilename = self.get_outfilename(pagename)
        # outfilename's path is in general different from self.outdir
        ensuredir(path.dirname(outfilename))
        try:
            f = codecs.open(outfilename, 'w', encoding, 'xmlcharrefreplace')
            try:
                f.write(output)
            finally:
                f.close()
        except (IOError, OSError) as err:
            self.warn("error writing file %s: %s" % (outfilename, err))
        if self.copysource and ctx.get('sourcename'):
            # copy the source file for the "show source" link
            source_name = path.join(self.outdir, '_sources',
                                    os_path(ctx['sourcename']))
            ensuredir(path.dirname(source_name))
            copyfile(self.env.doc2path(pagename), source_name)

    def handle_finish(self):
        if self.indexer:
            self.finish_tasks.add_task(self.dump_search_index)
        self.finish_tasks.add_task(self.dump_inventory)

    def dump_inventory(self):
        self.info(bold('dumping object inventory... '), nonl=True)
        f = open(path.join(self.outdir, INVENTORY_FILENAME), 'wb')
        try:
            f.write((u'# Sphinx inventory version 2\n'
                     u'# Project: %s\n'
                     u'# Version: %s\n'
                     u'# The remainder of this file is compressed using zlib.\n'
                     % (self.config.project, self.config.version)).encode('utf-8'))
            compressor = zlib.compressobj(9)
            for domainname, domain in sorted(self.env.domains.items()):
                for name, dispname, type, docname, anchor, prio in \
                        sorted(domain.get_objects()):
                    if anchor.endswith(name):
                        # this can shorten the inventory by as much as 25%
                        anchor = anchor[:-len(name)] + '$'
                    uri = self.get_target_uri(docname)
                    if anchor:
                        uri += '#' + anchor
                    if dispname == name:
                        dispname = u'-'
                    f.write(compressor.compress(
                        (u'%s %s:%s %s %s %s\n' % (name, domainname, type,
                                                   prio, uri, dispname)).encode('utf-8')))
            f.write(compressor.flush())
        finally:
            f.close()
        self.info('done')

    def dump_search_index(self):
        self.info(
            bold('dumping search index in %s ... ' % self.indexer.label()),
            nonl=True)
        self.indexer.prune(self.env.all_docs)
        searchindexfn = path.join(self.outdir, self.searchindex_filename)
        # first write to a temporary file, so that if dumping fails,
        # the existing index won't be overwritten
        if self.indexer_dumps_unicode:
            f = codecs.open(searchindexfn + '.tmp', 'w', encoding='utf-8')
        else:
            f = open(searchindexfn + '.tmp', 'wb')
        try:
            self.indexer.dump(f, self.indexer_format)
        finally:
            f.close()
        movefile(searchindexfn + '.tmp', searchindexfn)
        self.info('done')


class DirectoryHTMLBuilder(StandaloneHTMLBuilder):
    """
    A StandaloneHTMLBuilder that creates all HTML pages as "index.html" in
    a directory given by their pagename, so that generated URLs don't have
    ``.html`` in them.
    """
    name = 'dirhtml'

    def get_target_uri(self, docname, typ=None):
        if docname == 'index':
            return ''
        if docname.endswith(SEP + 'index'):
            return docname[:-5]  # up to sep
        return docname + SEP

    def get_outfilename(self, pagename):
        if pagename == 'index' or pagename.endswith(SEP + 'index'):
            outfilename = path.join(self.outdir, os_path(pagename) +
                                    self.out_suffix)
        else:
            outfilename = path.join(self.outdir, os_path(pagename),
                                    'index' + self.out_suffix)

        return outfilename

    def prepare_writing(self, docnames):
        StandaloneHTMLBuilder.prepare_writing(self, docnames)
        self.globalcontext['no_search_suffix'] = True


class SingleFileHTMLBuilder(StandaloneHTMLBuilder):
    """
    A StandaloneHTMLBuilder subclass that puts the whole document tree on one
    HTML page.
    """
    name = 'singlehtml'
    copysource = False

    def get_outdated_docs(self):
        return 'all documents'

    def get_target_uri(self, docname, typ=None):
        if docname in self.env.all_docs:
            # all references are on the same page...
            return self.config.master_doc + self.out_suffix + \
                '#document-' + docname
        else:
            # chances are this is a html_additional_page
            return docname + self.out_suffix

    def get_relative_uri(self, from_, to, typ=None):
        # ignore source
        return self.get_target_uri(to, typ)

    def fix_refuris(self, tree):
        # fix refuris with double anchor
        fname = self.config.master_doc + self.out_suffix
        for refnode in tree.traverse(nodes.reference):
            if 'refuri' not in refnode:
                continue
            refuri = refnode['refuri']
            hashindex = refuri.find('#')
            if hashindex < 0:
                continue
            hashindex = refuri.find('#', hashindex+1)
            if hashindex >= 0:
                refnode['refuri'] = fname + refuri[hashindex:]

    def _get_local_toctree(self, docname, collapse=True, **kwds):
        if 'includehidden' not in kwds:
            kwds['includehidden'] = False
        toctree = self.env.get_toctree_for(docname, self, collapse, **kwds)
        self.fix_refuris(toctree)
        return self.render_partial(toctree)['fragment']

    def assemble_doctree(self):
        master = self.config.master_doc
        tree = self.env.get_doctree(master)
        tree = inline_all_toctrees(self, set(), master, tree, darkgreen, [master])
        tree['docname'] = master
        self.env.resolve_references(tree, master, self)
        self.fix_refuris(tree)
        return tree

    def assemble_toc_secnumbers(self):
        # Assemble toc_secnumbers to resolve section numbers on SingleHTML.
        # Merge all secnumbers to single secnumber.
        #
        # Note: current Sphinx has refid confliction in singlehtml mode.
        #       To avoid the problem, it replaces key of secnumbers to
        #       tuple of docname and refid.
        #
        #       There are related codes in inline_all_toctres() and
        #       HTMLTranslter#add_secnumber().
        new_secnumbers = {}
        for docname, secnums in iteritems(self.env.toc_secnumbers):
            for id, secnum in iteritems(secnums):
                new_secnumbers[(docname, id)] = secnum

        return {self.config.master_doc: new_secnumbers}

    def assemble_toc_fignumbers(self):
        # Assemble toc_fignumbers to resolve figure numbers on SingleHTML.
        # Merge all fignumbers to single fignumber.
        #
        # Note: current Sphinx has refid confliction in singlehtml mode.
        #       To avoid the problem, it replaces key of secnumbers to
        #       tuple of docname and refid.
        #
        #       There are related codes in inline_all_toctres() and
        #       HTMLTranslter#add_fignumber().
        new_fignumbers = {}
        # {u'foo': {'figure': {'id2': (2,), 'id1': (1,)}}, u'bar': {'figure': {'id1': (3,)}}}
        for docname, fignumlist in iteritems(self.env.toc_fignumbers):
            for figtype, fignums in iteritems(fignumlist):
                new_fignumbers.setdefault((docname, figtype), {})
                for id, fignum in iteritems(fignums):
                    new_fignumbers[(docname, figtype)][id] = fignum

        return {self.config.master_doc: new_fignumbers}

    def get_doc_context(self, docname, body, metatags):
        # no relation links...
        toc = self.env.get_toctree_for(self.config.master_doc, self, False)
        # if there is no toctree, toc is None
        if toc:
            self.fix_refuris(toc)
            toc = self.render_partial(toc)['fragment']
            display_toc = True
        else:
            toc = ''
            display_toc = False
        return dict(
            parents = [],
            prev = None,
            next = None,
            docstitle = None,
            title = self.config.html_title,
            meta = None,
            body = body,
            metatags = metatags,
            rellinks = [],
            sourcename = '',
            toc = toc,
            display_toc = display_toc,
        )

    def write(self, *ignored):
        docnames = self.env.all_docs

        self.info(bold('preparing documents... '), nonl=True)
        self.prepare_writing(docnames)
        self.info('done')

        self.info(bold('assembling single document... '), nonl=True)
        doctree = self.assemble_doctree()
        self.env.toc_secnumbers = self.assemble_toc_secnumbers()
        self.env.toc_fignumbers = self.assemble_toc_fignumbers()
        self.info()
        self.info(bold('writing... '), nonl=True)
        self.write_doc_serialized(self.config.master_doc, doctree)
        self.write_doc(self.config.master_doc, doctree)
        self.info('done')

    def finish(self):
        # no indices or search pages are supported
        self.info(bold('writing additional files...'), nonl=1)

        # additional pages from conf.py
        for pagename, template in self.config.html_additional_pages.items():
            self.info(' '+pagename, nonl=1)
            self.handle_page(pagename, {}, template)

        if self.config.html_use_opensearch:
            self.info(' opensearch', nonl=1)
            fn = path.join(self.outdir, '_static', 'opensearch.xml')
            self.handle_page('opensearch', {}, 'opensearch.xml', outfilename=fn)

        self.info()

        self.copy_image_files()
        self.copy_download_files()
        self.copy_static_files()
        self.copy_extra_files()
        self.write_buildinfo()
        self.dump_inventory()


class SerializingHTMLBuilder(StandaloneHTMLBuilder):
    """
    An abstract builder that serializes the generated HTML.
    """
    #: the serializing implementation to use.  Set this to a module that
    #: implements a `dump`, `load`, `dumps` and `loads` functions
    #: (pickle, simplejson etc.)
    implementation = None
    implementation_dumps_unicode = False
    #: additional arguments for dump()
    additional_dump_args = ()

    #: the filename for the global context file
    globalcontext_filename = None

    supported_image_types = ['image/svg+xml', 'image/png',
                             'image/gif', 'image/jpeg']

    def init(self):
        self.config_hash = ''
        self.tags_hash = ''
        self.imagedir = '_images'
        self.current_docname = None
        self.theme = None       # no theme necessary
        self.templates = None   # no template bridge necessary
        self.init_translator_class()
        self.init_highlighter()

    def get_target_uri(self, docname, typ=None):
        if docname == 'index':
            return ''
        if docname.endswith(SEP + 'index'):
            return docname[:-5]  # up to sep
        return docname + SEP

    def dump_context(self, context, filename):
        if self.implementation_dumps_unicode:
            f = codecs.open(filename, 'w', encoding='utf-8')
        else:
            f = open(filename, 'wb')
        try:
            self.implementation.dump(context, f, *self.additional_dump_args)
        finally:
            f.close()

    def handle_page(self, pagename, ctx, templatename='page.html',
                    outfilename=None, event_arg=None):
        ctx['current_page_name'] = pagename
        self.add_sidebars(pagename, ctx)

        if not outfilename:
            outfilename = path.join(self.outdir,
                                    os_path(pagename) + self.out_suffix)

        # we're not taking the return value here, since no template is
        # actually rendered
        self.app.emit('html-page-context', pagename, templatename, ctx, event_arg)

        ensuredir(path.dirname(outfilename))
        self.dump_context(ctx, outfilename)

        # if there is a source file, copy the source file for the
        # "show source" link
        if ctx.get('sourcename'):
            source_name = path.join(self.outdir, '_sources',
                                    os_path(ctx['sourcename']))
            ensuredir(path.dirname(source_name))
            copyfile(self.env.doc2path(pagename), source_name)

    def handle_finish(self):
        # dump the global context
        outfilename = path.join(self.outdir, self.globalcontext_filename)
        self.dump_context(self.globalcontext, outfilename)

        # super here to dump the search index
        StandaloneHTMLBuilder.handle_finish(self)

        # copy the environment file from the doctree dir to the output dir
        # as needed by the web app
        copyfile(path.join(self.doctreedir, ENV_PICKLE_FILENAME),
                 path.join(self.outdir, ENV_PICKLE_FILENAME))

        # touch 'last build' file, used by the web application to determine
        # when to reload its environment and clear the cache
        open(path.join(self.outdir, LAST_BUILD_FILENAME), 'w').close()


class PickleHTMLBuilder(SerializingHTMLBuilder):
    """
    A Builder that dumps the generated HTML into pickle files.
    """
    implementation = pickle
    implementation_dumps_unicode = False
    additional_dump_args = (pickle.HIGHEST_PROTOCOL,)
    indexer_format = pickle
    indexer_dumps_unicode = False
    name = 'pickle'
    out_suffix = '.fpickle'
    globalcontext_filename = 'globalcontext.pickle'
    searchindex_filename = 'searchindex.pickle'

# compatibility alias
WebHTMLBuilder = PickleHTMLBuilder


class JSONHTMLBuilder(SerializingHTMLBuilder):
    """
    A builder that dumps the generated HTML into JSON files.
    """
    implementation = jsonimpl
    implementation_dumps_unicode = True
    indexer_format = jsonimpl
    indexer_dumps_unicode = True
    name = 'json'
    out_suffix = '.fjson'
    globalcontext_filename = 'globalcontext.json'
    searchindex_filename = 'searchindex.json'

    def init(self):
        SerializingHTMLBuilder.init(self)
