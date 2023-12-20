"""
This module implements the JsonRequest class which is a more convenient class
(than Request) to generate JSON Requests.

See documentation in docs/topics/request-response.rst
"""

import copy
import json
import warnings
from typing import Any, Optional, Tuple

from scrapy.http.request import Request


class JsonRequest(Request):
    attributes: Tuple[str, ...] = Request.attributes + ("dumps_kwargs",)

    def __init__(
        self, *args: Any, dumps_kwargs: Optional[dict] = None, **kwargs: Any
    ) -> None:
        dumps_kwargs = copy.deepcopy(dumps_kwargs) if dumps_kwargs is not None else {}
        dumps_kwargs.setdefault("sort_keys", True)
        self._dumps_kwargs = dumps_kwargs

        body_passed = kwargs.get("body", None) is not None
        data = kwargs.pop("data", None)
        data_passed = data is not None

        if body_passed and data_passed:
            warnings.warn("Both body and data passed. data will be ignored")
        elif not body_passed and data_passed:
            kwargs["body"] = self._dumps(data)
            if "method" not in kwargs:
                kwargs["method"] = "POST"

        super().__init__(*args, **kwargs)
        self.headers.setdefault("Content-Type", "application/json")
        self.headers.setdefault(
            "Accept", "application/json, text/javascript, */*; q=0.01"
        )

    @property
    def dumps_kwargs(self) -> dict:
        return self._dumps_kwargs

    def replace(self, *args: Any, **kwargs: Any) -> Request:
        body_passed = kwargs.get("body", None) is not None
        data = kwargs.pop("data", None)
        data_passed = data is not None

        if body_passed and data_passed:
            warnings.warn("Both body and data passed. data will be ignored")
        elif not body_passed and data_passed:
            kwargs["body"] = self._dumps(data)

        return super().replace(*args, **kwargs)

    def _dumps(self, data: dict) -> str:
        """Convert to JSON"""
        return json.dumps(data, **self._dumps_kwargs)
