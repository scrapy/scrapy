from ..abstract import AbstractSkipParser
from ..markdown.lexers import DirectiveInHTMLCommentLexer


class SkipParser(AbstractSkipParser):
    """
    A :any:`Parser` for :ref:`skip <markdown-skip-parser>` instructions.
    """

    def __init__(self) -> None:
        super().__init__([
            DirectiveInHTMLCommentLexer('skip'),
        ])
