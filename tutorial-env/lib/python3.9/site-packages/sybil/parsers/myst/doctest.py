from typing import Iterable

from sybil import Document, Region
from sybil.evaluators.doctest import DocTestEvaluator
from sybil.parsers.abstract import DocTestStringParser
from .lexers import DirectiveLexer


class DocTestDirectiveParser:
    """
    A :any:`Parser` for :ref:`doctest directive <myst-doctest-parser>` examples.

    :param optionflags:
        :ref:`doctest option flags<option-flags-and-directives>` to use
        when evaluating the examples found by this parser.

    """
    def __init__(self, optionflags: int = 0) -> None:
        self.lexer = DirectiveLexer('doctest')
        self.string_parser = DocTestStringParser(DocTestEvaluator(optionflags))

    def __call__(self, document: Document) -> Iterable[Region]:
        for lexed_region in self.lexer(document):
            source = lexed_region.lexemes['source']
            for region in self.string_parser(source, document.path):
                region.adjust(lexed_region, source)
                yield region

