# -*- coding: utf-8 -*-
"""
    sphinx.io
    ~~~~~~~~~

    Input/Output files

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""
from docutils.io import FileInput
from docutils.readers import standalone
from docutils.writers import UnfilteredWriter
from six import string_types, text_type

from sphinx.transforms import ApplySourceWorkaround, ExtraTranslatableNodes, Locale, \
    CitationReferences, DefaultSubstitutions, MoveModuleTargets, HandleCodeBlocks, \
    AutoNumbering, AutoIndexUpgrader, SortIds, RemoveTranslatableInline
from sphinx.util import import_object, split_docinfo


class SphinxBaseReader(standalone.Reader):
    """
    Add our source parsers
    """
    def __init__(self, app, parsers={}, *args, **kwargs):
        standalone.Reader.__init__(self, *args, **kwargs)
        self.parser_map = {}
        for suffix, parser_class in parsers.items():
            if isinstance(parser_class, string_types):
                parser_class = import_object(parser_class, 'source parser')
            parser = parser_class()
            if hasattr(parser, 'set_application'):
                parser.set_application(app)
            self.parser_map[suffix] = parser

    def read(self, source, parser, settings):
        self.source = source

        for suffix in self.parser_map:
            if source.source_path.endswith(suffix):
                self.parser = self.parser_map[suffix]
                break

        if not self.parser:
            self.parser = parser
        self.settings = settings
        self.input = self.source.read()
        self.parse()
        return self.document

    def get_transforms(self):
        return standalone.Reader.get_transforms(self) + self.transforms


class SphinxStandaloneReader(SphinxBaseReader):
    """
    Add our own transforms.
    """
    transforms = [ApplySourceWorkaround, ExtraTranslatableNodes, Locale, CitationReferences,
                  DefaultSubstitutions, MoveModuleTargets, HandleCodeBlocks,
                  AutoNumbering, AutoIndexUpgrader, SortIds, RemoveTranslatableInline]


class SphinxI18nReader(SphinxBaseReader):
    """
    Replacer for document.reporter.get_source_and_line method.

    reST text lines for translation do not have the original source line number.
    This class provides the correct line numbers when reporting.
    """

    transforms = [ApplySourceWorkaround, ExtraTranslatableNodes, CitationReferences,
                  DefaultSubstitutions, MoveModuleTargets, HandleCodeBlocks,
                  AutoNumbering, SortIds, RemoveTranslatableInline]

    def __init__(self, *args, **kwargs):
        SphinxBaseReader.__init__(self, *args, **kwargs)
        self.lineno = None

    def set_lineno_for_reporter(self, lineno):
        self.lineno = lineno

    def new_document(self):
        document = SphinxBaseReader.new_document(self)
        reporter = document.reporter

        def get_source_and_line(lineno=None):
            return reporter.source, self.lineno

        reporter.get_source_and_line = get_source_and_line
        return document


class SphinxDummyWriter(UnfilteredWriter):
    supported = ('html',)  # needed to keep "meta" nodes

    def translate(self):
        pass


class SphinxFileInput(FileInput):
    def __init__(self, app, env, *args, **kwds):
        self.app = app
        self.env = env
        kwds['error_handler'] = 'sphinx'  # py3: handle error on open.
        FileInput.__init__(self, *args, **kwds)

    def decode(self, data):
        if isinstance(data, text_type):  # py3: `data` already decoded.
            return data
        return data.decode(self.encoding, 'sphinx')  # py2: decoding

    def read(self):
        def get_parser_type(docname):
            path = self.env.doc2path(docname)
            for suffix in self.env.config.source_parsers:
                if path.endswith(suffix):
                    parser_class = self.env.config.source_parsers[suffix]
                    if isinstance(parser_class, string_types):
                        parser_class = import_object(parser_class, 'source parser')
                    return parser_class.supported
            else:
                return ('restructuredtext',)

        data = FileInput.read(self)
        if self.app:
            arg = [data]
            self.app.emit('source-read', self.env.docname, arg)
            data = arg[0]
        docinfo, data = split_docinfo(data)
        if 'restructuredtext' in get_parser_type(self.env.docname):
            if self.env.config.rst_epilog:
                data = data + '\n' + self.env.config.rst_epilog + '\n'
            if self.env.config.rst_prolog:
                data = self.env.config.rst_prolog + '\n' + data
        return docinfo + data
