from doctest import (
    DocTest as BaseDocTest,
    DocTestRunner as BaseDocTestRunner,
    Example as BaseDocTestExample,
    set_unittest_reportflags,
)
from typing import Any, Dict, List, Optional

from sybil import Example


class DocTest(BaseDocTest):
    def __init__(
            self,
            examples: List[BaseDocTestExample],
            globs: Dict[str, Any],
            name: str,
            filename: Optional[str],
            lineno: Optional[int],
            docstring: Optional[str],
        ) -> None:
        # do everything like regular doctests, but don't make a copy of globs
        BaseDocTest.__init__(self, examples, globs, name, filename, lineno, docstring)
        self.globs = globs


class DocTestRunner(BaseDocTestRunner):

    def __init__(self, optionflags: int) -> None:
        _unittest_reportflags = set_unittest_reportflags(0)
        set_unittest_reportflags(_unittest_reportflags)
        optionflags |= _unittest_reportflags
        BaseDocTestRunner.__init__(

            self,
            verbose=False,
            optionflags=optionflags,
        )

    def _failure_header(self, test: DocTest, example: BaseDocTestExample) -> str:
        return ''


class DocTestEvaluator:
    """
    The :any:`Evaluator` to use for :class:`Regions <sybil.Region>` yielded by
    a :class:`~sybil.parsers.abstract.doctest.DocTestStringParser`.


    :param optionflags:
        :ref:`doctest option flags<option-flags-and-directives>` to use
        when evaluating examples.
    """

    def __init__(self, optionflags: int = 0) -> None:
        self.runner = DocTestRunner(optionflags)

    def __call__(self, sybil_example: Example) -> str:
        example = sybil_example.parsed
        namespace = sybil_example.namespace
        output: List[str] = []
        remove_name = False
        try:
            if '__name__' not in namespace:
                remove_name = True
                namespace['__name__'] = '__test__'
            self.runner.run(
                DocTest([example], namespace, name=sybil_example.path,
                        filename=None, lineno=example.lineno, docstring=None),
                clear_globs=False,
                out=output.append
            )
        finally:
            if remove_name:
                del namespace['__name__']
        return ''.join(output)
