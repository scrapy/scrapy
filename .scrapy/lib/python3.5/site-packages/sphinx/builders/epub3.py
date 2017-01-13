# -*- coding: utf-8 -*-
"""
    sphinx.builders.epub3
    ~~~~~~~~~~~~~~~~~~~~~

    Build epub3 files.
    Originally derived from epub.py.

    :copyright: Copyright 2007-2015 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import codecs
from os import path
from datetime import datetime

from sphinx.builders.epub import EpubBuilder


# (Fragment) templates from which the metainfo files content.opf, toc.ncx,
# mimetype, and META-INF/container.xml are created.
# This template section also defines strings that are embedded in the html
# output but that may be customized by (re-)setting module attributes,
# e.g. from conf.py.

NAVIGATION_DOC_TEMPLATE = u'''\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"\
 xmlns:epub="http://www.idpf.org/2007/ops" lang="%(lang)s" xml:lang="%(lang)s">
  <head>
    <title>%(toc_locale)s</title>
  </head>
  <body>
    <nav epub:type="toc">
      <h1>%(toc_locale)s</h1>
      <ol>
%(navlist)s
      </ol>
    </nav>
  </body>
</html>
'''

NAVLIST_TEMPLATE = u'''%(indent)s      <li><a href="%(refuri)s">%(text)s</a></li>'''
NAVLIST_TEMPLATE_HAS_CHILD = u'''%(indent)s      <li><a href="%(refuri)s">%(text)s</a>'''
NAVLIST_TEMPLATE_BEGIN_BLOCK = u'''%(indent)s        <ol>'''
NAVLIST_TEMPLATE_END_BLOCK = u'''%(indent)s        </ol>
%(indent)s      </li>'''
NAVLIST_INDENT = '  '

PACKAGE_DOC_TEMPLATE = u'''\
<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" xml:lang="%(lang)s"
      unique-identifier="%(uid)s">
  <metadata xmlns:opf="http://www.idpf.org/2007/opf"
        xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:language>%(lang)s</dc:language>
    <dc:title>%(title)s</dc:title>
    <dc:description>%(description)s</dc:description>
    <dc:creator>%(author)s</dc:creator>
    <dc:contributor>%(contributor)s</dc:contributor>
    <dc:publisher>%(publisher)s</dc:publisher>
    <dc:rights>%(copyright)s</dc:rights>
    <dc:identifier id="%(uid)s">%(id)s</dc:identifier>
    <dc:date>%(date)s</dc:date>
    <meta property="dcterms:modified">%(date)s</meta>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />
    <item id="nav" href="nav.xhtml"\
 media-type="application/xhtml+xml" properties="nav"/>
%(files)s
  </manifest>
  <spine toc="ncx" page-progression-direction="%(page_progression_direction)s">
%(spine)s
  </spine>
  <guide>
%(guide)s
  </guide>
</package>
'''

DOCTYPE = u'''<!DOCTYPE html>'''

# The epub3 publisher


class Epub3Builder(EpubBuilder):
    """
    Builder that outputs epub3 files.

    It creates the metainfo files content.opf, nav.xhtml, toc.ncx, mimetype,
    and META-INF/container.xml. Afterwards, all necessary files are zipped to
    an epub file.
    """
    name = 'epub3'

    navigation_doc_template = NAVIGATION_DOC_TEMPLATE
    navlist_template = NAVLIST_TEMPLATE
    navlist_template_has_child = NAVLIST_TEMPLATE_HAS_CHILD
    navlist_template_begin_block = NAVLIST_TEMPLATE_BEGIN_BLOCK
    navlist_template_end_block = NAVLIST_TEMPLATE_END_BLOCK
    navlist_indent = NAVLIST_INDENT
    content_template = PACKAGE_DOC_TEMPLATE
    doctype = DOCTYPE

    # Finish by building the epub file
    def handle_finish(self):
        """Create the metainfo files and finally the epub."""
        self.get_toc()
        self.build_mimetype(self.outdir, 'mimetype')
        self.build_container(self.outdir, 'META-INF/container.xml')
        self.build_content(self.outdir, 'content.opf')
        self.build_navigation_doc(self.outdir, 'nav.xhtml')
        self.build_toc(self.outdir, 'toc.ncx')
        self.build_epub(self.outdir, self.config.epub_basename + '.epub')

    def content_metadata(self, files, spine, guide):
        """Create a dictionary with all metadata for the content.opf
        file properly escaped.
        """
        metadata = super(Epub3Builder, self).content_metadata(
            files, spine, guide)
        metadata['description'] = self.esc(self.config.epub3_description)
        metadata['contributor'] = self.esc(self.config.epub3_contributor)
        metadata['page_progression_direction'] = self.esc(
            self.config.epub3_page_progression_direction) or 'default'
        metadata['date'] = self.esc(datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
        return metadata

    def new_navlist(self, node, level, has_child):
        """Create a new entry in the toc from the node at given level."""
        # XXX Modifies the node
        self.tocid += 1
        node['indent'] = self.navlist_indent * level
        if has_child:
            return self.navlist_template_has_child % node
        else:
            return self.navlist_template % node

    def begin_navlist_block(self, level):
        return self.navlist_template_begin_block % {
            "indent": self.navlist_indent * level
        }

    def end_navlist_block(self, level):
        return self.navlist_template_end_block % {"indent": self.navlist_indent * level}

    def build_navlist(self, nodes):
        """Create the toc navigation structure.

        This method is almost same as build_navpoints method in epub.py.
        This is because the logical navigation structure of epub3 is not
        different from one of epub2.

        The difference from build_navpoints method is templates which are used
        when generating navigation documents.
        """
        navlist = []
        level = 1
        usenodes = []
        for node in nodes:
            if not node['text']:
                continue
            file = node['refuri'].split('#')[0]
            if file in self.ignored_files:
                continue
            if node['level'] > self.config.epub_tocdepth:
                continue
            usenodes.append(node)
        for i, node in enumerate(usenodes):
            curlevel = node['level']
            if curlevel == level + 1:
                navlist.append(self.begin_navlist_block(level))
            while curlevel < level:
                level -= 1
                navlist.append(self.end_navlist_block(level))
            level = curlevel
            if i != len(usenodes) - 1 and usenodes[i + 1]['level'] > level:
                has_child = True
            else:
                has_child = False
            navlist.append(self.new_navlist(node, level, has_child))
        while level != 1:
            level -= 1
            navlist.append(self.end_navlist_block(level))
        return '\n'.join(navlist)

    def navigation_doc_metadata(self, navlist):
        """Create a dictionary with all metadata for the nav.xhtml file
        properly escaped.
        """
        metadata = {}
        metadata['lang'] = self.esc(self.config.epub_language)
        metadata['toc_locale'] = self.esc(self.guide_titles['toc'])
        metadata['navlist'] = navlist
        return metadata

    def build_navigation_doc(self, outdir, outname):
        """Write the metainfo file nav.xhtml."""
        self.info('writing %s file...' % outname)

        if self.config.epub_tocscope == 'default':
            doctree = self.env.get_and_resolve_doctree(
                self.config.master_doc, self,
                prune_toctrees=False, includehidden=False)
            refnodes = self.get_refnodes(doctree, [])
            self.toc_add_files(refnodes)
        else:
            # 'includehidden'
            refnodes = self.refnodes
        navlist = self.build_navlist(refnodes)
        f = codecs.open(path.join(outdir, outname), 'w', 'utf-8')
        try:
            f.write(self.navigation_doc_template %
                    self.navigation_doc_metadata(navlist))
        finally:
            f.close()
            # Add nav.xhtml to epub file
            if outname not in self.files:
                self.files.append(outname)
