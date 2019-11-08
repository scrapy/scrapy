from doctest import ELLIPSIS

from sybil import Sybil
from sybil.parsers.codeblock import CodeBlockParser
from sybil.parsers.doctest import DocTestParser
from sybil.parsers.skip import skip


pytest_collect_file = Sybil(
    parsers=[
        DocTestParser(optionflags=ELLIPSIS),
        CodeBlockParser(future_imports=['print_function']),
        skip,
    ],
    pattern='*.rst',
).pytest()
