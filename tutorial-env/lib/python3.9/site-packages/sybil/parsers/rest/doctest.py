from typing import Iterable

from sybil import Document, Region
from sybil.evaluators.doctest import DocTestEvaluator
from sybil.parsers.abstract import DocTestStringParser
from .lexers import DirectiveLexer


class DocTestParser:
    """
    A :any:`Parser` for :ref:`doctest-parser` examples.

    :param optionflags:
        :ref:`doctest option flags<option-flags-and-directives>` to use
        when evaluating the examples found by this parser.

    """
    def __init__(self, optionflags: int = 0) -> None:
        self.string_parser = DocTestStringParser(DocTestEvaluator(optionflags))

    def __call__(self, document: Document) -> Iterable[Region]:
        return self.string_parser(document.text, document.path)


class DocTestDirectiveParser:
    """
    A :any:`Parser` for :rst:dir:`doctest` directives.

    :param optionflags:
        :ref:`doctest option flags<option-flags-and-directives>` to use
        when evaluating the examples found by this parser.

    """

    def __init__(self, optionflags: int = 0) -> None:
        self.lexer = DirectiveLexer(directive='doctest')
        self.string_parser = DocTestStringParser(DocTestEvaluator(optionflags))

    def __call__(self, document: Document) -> Iterable[Region]:
        for lexed in self.lexer(document):
            source = lexed.lexemes['source']
            for doctest_region in self.string_parser(source, document.path):
                doctest_region.adjust(lexed, source)
                yield doctest_region
