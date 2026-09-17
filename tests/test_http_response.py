from __future__ import annotations

from scrapy.http import Response
from tests.utils.bases.http_response import TestResponseBase


class TestResponse(TestResponseBase):
    response_class = Response
