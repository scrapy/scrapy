import re
from typing import Optional, Dict, Iterable

from sybil import Document, Region
from sybil.parsers.abstract.lexers import BlockLexer

START_PATTERN_TEMPLATE =(
    r'^(?P<prefix>[ \t]*)\.\.\s*(?P<directive>{directive})'
    r'{delimiter}[ \t]*'
    r'(?P<arguments>[^\n]+)?\n'
    r'(?P<options>(?:\1[ \t]+:[\w-]*:[^\n]*\n)+)?'
)

OPTIONS_PATTERN = re.compile(r'[^:]*:(?P<name>[^:]+):[ \t]*(?P<value>[^\n]*)\n')
END_PATTERN_TEMPLATE = r'((?<=\n)(?=\.\.)|\n?\Z|\n[ \t]{{0,{len_prefix}}}(?=\S|\Z))'


def parse_options_and_source(lexed: Region) -> None:
    lexemes = lexed.lexemes
    raw_options = lexemes.pop('options', None)
    options = lexemes['options'] = {}
    if raw_options:
        for match in OPTIONS_PATTERN.finditer(raw_options):
            options[match['name']] = match['value']
    source = lexemes.get('source')
    if source:
        lexemes['source'] = source.strip_leading_newlines()


class DirectiveLexer(BlockLexer):
    """
    A :class:`~sybil.parsers.abstract.lexers.BlockLexer` for ReST directives that extracts the
    following lexemes:

    - ``directive`` as a  :class:`str`.
    - ``arguments`` as a :class:`str`.
    - ``source`` as a :class:`~sybil.Lexeme`.

    :param directive:
        a :class:`str` containing a regular expression pattern to match directive names.

    :param arguments:
        a :class:`str` containing a regular expression pattern to match directive arguments.

    :param mapping:
        If provided, this is used to rename lexemes from the keys in the mapping to their values.
        Only mapped lexemes will be returned in any :class:`~sybil.Region` objects.
    """

    delimiter = '::'

    def __init__(
            self,
            directive: str,
            arguments: str = '',
            mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        A lexer for ReST directives.
        Both ``directive`` and ``arguments`` are regex patterns.
        """
        super().__init__(
            start_pattern=re.compile(
                START_PATTERN_TEMPLATE.format(
                    directive=directive,
                    delimiter=self.delimiter,
                    arguments=arguments
                ),
                re.MULTILINE
            ),
            end_pattern_template=END_PATTERN_TEMPLATE,
            mapping=mapping,
        )

    def __call__(self, document: Document) -> Iterable[Region]:
        for lexed in super().__call__(document):
            parse_options_and_source(lexed)
            yield lexed


class DirectiveInCommentLexer(DirectiveLexer):
    """
    A :class:`~sybil.parsers.abstract.lexers.BlockLexer` for faux ReST directives in comments
    such as:

    .. code-block:: rest

        .. not-really-a-directive: some-argument

          Source here...

    It extracts the following lexemes:

    - ``directive`` as a  :class:`str`.
    - ``arguments`` as a :class:`str`.
    - ``source`` as a :class:`~sybil.Lexeme`.

    :param directive:
        a :class:`str` containing a regular expression pattern to match directive names.

    :param arguments:
        a :class:`str` containing a regular expression pattern to match directive arguments.

    :param mapping:
        If provided, this is used to rename lexemes from the keys in the mapping to their values.
        Only mapped lexemes will be returned in any :class:`~sybil.Region` objects.
    """

    # This is the pattern used for invisible code blocks and the like.
    delimiter = ':?'
