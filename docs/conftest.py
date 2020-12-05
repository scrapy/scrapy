from doctest import ELLIPSIS, NORMALIZE_WHITESPACE
from pathlib import Path

from scrapy.http.response.html import HtmlResponse
from sybil import Sybil
from sybil.parsers.codeblock import CodeBlockParser
from sybil.parsers.doctest import DocTestParser
from sybil.parsers.skip import skip


def load_response(url, filename):
    input_path = Path(__file__).resolve().parent / '_tests' / filename
    return HtmlResponse(url, body=input_path.read_bytes())


def setup(namespace):
    namespace['load_response'] = load_response


pytest_collect_file = Sybil(
    parsers=[
        DocTestParser(optionflags=ELLIPSIS | NORMALIZE_WHITESPACE),
        CodeBlockParser(future_imports=['print_function']),
        skip,
    ],
    pattern='*.rst',
    setup=setup,
).pytest()
