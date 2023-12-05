import re
from typing import Optional, Dict, Iterable

from sybil import Document, Region
from sybil.parsers.abstract.lexers import BlockLexer
from sybil.parsers.markdown.lexers import CODEBLOCK_END_TEMPLATE
from sybil.parsers.rest.lexers import parse_options_and_source

DIRECTIVE_START_TEMPLATE = (
    r"^(?P<prefix>[ \t]*)```\{{(?P<directive>{directive})}} ?(?P<arguments>{arguments})$\n"
    r'(?P<options>(?:\1[ \t]*:[\w-]*:[^\n]*\n)+)?'
    r"(\1---\n(?P<yaml_options>(?:.+\n)*)\1---\n)?"
)


def parse_yaml_options(lexed: Region) -> None:
    lexemes = lexed.lexemes
    yaml_options = lexemes.pop('yaml_options', None)
    if yaml_options is not None:
        # import here to avoid a dependency on PyYAML except where it's really needed:
        from yaml import safe_load
        options = safe_load(yaml_options)
        lexemes['options'].update(options)


class DirectiveLexer(BlockLexer):
    """
    A :class:`~sybil.parsers.abstract.lexers.BlockLexer` for MyST directives such as:

    .. code-block:: markdown

        ```{directivename} arguments
        ---
        key1: val1
        key2: val2
        ---
        This is
        directive content
        ```

    The following lexemes are extracted:

    - ``directive`` as a  :class:`str`.
    - ``arguments`` as a :class:`str`.
    - ``source`` as a :class:`~sybil.Lexeme`.

    :param directive:
        a :class:`str` containing a regular expression pattern to match directive names.

    :param arguments:
        a :class:`str` containing a regular expression pattern to match directive arguments.

    :param mapping:
        If provided, this is used to rename lexemes from the keys in the mapping to their
        values. Only mapped lexemes will be returned in any :class:`~sybil.Region` objects.

    """

    def __init__(
            self, directive: str, arguments: str = '.*', mapping: Optional[Dict[str, str]] = None
    ) -> None:
        super().__init__(
            start_pattern=re.compile(
                DIRECTIVE_START_TEMPLATE.format(directive=directive, arguments=arguments),
                re.MULTILINE
            ),
            end_pattern_template=CODEBLOCK_END_TEMPLATE,
            mapping=mapping,
        )

    def __call__(self, document: Document) -> Iterable[Region]:
        for lexed in super().__call__(document):
            parse_options_and_source(lexed)
            parse_yaml_options(lexed)
            yield lexed


DIRECTIVE_IN_PERCENT_COMMENT_START = (
    r"^(?P<prefix>[ \t]*%)[ \t]*(?P<directive>{directive})(:[ \t]*(?P<arguments>{arguments}))?$\n"
)
DIRECTIVE_IN_PERCENT_COMMENT_END = '(?<=\n)(?!{prefix})'


class DirectiveInPercentCommentLexer(BlockLexer):
    """
    A :class:`~sybil.parsers.abstract.lexers.BlockLexer` for faux MyST directives in
    %-style Markdown comments such as:

    .. code-block:: markdown

        % not-really-a-directive: some-argument
        %
        %     Source here...

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

    def __init__(
            self, directive: str, arguments: str = '.*', mapping: Optional[Dict[str, str]] = None
    ) -> None:
        super().__init__(
            start_pattern=re.compile(
                DIRECTIVE_IN_PERCENT_COMMENT_START.format(directive=directive, arguments=arguments),
                re.MULTILINE
            ),
            end_pattern_template=DIRECTIVE_IN_PERCENT_COMMENT_END,
            mapping=mapping,
        )


