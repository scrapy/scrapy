import re

from sybil.parsers.abstract import AbstractClearNamespaceParser
from .lexers import DirectiveInCommentLexer


class ClearNamespaceParser(AbstractClearNamespaceParser):
    """
    A :any:`Parser` for :ref:`clear-namespace <clear-namespace>` instructions.
    """

    def __init__(self) -> None:
        super().__init__([DirectiveInCommentLexer('clear-namespace')])
