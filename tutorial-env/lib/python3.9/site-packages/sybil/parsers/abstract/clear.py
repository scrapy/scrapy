from typing import Iterable, Sequence

from sybil import Document, Region, Example
from sybil.parsers.abstract.lexers import LexerCollection
from sybil.typing import Lexer


class AbstractClearNamespaceParser:
    """
    An abstract parser for clearing the :class:`~sybil.Document.namespace`.
    """

    def __init__(self, lexers: Sequence[Lexer]) -> None:
        self.lexers = LexerCollection(lexers)

    @staticmethod
    def evaluate(example: Example) -> None:
        example.document.namespace.clear()

    def __call__(self, document: Document) -> Iterable[Region]:
        for lexed in self.lexers(document):
            yield Region(lexed.start, lexed.end, lexed.lexemes['source'], self.evaluate)
