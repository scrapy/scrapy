from doctest import ELLIPSIS, NORMALIZE_WHITESPACE
from pathlib import Path

from sybil import Sybil
from sybil.parsers.doctest import DocTestParser
from sybil.parsers.skip import skip

try:
    # >2.0.1
    from sybil.parsers.codeblock import PythonCodeBlockParser
except ImportError:
    from sybil.parsers.codeblock import CodeBlockParser as PythonCodeBlockParser

from scrapy.http.response.html import HtmlResponse


def load_response(url: str, filename: str) -> HtmlResponse:
    input_path = Path(__file__).parent / "_tests" / filename
    return HtmlResponse(url, body=input_path.read_bytes())


def setup(namespace):
    namespace["load_response"] = load_response


pytest_collect_file = Sybil(
    parsers=[
        DocTestParser(optionflags=ELLIPSIS | NORMALIZE_WHITESPACE),
        PythonCodeBlockParser(future_imports=["print_function"]),
        skip,
    ],
    pattern="*.rst",
    setup=setup,
).pytest()
