# -*- coding: utf-8 -*-
"""
    sphinx.builders.text
    ~~~~~~~~~~~~~~~~~~~~

    Plain-text Sphinx builder.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import codecs
from os import path

from docutils.io import StringOutput

from sphinx.builders import Builder
from sphinx.util.osutil import ensuredir, os_path
from sphinx.writers.text import TextWriter


class TextBuilder(Builder):
    name = 'text'
    format = 'text'
    out_suffix = '.txt'
    allow_parallel = True

    def init(self):
        pass

    def get_outdated_docs(self):
        for docname in self.env.found_docs:
            if docname not in self.env.all_docs:
                yield docname
                continue
            targetname = self.env.doc2path(docname, self.outdir,
                                           self.out_suffix)
            try:
                targetmtime = path.getmtime(targetname)
            except Exception:
                targetmtime = 0
            try:
                srcmtime = path.getmtime(self.env.doc2path(docname))
                if srcmtime > targetmtime:
                    yield docname
            except EnvironmentError:
                # source doesn't exist anymore
                pass

    def get_target_uri(self, docname, typ=None):
        return ''

    def prepare_writing(self, docnames):
        self.writer = TextWriter(self)

    def write_doc(self, docname, doctree):
        self.current_docname = docname
        destination = StringOutput(encoding='utf-8')
        self.writer.write(doctree, destination)
        outfilename = path.join(self.outdir, os_path(docname) + self.out_suffix)
        ensuredir(path.dirname(outfilename))
        try:
            f = codecs.open(outfilename, 'w', 'utf-8')
            try:
                f.write(self.writer.output)
            finally:
                f.close()
        except (IOError, OSError) as err:
            self.warn("error writing file %s: %s" % (outfilename, err))

    def finish(self):
        pass
