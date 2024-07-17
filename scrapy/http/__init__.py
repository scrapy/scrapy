"""
Module containing all HTTP related classes

Use this module (instead of the more specific ones) when importing Headers,
Request and Response outside this module.
"""

from warnings import catch_warnings, filterwarnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http.headers import Headers
from scrapy.http.request import Request
from scrapy.http.request.json_request import JsonRequest
from scrapy.http.request.rpc import XmlRpcRequest
from scrapy.http.response import Response
from scrapy.http.response.html import HtmlResponse
from scrapy.http.response.json import JsonResponse
from scrapy.http.response.text import TextResponse
from scrapy.http.response.xml import XmlResponse
from scrapy.utils.deprecate import create_deprecated_class

with catch_warnings():
    filterwarnings("ignore", category=ScrapyDeprecationWarning)

    from scrapy.http.request.form import FormRequest as _FormRequest

    FormRequest = create_deprecated_class(
        name="FormRequest",
        new_class=_FormRequest,
        subclass_warn_message="{cls} inherits from deprecated class {old}, use the form2request library instead.",
        instance_warn_message="{cls} is deprecated, use the form2request library instead.",
    )
