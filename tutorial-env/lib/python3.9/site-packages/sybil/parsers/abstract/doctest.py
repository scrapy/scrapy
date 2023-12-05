from doctest import (
    DocTestParser as BaseDocTestParser,
    Example as DocTestExample,
)
from typing import Iterable

from sybil.evaluators.doctest import DocTestEvaluator
from sybil.region import Region


class DocTestStringParser(BaseDocTestParser):
    """
    This isn't a true :any:`Parser` in that it must be called with a :class:`str` containing
    the doctest example's source and the file name that the example came from.
    """

    def __init__(self, evaluator: DocTestEvaluator = DocTestEvaluator()) -> None:
        #: The evaluator to use for any doctests found in the supplied source string.
        self.evaluator: DocTestEvaluator = evaluator

    def __call__(self, string: str, name: str) -> Iterable[Region]:
        """
        This will yield :class:`sybil.Region` objects for any doctest examples found in
        the supplied ``string`` with the :attr:`evaluator` supplied to its constructor
        and the file ``name`` supplied.

        Each section starting with a ``>>>`` will form a separate region.
        """
        # a cut down version of doctest.DocTestParser.parse:
        charno, lineno = 0, 0
        # Find all doctest examples in the string:
        for m in self._EXAMPLE_RE.finditer(string):  # type: ignore
            # Update lineno (lines before this example)
            lineno += string.count('\n', charno, m.start())
            # Extract info from the regexp match.
            source, options, want, exc_msg = self._parse_example(m, name, lineno)  # type: ignore

            # Create an Example, and add it to the list.
            if not self._IS_BLANK_OR_COMMENT(source):  # type: ignore
                yield Region(
                    m.start(),
                    m.end(),
                    DocTestExample(source, want, exc_msg,
                                   lineno=lineno,
                                   indent=len(m.group('indent')),
                                   options=options),
                    self.evaluator

                )
            # Update lineno (lines inside this example)
            lineno += string.count('\n', m.start(), m.end())
            # Update charno.
            charno = m.end()


