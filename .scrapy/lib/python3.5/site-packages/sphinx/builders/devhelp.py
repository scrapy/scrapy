# -*- coding: utf-8 -*-
"""
    sphinx.builders.devhelp
    ~~~~~~~~~~~~~~~~~~~~~~~

    Build HTML documentation and Devhelp_ support files.

    .. _Devhelp: http://live.gnome.org/devhelp

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""
from __future__ import absolute_import

import re
from os import path

from docutils import nodes

from sphinx import addnodes
from sphinx.builders.html import StandaloneHTMLBuilder

try:
    import xml.etree.ElementTree as etree
except ImportError:
    try:
        import lxml.etree as etree
    except ImportError:
        try:
            import elementtree.ElementTree as etree
        except ImportError:
            import cElementTree as etree

try:
    import gzip

    def comp_open(filename, mode='rb'):
        return gzip.open(filename + '.gz', mode)
except ImportError:
    def comp_open(filename, mode='rb'):
        return open(filename, mode)


class DevhelpBuilder(StandaloneHTMLBuilder):
    """
    Builder that also outputs GNOME Devhelp file.
    """
    name = 'devhelp'

    # don't copy the reST source
    copysource = False
    supported_image_types = ['image/png', 'image/gif', 'image/jpeg']

    # don't add links
    add_permalinks = False
    # don't add sidebar etc.
    embedded = True

    def init(self):
        StandaloneHTMLBuilder.init(self)
        self.out_suffix = '.html'
        self.link_suffix = '.html'

    def handle_finish(self):
        self.build_devhelp(self.outdir, self.config.devhelp_basename)

    def build_devhelp(self, outdir, outname):
        self.info('dumping devhelp index...')

        # Basic info
        root = etree.Element('book',
                             title=self.config.html_title,
                             name=self.config.project,
                             link="index.html",
                             version=self.config.version)
        tree = etree.ElementTree(root)

        # TOC
        chapters = etree.SubElement(root, 'chapters')

        tocdoc = self.env.get_and_resolve_doctree(
            self.config.master_doc, self, prune_toctrees=False)

        def write_toc(node, parent):
            if isinstance(node, addnodes.compact_paragraph) or \
               isinstance(node, nodes.bullet_list):
                for subnode in node:
                    write_toc(subnode, parent)
            elif isinstance(node, nodes.list_item):
                item = etree.SubElement(parent, 'sub')
                for subnode in node:
                    write_toc(subnode, item)
            elif isinstance(node, nodes.reference):
                parent.attrib['link'] = node['refuri']
                parent.attrib['name'] = node.astext()

        def istoctree(node):
            return isinstance(node, addnodes.compact_paragraph) and \
                'toctree' in node

        for node in tocdoc.traverse(istoctree):
            write_toc(node, chapters)

        # Index
        functions = etree.SubElement(root, 'functions')
        index = self.env.create_index(self)

        def write_index(title, refs, subitems):
            if len(refs) == 0:
                pass
            elif len(refs) == 1:
                etree.SubElement(functions, 'function',
                                 name=title, link=refs[0][1])
            else:
                for i, ref in enumerate(refs):
                    etree.SubElement(functions, 'function',
                                     name="[%d] %s" % (i, title),
                                     link=ref[1])

            if subitems:
                parent_title = re.sub(r'\s*\(.*\)\s*$', '', title)
                for subitem in subitems:
                    write_index("%s %s" % (parent_title, subitem[0]),
                                subitem[1], [])

        for (key, group) in index:
            for title, (refs, subitems, key) in group:
                write_index(title, refs, subitems)

        # Dump the XML file
        f = comp_open(path.join(outdir, outname + '.devhelp'), 'w')
        try:
            tree.write(f, 'utf-8')
        finally:
            f.close()
