# -*- coding: utf-8 -*-
"""
    sphinx.builders.epub
    ~~~~~~~~~~~~~~~~~~~~

    Build epub files.
    Originally derived from qthelp.py.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import os
import re
import codecs
import zipfile
from os import path
from datetime import datetime

try:
    from PIL import Image
except ImportError:
    try:
        import Image
    except ImportError:
        Image = None

from docutils import nodes

from sphinx import addnodes
from sphinx.builders.html import StandaloneHTMLBuilder
from sphinx.util.osutil import ensuredir, copyfile, EEXIST
from sphinx.util.smartypants import sphinx_smarty_pants as ssp
from sphinx.util.console import brown


# (Fragment) templates from which the metainfo files content.opf, toc.ncx,
# mimetype, and META-INF/container.xml are created.
# This template section also defines strings that are embedded in the html
# output but that may be customized by (re-)setting module attributes,
# e.g. from conf.py.

MIMETYPE_TEMPLATE = 'application/epub+zip'  # no EOL!

CONTAINER_TEMPLATE = u'''\
<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0"
      xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="content.opf"
        media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
'''

TOC_TEMPLATE = u'''\
<?xml version="1.0"?>
<ncx version="2005-1" xmlns="http://www.daisy.org/z3986/2005/ncx/">
  <head>
    <meta name="dtb:uid" content="%(uid)s"/>
    <meta name="dtb:depth" content="%(level)d"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle>
    <text>%(title)s</text>
  </docTitle>
  <navMap>
%(navpoints)s
  </navMap>
</ncx>
'''

NAVPOINT_TEMPLATE = u'''\
%(indent)s  <navPoint id="%(navpoint)s" playOrder="%(playorder)d">
%(indent)s    <navLabel>
%(indent)s      <text>%(text)s</text>
%(indent)s    </navLabel>
%(indent)s    <content src="%(refuri)s" />
%(indent)s  </navPoint>'''

NAVPOINT_INDENT = '  '
NODE_NAVPOINT_TEMPLATE = 'navPoint%d'

CONTENT_TEMPLATE = u'''\
<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0"
      unique-identifier="%(uid)s">
  <metadata xmlns:opf="http://www.idpf.org/2007/opf"
        xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:language>%(lang)s</dc:language>
    <dc:title>%(title)s</dc:title>
    <dc:creator opf:role="aut">%(author)s</dc:creator>
    <dc:publisher>%(publisher)s</dc:publisher>
    <dc:rights>%(copyright)s</dc:rights>
    <dc:identifier id="%(uid)s" opf:scheme="%(scheme)s">%(id)s</dc:identifier>
    <dc:date>%(date)s</dc:date>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />
%(files)s
  </manifest>
  <spine toc="ncx">
%(spine)s
  </spine>
  <guide>
%(guide)s
  </guide>
</package>
'''

COVER_TEMPLATE = u'''\
    <meta name="cover" content="%(cover)s"/>
'''

COVERPAGE_NAME = u'epub-cover.xhtml'

FILE_TEMPLATE = u'''\
    <item id="%(id)s"
          href="%(href)s"
          media-type="%(media_type)s" />'''

SPINE_TEMPLATE = u'''\
    <itemref idref="%(idref)s" />'''

NO_LINEAR_SPINE_TEMPLATE = u'''\
    <itemref idref="%(idref)s" linear="no" />'''

GUIDE_TEMPLATE = u'''\
    <reference type="%(type)s" title="%(title)s" href="%(uri)s" />'''

TOCTREE_TEMPLATE = u'toctree-l%d'

DOCTYPE = u'''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'''

LINK_TARGET_TEMPLATE = u' [%(uri)s]'

FOOTNOTE_LABEL_TEMPLATE = u'#%d'

FOOTNOTES_RUBRIC_NAME = u'Footnotes'

CSS_LINK_TARGET_CLASS = u'link-target'

# XXX These strings should be localized according to epub_language
GUIDE_TITLES = {
    'toc': u'Table of Contents',
    'cover': u'Cover'
}

MEDIA_TYPES = {
    '.xhtml': 'application/xhtml+xml',
    '.css': 'text/css',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.otf': 'application/x-font-otf',
    '.ttf': 'application/x-font-ttf',
    '.woff': 'application/font-woff',
}

VECTOR_GRAPHICS_EXTENSIONS = ('.svg',)

# Regular expression to match colons only in local fragment identifiers.
# If the URI contains a colon before the #,
# it is an external link that should not change.
REFURI_RE = re.compile("([^#:]*#)(.*)")


# The epub publisher

class EpubBuilder(StandaloneHTMLBuilder):
    """
    Builder that outputs epub files.

    It creates the metainfo files container.opf, toc.ncx, mimetype, and
    META-INF/container.xml.  Afterwards, all necessary files are zipped to an
    epub file.
    """
    name = 'epub'

    # don't copy the reST source
    copysource = False
    supported_image_types = ['image/svg+xml', 'image/png', 'image/gif',
                             'image/jpeg']

    # don't add links
    add_permalinks = False
    # don't add sidebar etc.
    embedded = True
    # dont' create links to original images from images
    html_scaled_image_link = False
    # don't generate search index or include search page
    search = False

    mimetype_template = MIMETYPE_TEMPLATE
    container_template = CONTAINER_TEMPLATE
    toc_template = TOC_TEMPLATE
    navpoint_template = NAVPOINT_TEMPLATE
    navpoint_indent = NAVPOINT_INDENT
    node_navpoint_template = NODE_NAVPOINT_TEMPLATE
    content_template = CONTENT_TEMPLATE
    cover_template = COVER_TEMPLATE
    coverpage_name = COVERPAGE_NAME
    file_template = FILE_TEMPLATE
    spine_template = SPINE_TEMPLATE
    no_linear_spine_template = NO_LINEAR_SPINE_TEMPLATE
    guide_template = GUIDE_TEMPLATE
    toctree_template = TOCTREE_TEMPLATE
    doctype = DOCTYPE
    link_target_template = LINK_TARGET_TEMPLATE
    css_link_target_class = CSS_LINK_TARGET_CLASS
    guide_titles = GUIDE_TITLES
    media_types = MEDIA_TYPES
    refuri_re = REFURI_RE

    def init(self):
        StandaloneHTMLBuilder.init(self)
        # the output files for epub must be .html only
        self.out_suffix = '.xhtml'
        self.link_suffix = '.xhtml'
        self.playorder = 0
        self.tocid = 0

    def get_theme_config(self):
        return self.config.epub_theme, self.config.epub_theme_options

    # generic support functions
    def make_id(self, name, id_cache={}):
        # id_cache is intentionally mutable
        """Return a unique id for name."""
        id = id_cache.get(name)
        if not id:
            id = 'epub-%d' % self.env.new_serialno('epub')
            id_cache[name] = id
        return id

    def esc(self, name):
        """Replace all characters not allowed in text an attribute values."""
        # Like cgi.escape, but also replace apostrophe
        name = name.replace('&', '&amp;')
        name = name.replace('<', '&lt;')
        name = name.replace('>', '&gt;')
        name = name.replace('"', '&quot;')
        name = name.replace('\'', '&#39;')
        return name

    def get_refnodes(self, doctree, result):
        """Collect section titles, their depth in the toc and the refuri."""
        # XXX: is there a better way than checking the attribute
        # toctree-l[1-8] on the parent node?
        if isinstance(doctree, nodes.reference) and 'refuri' in doctree:
            refuri = doctree['refuri']
            if refuri.startswith('http://') or refuri.startswith('https://') \
               or refuri.startswith('irc:') or refuri.startswith('mailto:'):
                return result
            classes = doctree.parent.attributes['classes']
            for level in range(8, 0, -1):  # or range(1, 8)?
                if (self.toctree_template % level) in classes:
                    result.append({
                        'level': level,
                        'refuri': self.esc(refuri),
                        'text': ssp(self.esc(doctree.astext()))
                    })
                    break
        else:
            for elem in doctree.children:
                result = self.get_refnodes(elem, result)
        return result

    def get_toc(self):
        """Get the total table of contents, containing the master_doc
        and pre and post files not managed by sphinx.
        """
        doctree = self.env.get_and_resolve_doctree(self.config.master_doc,
                                                   self, prune_toctrees=False,
                                                   includehidden=True)
        self.refnodes = self.get_refnodes(doctree, [])
        master_dir = path.dirname(self.config.master_doc)
        if master_dir:
            master_dir += '/'  # XXX or os.sep?
            for item in self.refnodes:
                item['refuri'] = master_dir + item['refuri']
        self.toc_add_files(self.refnodes)

    def toc_add_files(self, refnodes):
        """Add the master_doc, pre and post files to a list of refnodes.
        """
        refnodes.insert(0, {
            'level': 1,
            'refuri': self.esc(self.config.master_doc + self.out_suffix),
            'text': ssp(self.esc(
                self.env.titles[self.config.master_doc].astext()))
        })
        for file, text in reversed(self.config.epub_pre_files):
            refnodes.insert(0, {
                'level': 1,
                'refuri': self.esc(file),
                'text': ssp(self.esc(text))
            })
        for file, text in self.config.epub_post_files:
            refnodes.append({
                'level': 1,
                'refuri': self.esc(file),
                'text': ssp(self.esc(text))
            })

    def fix_fragment(self, prefix, fragment):
        """Return a href/id attribute with colons replaced by hyphens."""
        return prefix + fragment.replace(':', '-')

    def fix_ids(self, tree):
        """Replace colons with hyphens in href and id attributes.

        Some readers crash because they interpret the part as a
        transport protocol specification.
        """
        for node in tree.traverse(nodes.reference):
            if 'refuri' in node:
                m = self.refuri_re.match(node['refuri'])
                if m:
                    node['refuri'] = self.fix_fragment(m.group(1), m.group(2))
            if 'refid' in node:
                node['refid'] = self.fix_fragment('', node['refid'])
        for node in tree.traverse(addnodes.desc_signature):
            ids = node.attributes['ids']
            newids = []
            for id in ids:
                newids.append(self.fix_fragment('', id))
            node.attributes['ids'] = newids

    def add_visible_links(self, tree, show_urls='inline'):
        """Add visible link targets for external links"""

        def make_footnote_ref(doc, label):
            """Create a footnote_reference node with children"""
            footnote_ref = nodes.footnote_reference('[#]_')
            footnote_ref.append(nodes.Text(label))
            doc.note_autofootnote_ref(footnote_ref)
            return footnote_ref

        def make_footnote(doc, label, uri):
            """Create a footnote node with children"""
            footnote = nodes.footnote(uri)
            para = nodes.paragraph()
            para.append(nodes.Text(uri))
            footnote.append(para)
            footnote.insert(0, nodes.label('', label))
            doc.note_autofootnote(footnote)
            return footnote

        def footnote_spot(tree):
            """Find or create a spot to place footnotes.

            The function returns the tuple (parent, index)."""
            # The code uses the following heuristic:
            # a) place them after the last existing footnote
            # b) place them after an (empty) Footnotes rubric
            # c) create an empty Footnotes rubric at the end of the document
            fns = tree.traverse(nodes.footnote)
            if fns:
                fn = fns[-1]
                return fn.parent, fn.parent.index(fn) + 1
            for node in tree.traverse(nodes.rubric):
                if len(node.children) == 1 and \
                        node.children[0].astext() == FOOTNOTES_RUBRIC_NAME:
                    return node.parent, node.parent.index(node) + 1
            doc = tree.traverse(nodes.document)[0]
            rub = nodes.rubric()
            rub.append(nodes.Text(FOOTNOTES_RUBRIC_NAME))
            doc.append(rub)
            return doc, doc.index(rub) + 1

        if show_urls == 'no':
            return
        if show_urls == 'footnote':
            doc = tree.traverse(nodes.document)[0]
            fn_spot, fn_idx = footnote_spot(tree)
            nr = 1
        for node in tree.traverse(nodes.reference):
            uri = node.get('refuri', '')
            if (uri.startswith('http:') or uri.startswith('https:') or
                    uri.startswith('ftp:')) and uri not in node.astext():
                idx = node.parent.index(node) + 1
                if show_urls == 'inline':
                    uri = self.link_target_template % {'uri': uri}
                    link = nodes.inline(uri, uri)
                    link['classes'].append(self.css_link_target_class)
                    node.parent.insert(idx, link)
                elif show_urls == 'footnote':
                    label = FOOTNOTE_LABEL_TEMPLATE % nr
                    nr += 1
                    footnote_ref = make_footnote_ref(doc, label)
                    node.parent.insert(idx, footnote_ref)
                    footnote = make_footnote(doc, label, uri)
                    fn_spot.insert(fn_idx, footnote)
                    footnote_ref['refid'] = footnote['ids'][0]
                    footnote.add_backref(footnote_ref['ids'][0])
                    fn_idx += 1

    def write_doc(self, docname, doctree):
        """Write one document file.

        This method is overwritten in order to fix fragment identifiers
        and to add visible external links.
        """
        self.fix_ids(doctree)
        self.add_visible_links(doctree, self.config.epub_show_urls)
        return StandaloneHTMLBuilder.write_doc(self, docname, doctree)

    def fix_genindex(self, tree):
        """Fix href attributes for genindex pages."""
        # XXX: modifies tree inline
        # Logic modeled from themes/basic/genindex.html
        for key, columns in tree:
            for entryname, (links, subitems, key_) in columns:
                for (i, (ismain, link)) in enumerate(links):
                    m = self.refuri_re.match(link)
                    if m:
                        links[i] = (ismain,
                                    self.fix_fragment(m.group(1), m.group(2)))
                for subentryname, subentrylinks in subitems:
                    for (i, (ismain, link)) in enumerate(subentrylinks):
                        m = self.refuri_re.match(link)
                        if m:
                            subentrylinks[i] = (ismain,
                                                self.fix_fragment(m.group(1), m.group(2)))

    def is_vector_graphics(self, filename):
        """Does the filename extension indicate a vector graphic format?"""
        ext = path.splitext(filename)[-1]
        return ext in VECTOR_GRAPHICS_EXTENSIONS

    def copy_image_files_pil(self):
        """Copy images using the PIL.
        The method tries to read and write the files with the PIL,
        converting the format and resizing the image if necessary/possible.
        """
        ensuredir(path.join(self.outdir, self.imagedir))
        for src in self.app.status_iterator(self.images, 'copying images... ',
                                            brown, len(self.images)):
            dest = self.images[src]
            try:
                img = Image.open(path.join(self.srcdir, src))
            except IOError:
                if not self.is_vector_graphics(src):
                    self.warn('cannot read image file %r: copying it instead' %
                              (path.join(self.srcdir, src), ))
                try:
                    copyfile(path.join(self.srcdir, src),
                             path.join(self.outdir, self.imagedir, dest))
                except (IOError, OSError) as err:
                    self.warn('cannot copy image file %r: %s' %
                              (path.join(self.srcdir, src), err))
                continue
            if self.config.epub_fix_images:
                if img.mode in ('P',):
                    # See PIL documentation for Image.convert()
                    img = img.convert()
            if self.config.epub_max_image_width > 0:
                (width, height) = img.size
                nw = self.config.epub_max_image_width
                if width > nw:
                    nh = (height * nw) / width
                    img = img.resize((nw, nh), Image.BICUBIC)
            try:
                img.save(path.join(self.outdir, self.imagedir, dest))
            except (IOError, OSError) as err:
                self.warn('cannot write image file %r: %s' %
                          (path.join(self.srcdir, src), err))

    def copy_image_files(self):
        """Copy image files to destination directory.
        This overwritten method can use the PIL to convert image files.
        """
        if self.images:
            if self.config.epub_fix_images or self.config.epub_max_image_width:
                if not Image:
                    self.warn('PIL not found - copying image files')
                    super(EpubBuilder, self).copy_image_files()
                else:
                    self.copy_image_files_pil()
            else:
                super(EpubBuilder, self).copy_image_files()

    def handle_page(self, pagename, addctx, templatename='page.html',
                    outfilename=None, event_arg=None):
        """Create a rendered page.

        This method is overwritten for genindex pages in order to fix href link
        attributes.
        """
        if pagename.startswith('genindex'):
            self.fix_genindex(addctx['genindexentries'])
        addctx['doctype'] = self.doctype
        StandaloneHTMLBuilder.handle_page(self, pagename, addctx, templatename,
                                          outfilename, event_arg)

    # Finish by building the epub file
    def handle_finish(self):
        """Create the metainfo files and finally the epub."""
        self.get_toc()
        self.build_mimetype(self.outdir, 'mimetype')
        self.build_container(self.outdir, 'META-INF/container.xml')
        self.build_content(self.outdir, 'content.opf')
        self.build_toc(self.outdir, 'toc.ncx')
        self.build_epub(self.outdir, self.config.epub_basename + '.epub')

    def build_mimetype(self, outdir, outname):
        """Write the metainfo file mimetype."""
        self.info('writing %s file...' % outname)
        f = codecs.open(path.join(outdir, outname), 'w', 'utf-8')
        try:
            f.write(self.mimetype_template)
        finally:
            f.close()

    def build_container(self, outdir, outname):
        """Write the metainfo file META-INF/cointainer.xml."""
        self.info('writing %s file...' % outname)
        fn = path.join(outdir, outname)
        try:
            os.mkdir(path.dirname(fn))
        except OSError as err:
            if err.errno != EEXIST:
                raise
        f = codecs.open(path.join(outdir, outname), 'w', 'utf-8')
        try:
            f.write(self.container_template)
        finally:
            f.close()

    def content_metadata(self, files, spine, guide):
        """Create a dictionary with all metadata for the content.opf
        file properly escaped.
        """
        metadata = {}
        metadata['title'] = self.esc(self.config.epub_title)
        metadata['author'] = self.esc(self.config.epub_author)
        metadata['uid'] = self.esc(self.config.epub_uid)
        metadata['lang'] = self.esc(self.config.epub_language)
        metadata['publisher'] = self.esc(self.config.epub_publisher)
        metadata['copyright'] = self.esc(self.config.epub_copyright)
        metadata['scheme'] = self.esc(self.config.epub_scheme)
        metadata['id'] = self.esc(self.config.epub_identifier)
        metadata['date'] = self.esc(datetime.utcnow().strftime("%Y-%m-%d"))
        metadata['files'] = files
        metadata['spine'] = spine
        metadata['guide'] = guide
        return metadata

    def build_content(self, outdir, outname):
        """Write the metainfo file content.opf It contains bibliographic data,
        a file list and the spine (the reading order).
        """
        self.info('writing %s file...' % outname)

        # files
        if not outdir.endswith(os.sep):
            outdir += os.sep
        olen = len(outdir)
        projectfiles = []
        self.files = []
        self.ignored_files = ['.buildinfo', 'mimetype', 'content.opf',
                              'toc.ncx', 'META-INF/container.xml',
                              self.config.epub_basename + '.epub'] + \
            self.config.epub_exclude_files
        for root, dirs, files in os.walk(outdir):
            for fn in files:
                filename = path.join(root, fn)[olen:]
                if filename in self.ignored_files:
                    continue
                ext = path.splitext(filename)[-1]
                if ext not in self.media_types:
                    # we always have JS and potentially OpenSearch files, don't
                    # always warn about them
                    if ext not in ('.js', '.xml'):
                        self.warn('unknown mimetype for %s, ignoring' % filename)
                    continue
                filename = filename.replace(os.sep, '/')
                projectfiles.append(self.file_template % {
                    'href': self.esc(filename),
                    'id': self.esc(self.make_id(filename)),
                    'media_type': self.esc(self.media_types[ext])
                })
                self.files.append(filename)

        # spine
        spine = []
        spinefiles = set()
        for item in self.refnodes:
            if '#' in item['refuri']:
                continue
            if item['refuri'] in self.ignored_files:
                continue
            spine.append(self.spine_template % {
                'idref': self.esc(self.make_id(item['refuri']))
            })
            spinefiles.add(item['refuri'])
        for info in self.domain_indices:
            spine.append(self.spine_template % {
                'idref': self.esc(self.make_id(info[0] + self.out_suffix))
            })
            spinefiles.add(info[0] + self.out_suffix)
        if self.get_builder_config('use_index', 'epub'):
            spine.append(self.spine_template % {
                'idref': self.esc(self.make_id('genindex' + self.out_suffix))
            })
            spinefiles.add('genindex' + self.out_suffix)
        # add auto generated files
        for name in self.files:
            if name not in spinefiles and name.endswith(self.out_suffix):
                spine.append(self.no_linear_spine_template % {
                    'idref': self.esc(self.make_id(name))
                })

        # add the optional cover
        content_tmpl = self.content_template
        html_tmpl = None
        if self.config.epub_cover:
            image, html_tmpl = self.config.epub_cover
            image = image.replace(os.sep, '/')
            mpos = content_tmpl.rfind('</metadata>')
            cpos = content_tmpl.rfind('\n', 0, mpos) + 1
            content_tmpl = content_tmpl[:cpos] + \
                COVER_TEMPLATE % {'cover': self.esc(self.make_id(image))} + \
                content_tmpl[cpos:]
            if html_tmpl:
                spine.insert(0, self.spine_template % {
                    'idref': self.esc(self.make_id(self.coverpage_name))})
                if self.coverpage_name not in self.files:
                    ext = path.splitext(self.coverpage_name)[-1]
                    self.files.append(self.coverpage_name)
                    projectfiles.append(self.file_template % {
                        'href': self.esc(self.coverpage_name),
                        'id': self.esc(self.make_id(self.coverpage_name)),
                        'media_type': self.esc(self.media_types[ext])
                    })
                ctx = {'image': self.esc(image), 'title': self.config.project}
                self.handle_page(
                    path.splitext(self.coverpage_name)[0], ctx, html_tmpl)
                spinefiles.add(self.coverpage_name)

        guide = []
        auto_add_cover = True
        auto_add_toc = True
        if self.config.epub_guide:
            for type, uri, title in self.config.epub_guide:
                file = uri.split('#')[0]
                if file not in self.files:
                    self.files.append(file)
                if type == 'cover':
                    auto_add_cover = False
                if type == 'toc':
                    auto_add_toc = False
                guide.append(self.guide_template % {
                    'type': self.esc(type),
                    'title': self.esc(title),
                    'uri': self.esc(uri)
                })
        if auto_add_cover and html_tmpl:
            guide.append(self.guide_template % {
                'type': 'cover',
                'title': self.guide_titles['cover'],
                'uri': self.esc(self.coverpage_name)
            })
        if auto_add_toc and self.refnodes:
            guide.append(self.guide_template % {
                'type': 'toc',
                'title': self.guide_titles['toc'],
                'uri': self.esc(self.refnodes[0]['refuri'])
            })
        projectfiles = '\n'.join(projectfiles)
        spine = '\n'.join(spine)
        guide = '\n'.join(guide)

        # write the project file
        f = codecs.open(path.join(outdir, outname), 'w', 'utf-8')
        try:
            f.write(content_tmpl %
                    self.content_metadata(projectfiles, spine, guide))
        finally:
            f.close()

    def new_navpoint(self, node, level, incr=True):
        """Create a new entry in the toc from the node at given level."""
        # XXX Modifies the node
        if incr:
            self.playorder += 1
        self.tocid += 1
        node['indent'] = self.navpoint_indent * level
        node['navpoint'] = self.esc(self.node_navpoint_template % self.tocid)
        node['playorder'] = self.playorder
        return self.navpoint_template % node

    def insert_subnav(self, node, subnav):
        """Insert nested navpoints for given node.

        The node and subnav are already rendered to text.
        """
        nlist = node.rsplit('\n', 1)
        nlist.insert(-1, subnav)
        return '\n'.join(nlist)

    def build_navpoints(self, nodes):
        """Create the toc navigation structure.

        Subelements of a node are nested inside the navpoint.  For nested nodes
        the parent node is reinserted in the subnav.
        """
        navstack = []
        navlist = []
        level = 1
        lastnode = None
        for node in nodes:
            if not node['text']:
                continue
            file = node['refuri'].split('#')[0]
            if file in self.ignored_files:
                continue
            if node['level'] > self.config.epub_tocdepth:
                continue
            if node['level'] == level:
                navlist.append(self.new_navpoint(node, level))
            elif node['level'] == level + 1:
                navstack.append(navlist)
                navlist = []
                level += 1
                if lastnode and self.config.epub_tocdup:
                    # Insert starting point in subtoc with same playOrder
                    navlist.append(self.new_navpoint(lastnode, level, False))
                navlist.append(self.new_navpoint(node, level))
            else:
                while node['level'] < level:
                    subnav = '\n'.join(navlist)
                    navlist = navstack.pop()
                    navlist[-1] = self.insert_subnav(navlist[-1], subnav)
                    level -= 1
                navlist.append(self.new_navpoint(node, level))
            lastnode = node
        while level != 1:
            subnav = '\n'.join(navlist)
            navlist = navstack.pop()
            navlist[-1] = self.insert_subnav(navlist[-1], subnav)
            level -= 1
        return '\n'.join(navlist)

    def toc_metadata(self, level, navpoints):
        """Create a dictionary with all metadata for the toc.ncx file
        properly escaped.
        """
        metadata = {}
        metadata['uid'] = self.config.epub_uid
        metadata['title'] = self.config.epub_title
        metadata['level'] = level
        metadata['navpoints'] = navpoints
        return metadata

    def build_toc(self, outdir, outname):
        """Write the metainfo file toc.ncx."""
        self.info('writing %s file...' % outname)

        if self.config.epub_tocscope == 'default':
            doctree = self.env.get_and_resolve_doctree(self.config.master_doc,
                                                       self, prune_toctrees=False,
                                                       includehidden=False)
            refnodes = self.get_refnodes(doctree, [])
            self.toc_add_files(refnodes)
        else:
            # 'includehidden'
            refnodes = self.refnodes
        navpoints = self.build_navpoints(refnodes)
        level = max(item['level'] for item in self.refnodes)
        level = min(level, self.config.epub_tocdepth)
        f = codecs.open(path.join(outdir, outname), 'w', 'utf-8')
        try:
            f.write(self.toc_template % self.toc_metadata(level, navpoints))
        finally:
            f.close()

    def build_epub(self, outdir, outname):
        """Write the epub file.

        It is a zip file with the mimetype file stored uncompressed as the first
        entry.
        """
        self.info('writing %s file...' % outname)
        projectfiles = ['META-INF/container.xml', 'content.opf', 'toc.ncx'] \
            + self.files
        epub = zipfile.ZipFile(path.join(outdir, outname), 'w',
                               zipfile.ZIP_DEFLATED)
        epub.write(path.join(outdir, 'mimetype'), 'mimetype',
                   zipfile.ZIP_STORED)
        for file in projectfiles:
            fp = path.join(outdir, file)
            epub.write(fp, file, zipfile.ZIP_DEFLATED)
        epub.close()
