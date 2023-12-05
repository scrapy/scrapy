import re
import textwrap
from itertools import chain
from typing import Optional, Dict, Iterable, Pattern, List

from sybil import Document
from sybil.exceptions import LexingException
from sybil.region import Lexeme, Region
from sybil.typing import Lexer


class LexerCollection(List[Lexer]):

    def __call__(self, document: Document) -> Iterable[Region]:
        return chain(*(lexer(document) for lexer in self))


class BlockLexer:
    """
    This is a base class useful for any :any:`Lexer` that must handle block-style languages
    such as ReStructured Text or MarkDown.

    It yields a sequence of :class:`~sybil.Region` objects for each case where the
    ``start_pattern`` matches. A ``source`` :class:`~sybil.Lexeme` is created from the text between
    the end of the start pattern and the start of the end pattern.

    :param start_pattern:
        This is used to match the start of the block. Any named groups will be returned
        in the :attr:`~sybil.Region.lexemes` :class:`dict` of resulting
        :class:`~sybil.Region` objects. If a ``prefix`` named group forms
        part of the match, this will be template substituted into the ``end_pattern_template``
        before it is compiled.

    :param end_pattern_template:
        This is used to match the end of any block found by the ``start_pattern``.
        It is templated with any ``prefix`` group from the ``start_pattern`` :class:`~typing.Match`
        and ``len_prefix``, the length of that prefix, before being compiled into a
        :class:`~typing.Pattern`.

    :param mapping:
        If provided, this is used to rename lexemes from the keys in the mapping to their values.
        Only mapped lexemes will be returned in any :class:`~sybil.Region` objects.
    """

    def __init__(
            self,
            start_pattern: Pattern[str],
            end_pattern_template: str,
            mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        self.start_pattern = start_pattern
        self.end_pattern_template = end_pattern_template
        self.mapping = mapping

    def __call__(self, document: Document) -> Iterable[Region]:
        for start_match in re.finditer(self.start_pattern, document.text):
            source_start = start_match.end()
            lexemes = start_match.groupdict()
            prefix = lexemes.pop('prefix', '')
            end_pattern = re.compile(self.end_pattern_template.format(
                prefix=prefix, len_prefix=len(prefix)
            ))
            end_match = end_pattern.search(document.text, source_start)
            if end_match is None:
                raise LexingException(
                    f'Could not match {end_pattern.pattern!r} in {document.path}:\n'
                    f'{document.text[source_start:]!r}'
                )
            source_end = end_match.start()
            source = document.text[source_start:source_end]
            lines = source.splitlines(keepends=True)
            stripped = ''.join(line[len(prefix):] for line in lines)
            lexemes['source'] = Lexeme(
                textwrap.dedent(stripped),
                offset=source_start-start_match.start(),
                line_offset=start_match.group(0).count('\n')-1
            )
            if self.mapping:
                lexemes = {dest: lexemes[source] for source, dest in self.mapping.items()}
            yield Region(start_match.start(), source_end, lexemes=lexemes)
