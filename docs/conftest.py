import os
from doctest import ELLIPSIS, NORMALIZE_WHITESPACE

from scrapy.http.response.html import HtmlResponse
from sybil import Sybil
try:
    # >2.0.1
    from sybil.parsers.codeblock import PythonCodeBlockParser
except ImportError:
    from sybil.parsers.codeblock import CodeBlockParser as PythonCodeBlockParser
from sybil.parsers.doctest import DocTestParser
from sybil.parsers.skip import skip


def load_response(url, filename):
    input_path = os.path.join(os.path.dirname(__file__), '_tests', filename)
    with open(input_path, 'rb') as input_file:
        return HtmlResponse(url, body=input_file.read())


def setup(namespace):
    namespace['load_response'] = load_response


pytest_collect_file = Sybil(
    parsers=[
        DocTestParser(optionflags=ELLIPSIS | NORMALIZE_WHITESPACE),
        PythonCodeBlockParser(future_imports=['print_function']),
        skip,
    ],
    pattern='*.rst',
    setup=setup,
).pytest()
