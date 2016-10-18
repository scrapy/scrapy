# -*- coding: utf-8 -*-
"""
    sphinx.writers.xml
    ~~~~~~~~~~~~~~~~~~

    Docutils-native XML and pseudo-XML writers.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from docutils import writers
from docutils.writers.docutils_xml import Writer as BaseXMLWriter


class XMLWriter(BaseXMLWriter):

    def __init__(self, builder):
        BaseXMLWriter.__init__(self)
        self.builder = builder
        if self.builder.translator_class:
            self.translator_class = self.builder.translator_class

    def translate(self, *args, **kwargs):
        self.document.settings.newlines = \
            self.document.settings.indents = \
            self.builder.env.config.xml_pretty
        self.document.settings.xml_declaration = True
        self.document.settings.doctype_declaration = True
        return BaseXMLWriter.translate(self)


class PseudoXMLWriter(writers.Writer):

    supported = ('pprint', 'pformat', 'pseudoxml')
    """Formats this writer supports."""

    config_section = 'pseudoxml writer'
    config_section_dependencies = ('writers',)

    output = None
    """Final translated form of `document`."""

    def __init__(self, builder):
        writers.Writer.__init__(self)
        self.builder = builder

    def translate(self):
        self.output = self.document.pformat()

    def supports(self, format):
        """This writer supports all format-specific elements."""
        return True
