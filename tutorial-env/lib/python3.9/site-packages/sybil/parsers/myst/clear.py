import re

from sybil.parsers.abstract import AbstractClearNamespaceParser
from .lexers import DirectiveInPercentCommentLexer
from ..markdown.lexers import DirectiveInHTMLCommentLexer


class ClearNamespaceParser(AbstractClearNamespaceParser):
    """
    A :any:`Parser` for :ref:`clear-namespace <myst-clear-namespace>` instructions.
    """

    def __init__(self) -> None:
        super().__init__([
            DirectiveInPercentCommentLexer('clear-namespace'),
            DirectiveInHTMLCommentLexer('clear-namespace'),
        ])
