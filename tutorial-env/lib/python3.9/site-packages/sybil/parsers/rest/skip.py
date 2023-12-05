from ..abstract import AbstractSkipParser
from .lexers import DirectiveInCommentLexer


class SkipParser(AbstractSkipParser):
    """
    A :any:`Parser` for :ref:`skip <skip-parser>` instructions.
    """

    def __init__(self) -> None:
        super().__init__([DirectiveInCommentLexer('skip')])
