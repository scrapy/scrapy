from typing import Optional

from sybil.parsers.abstract import AbstractCodeBlockParser
from sybil.typing import Evaluator
from ..abstract.codeblock import PythonDocTestOrCodeBlockParser
from ..markdown.lexers import FencedCodeBlockLexer, DirectiveInHTMLCommentLexer


class CodeBlockParser(AbstractCodeBlockParser):
    """
    A :any:`Parser` for :ref:`markdown-codeblock-parser` examples.

    :param language:
        The language that this parser should look for.

    :param evaluator:
        The evaluator to use for evaluating code blocks in the specified language.
        You can also override the :meth:`evaluate` method below.
    """

    def __init__(
            self, language: Optional[str] = None, evaluator: Optional[Evaluator] = None
    ) -> None:
        super().__init__(
            [
                FencedCodeBlockLexer(
                    language=r'.+',
                    mapping={'language': 'arguments', 'source': 'source'},
                ),
                DirectiveInHTMLCommentLexer(
                    directive=r'(invisible-)?code(-block)?',
                    arguments='.+',
                ),
            ],
            language, evaluator
        )


class PythonCodeBlockParser(PythonDocTestOrCodeBlockParser):
    """
    A :any:`Parser` for Python :ref:`markdown-codeblock-parser` examples.

    :param future_imports:
        An optional list of strings that will be turned into
        ``from __future__ import ...`` statements and prepended to the code
        in each of the examples found by this parser.

    :param doctest_optionflags:
        :ref:`doctest option flags<option-flags-and-directives>` to use
        when evaluating the doctest examples found by this parser.
    """

    codeblock_parser_class = CodeBlockParser
