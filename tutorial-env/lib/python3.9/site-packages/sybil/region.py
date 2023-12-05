from typing import Any, Union, Optional

from sybil.typing import Evaluator, LexemeMapping


class Lexeme(str):
    """
    Where needed, this can store both the text of the lexeme
    and it's line offset relative to the line number of the example
    that contains it.
    """

    def __new__(cls, text: str, offset: int, line_offset: int) -> 'Lexeme':
        return str.__new__(cls, text)

    def __init__(self, text: str, offset: int, line_offset: int) -> None:
        self.text, self.offset, self.line_offset = text, offset, line_offset

    def strip_leading_newlines(self) -> 'Lexeme':
        stripped = self.lstrip('\n')
        removed = len(self) - len(stripped)
        return Lexeme(stripped, self.offset + removed, self.line_offset + removed)


MAX_REPR_PART_LENGTH = 40
CONTRACTED = '...'


class Region:
    """
    Parsers should yield instances of this class for each example they
    discover in a documentation source file.
    
    :param start: 
        The character position at which the example starts in the
        :class:`~sybil.document.Document`.
    
    :param end: 
        The character position at which the example ends in the
        :class:`~sybil.document.Document`.
    
    :param parsed: 
        The parsed version of the example.
    
    :param evaluator: 
        The callable to use to evaluate this example and check if it is
        as it should be.
    """

    def __init__(
            self,
            start: int,
            end: int,
            parsed: Any = None,
            evaluator: Optional[Evaluator] = None,
            lexemes: Optional[LexemeMapping] = None,
    ) -> None:
        #: The start of this region within the document's :attr:`~sybil.Document.text`.
        self.start: int = start
        #: The end of this region within the document's :attr:`~sybil.Document.text`.
        self.end: int = end
        #: The parsed version of this region. This only needs to have meaning to
        #: the :attr:`evaluator`.
        self.parsed: Any = parsed
        #: The :any:`Evaluator` for this region.
        self.evaluator: Optional[Evaluator] = evaluator
        #: The lexemes extracted from the region.
        self.lexemes: LexemeMapping = lexemes or {}

    @staticmethod
    def trim(text: str) -> str:
        if len(text) > MAX_REPR_PART_LENGTH:
            half = int((MAX_REPR_PART_LENGTH + len(CONTRACTED)) / 2)
            text = text[:half] + CONTRACTED + text[-half:]
        return text

    def __repr__(self) -> str:
        evaluator_text = f' evaluator={self.evaluator!r}' if self.evaluator else ''
        text = f'<Region start={self.start} end={self.end}{evaluator_text}>'
        if self.lexemes:
            text += '\n'
        for name, lexeme in self.lexemes.items():
            if isinstance(lexeme, str):
                lexeme = self.trim(lexeme)
            text += f'{name}: {lexeme!r}\n'
        if self.parsed:
            parsed_text = self.trim(repr(self.parsed))
            text += f'<Parsed>{parsed_text}</Parsed>'
        if self.parsed or self.lexemes:
            text += '</Region>'
        return text

    def __lt__(self, other: 'Region') -> bool:
        assert isinstance(other, type(self)), f"{type(other)} not supported for <"
        assert self.start == other.start  # This is where this may happen, if not something weird
        return True

    def adjust(self, lexed: Union['Region', 'Region'], lexeme: Lexeme) -> None:
        """
        Adjust the start and end of this region based on the provided :class:`Lexeme`
        and ::class:`Region` that lexeme came from.
        """
        self.start += (lexed.start + lexeme.offset)
        self.end += lexed.start
