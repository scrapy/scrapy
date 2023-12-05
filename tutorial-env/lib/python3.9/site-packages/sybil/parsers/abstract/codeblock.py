from typing import Iterable, Sequence, Optional, Callable

from sybil import Region, Document, Example
from sybil.typing import Evaluator, Lexer, Parser
from .doctest import DocTestStringParser
from .lexers import LexerCollection
from ...evaluators.doctest import DocTestEvaluator
from ...evaluators.python import PythonEvaluator


class AbstractCodeBlockParser:
    """
    An abstract parser for use when evaluating blocks of code.

    :param lexers:
        A sequence of :any:`Lexer` objects that will be applied in turn to each
        :class:`~sybil.Document`
        that is parsed. The :class:`~sybil.Region` objects returned by these lexers must have
        both an ``arguments`` string, containing the language of the lexed region, and a
        ``source`` :class:`~sybil.Lexeme` containing the source code of the lexed region.

    :param language:
        The language that this parser should look for. Lexed regions which don't have this
        language in their ``arguments`` lexeme will be ignored.

    :param evaluator:
        The evaluator to use for evaluating code blocks in the specified language.
        You can also override the :meth:`evaluate` method below.
    """

    language: str

    def __init__(
            self,
            lexers: Sequence[Lexer],
            language: Optional[str] = None,
            evaluator: Optional[Evaluator] = None,
    ) -> None:
        self.lexers = LexerCollection(lexers)
        if language is not None:
            self.language = language
        assert self.language, 'language must be specified!'
        self._evaluator: Optional[Evaluator] = evaluator

    def evaluate(self, example: Example) -> Optional[str]:
        """
        The :any:`Evaluator` used for regions yields by this parser can be provided by
        implementing this method.
        """
        raise NotImplementedError

    def __call__(self, document: Document) -> Iterable[Region]:
        for region in self.lexers(document):
            if region.lexemes['arguments'] == self.language:
                region.parsed = region.lexemes['source']
                region.evaluator = self._evaluator or self.evaluate
                yield region


class PythonDocTestOrCodeBlockParser:

    codeblock_parser_class: Callable[[str, Evaluator], Parser]

    def __init__(self, future_imports: Sequence[str] = (), doctest_optionflags: int = 0) -> None:
        self.doctest_parser = DocTestStringParser(
            DocTestEvaluator(doctest_optionflags)
        )
        self.codeblock_parser = self.codeblock_parser_class(
            'python', PythonEvaluator(future_imports)
        )

    def __call__(self, document: Document) -> Iterable[Region]:
        for region in self.codeblock_parser(document):
            source = region.parsed
            if region.parsed.startswith('>>>'):
                for doctest_region in self.doctest_parser(source, document.path):
                    doctest_region.adjust(region, source)
                    yield doctest_region
            else:
                yield region
