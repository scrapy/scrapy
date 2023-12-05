from sybil.parsers.abstract import AbstractClearNamespaceParser
from ..markdown.lexers import DirectiveInHTMLCommentLexer


class ClearNamespaceParser(AbstractClearNamespaceParser):
    """
    A :any:`Parser` for :ref:`clear-namespace <markdown-clear-namespace>` instructions.
    """

    def __init__(self) -> None:
        super().__init__([
            DirectiveInHTMLCommentLexer('clear-namespace'),
        ])
