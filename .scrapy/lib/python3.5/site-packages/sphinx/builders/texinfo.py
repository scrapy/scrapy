# -*- coding: utf-8 -*-
"""
    sphinx.builders.texinfo
    ~~~~~~~~~~~~~~~~~~~~~~~

    Texinfo builder.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from os import path

from six import iteritems
from docutils import nodes
from docutils.io import FileOutput
from docutils.utils import new_document
from docutils.frontend import OptionParser

from sphinx import addnodes
from sphinx.locale import _
from sphinx.builders import Builder
from sphinx.environment import NoUri
from sphinx.util.nodes import inline_all_toctrees
from sphinx.util.osutil import SEP, copyfile
from sphinx.util.console import bold, darkgreen
from sphinx.writers.texinfo import TexinfoWriter


TEXINFO_MAKEFILE = '''\
# Makefile for Sphinx Texinfo output

infodir ?= /usr/share/info

MAKEINFO = makeinfo --no-split
MAKEINFO_html = makeinfo --no-split --html
MAKEINFO_plaintext = makeinfo --no-split --plaintext
TEXI2PDF = texi2pdf --batch --expand
INSTALL_INFO = install-info

ALLDOCS = $(basename $(wildcard *.texi))

all: info
info: $(addsuffix .info,$(ALLDOCS))
plaintext: $(addsuffix .txt,$(ALLDOCS))
html: $(addsuffix .html,$(ALLDOCS))
pdf: $(addsuffix .pdf,$(ALLDOCS))

install-info: info
\tfor f in *.info; do \\
\t  cp -t $(infodir) "$$f" && \\
\t  $(INSTALL_INFO) --info-dir=$(infodir) "$$f" ; \\
\tdone

uninstall-info: info
\tfor f in *.info; do \\
\t  rm -f "$(infodir)/$$f"  ; \\
\t  $(INSTALL_INFO) --delete --info-dir=$(infodir) "$$f" ; \\
\tdone

%.info: %.texi
\t$(MAKEINFO) -o '$@' '$<'

%.txt: %.texi
\t$(MAKEINFO_plaintext) -o '$@' '$<'

%.html: %.texi
\t$(MAKEINFO_html) -o '$@' '$<'

%.pdf: %.texi
\t-$(TEXI2PDF) '$<'
\t-$(TEXI2PDF) '$<'
\t-$(TEXI2PDF) '$<'

clean:
\trm -f *.info *.pdf *.txt *.html
\trm -f *.log *.ind *.aux *.toc *.syn *.idx *.out *.ilg *.pla *.ky *.pg
\trm -f *.vr *.tp *.fn *.fns *.def *.defs *.cp *.cps *.ge *.ges *.mo

.PHONY: all info plaintext html pdf install-info uninstall-info clean
'''


class TexinfoBuilder(Builder):
    """
    Builds Texinfo output to create Info documentation.
    """
    name = 'texinfo'
    format = 'texinfo'
    supported_image_types = ['image/png', 'image/jpeg',
                             'image/gif']

    def init(self):
        self.docnames = []
        self.document_data = []

    def get_outdated_docs(self):
        return 'all documents'  # for now

    def get_target_uri(self, docname, typ=None):
        if docname not in self.docnames:
            raise NoUri
        else:
            return '%' + docname

    def get_relative_uri(self, from_, to, typ=None):
        # ignore source path
        return self.get_target_uri(to, typ)

    def init_document_data(self):
        preliminary_document_data = [list(x) for x in self.config.texinfo_documents]
        if not preliminary_document_data:
            self.warn('no "texinfo_documents" config value found; no documents '
                      'will be written')
            return
        # assign subdirs to titles
        self.titles = []
        for entry in preliminary_document_data:
            docname = entry[0]
            if docname not in self.env.all_docs:
                self.warn('"texinfo_documents" config value references unknown '
                          'document %s' % docname)
                continue
            self.document_data.append(entry)
            if docname.endswith(SEP+'index'):
                docname = docname[:-5]
            self.titles.append((docname, entry[2]))

    def write(self, *ignored):
        self.init_document_data()
        for entry in self.document_data:
            docname, targetname, title, author = entry[:4]
            targetname += '.texi'
            direntry = description = category = ''
            if len(entry) > 6:
                direntry, description, category = entry[4:7]
            toctree_only = False
            if len(entry) > 7:
                toctree_only = entry[7]
            destination = FileOutput(
                destination_path=path.join(self.outdir, targetname),
                encoding='utf-8')
            self.info("processing " + targetname + "... ", nonl=1)
            doctree = self.assemble_doctree(
                docname, toctree_only,
                appendices=(self.config.texinfo_appendices or []))
            self.info("writing... ", nonl=1)
            self.post_process_images(doctree)
            docwriter = TexinfoWriter(self)
            settings = OptionParser(
                defaults=self.env.settings,
                components=(docwriter,),
                read_config_files=True).get_default_values()
            settings.author = author
            settings.title = title
            settings.texinfo_filename = targetname[:-5] + '.info'
            settings.texinfo_elements = self.config.texinfo_elements
            settings.texinfo_dir_entry = direntry or ''
            settings.texinfo_dir_category = category or ''
            settings.texinfo_dir_description = description or ''
            settings.docname = docname
            doctree.settings = settings
            docwriter.write(doctree, destination)
            self.info("done")

    def assemble_doctree(self, indexfile, toctree_only, appendices):
        self.docnames = set([indexfile] + appendices)
        self.info(darkgreen(indexfile) + " ", nonl=1)
        tree = self.env.get_doctree(indexfile)
        tree['docname'] = indexfile
        if toctree_only:
            # extract toctree nodes from the tree and put them in a
            # fresh document
            new_tree = new_document('<texinfo output>')
            new_sect = nodes.section()
            new_sect += nodes.title(u'<Set title in conf.py>',
                                    u'<Set title in conf.py>')
            new_tree += new_sect
            for node in tree.traverse(addnodes.toctree):
                new_sect += node
            tree = new_tree
        largetree = inline_all_toctrees(self, self.docnames, indexfile, tree,
                                        darkgreen, [indexfile])
        largetree['docname'] = indexfile
        for docname in appendices:
            appendix = self.env.get_doctree(docname)
            appendix['docname'] = docname
            largetree.append(appendix)
        self.info()
        self.info("resolving references...")
        self.env.resolve_references(largetree, indexfile, self)
        # TODO: add support for external :ref:s
        for pendingnode in largetree.traverse(addnodes.pending_xref):
            docname = pendingnode['refdocname']
            sectname = pendingnode['refsectname']
            newnodes = [nodes.emphasis(sectname, sectname)]
            for subdir, title in self.titles:
                if docname.startswith(subdir):
                    newnodes.append(nodes.Text(_(' (in '), _(' (in ')))
                    newnodes.append(nodes.emphasis(title, title))
                    newnodes.append(nodes.Text(')', ')'))
                    break
            else:
                pass
            pendingnode.replace_self(newnodes)
        return largetree

    def finish(self):
        # copy image files
        if self.images:
            self.info(bold('copying images...'), nonl=1)
            for src, dest in iteritems(self.images):
                self.info(' '+src, nonl=1)
                copyfile(path.join(self.srcdir, src),
                         path.join(self.outdir, dest))
            self.info()

        self.info(bold('copying Texinfo support files... '), nonl=True)
        # copy Makefile
        fn = path.join(self.outdir, 'Makefile')
        self.info(fn, nonl=1)
        try:
            mkfile = open(fn, 'w')
            try:
                mkfile.write(TEXINFO_MAKEFILE)
            finally:
                mkfile.close()
        except (IOError, OSError) as err:
            self.warn("error writing file %s: %s" % (fn, err))
        self.info(' done')
