"""
This module implements the JsonRequest class which is a more convenient class
(than Request) to generate JSON Requests.

See documentation in docs/topics/request-response.rst
"""

from __future__ import annotations

import copy
import json
import warnings
from typing import TYPE_CHECKING, Any, overload

from scrapy.http.request import Request, RequestTypeVar

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self


class JsonRequest(Request):
    attributes: tuple[str, ...] = Request.attributes + ("dumps_kwargs",)

    def __init__(
        self, *args: Any, dumps_kwargs: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        dumps_kwargs = copy.deepcopy(dumps_kwargs) if dumps_kwargs is not None else {}
        dumps_kwargs.setdefault("sort_keys", True)
        self._dumps_kwargs: dict[str, Any] = dumps_kwargs

        body_passed = kwargs.get("body", None) is not None
        data: Any = kwargs.pop("data", None)
        data_passed: bool = data is not None

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
    def dumps_kwargs(self) -> dict[str, Any]:
        return self._dumps_kwargs

    @overload
    def replace(
        self, *args: Any, cls: type[RequestTypeVar], **kwargs: Any
    ) -> RequestTypeVar: ...

    @overload
    def replace(self, *args: Any, cls: None = None, **kwargs: Any) -> Self: ...

    def replace(
        self, *args: Any, cls: type[Request] | None = None, **kwargs: Any
    ) -> Request:
        body_passed = kwargs.get("body", None) is not None
        data: Any = kwargs.pop("data", None)
        data_passed: bool = data is not None

        if body_passed and data_passed:
            warnings.warn("Both body and data passed. data will be ignored")
        elif not body_passed and data_passed:
            kwargs["body"] = self._dumps(data)

        return super().replace(*args, cls=cls, **kwargs)

    def _dumps(self, data: Any) -> str:
        """Convert to JSON"""
        return json.dumps(data, **self._dumps_kwargs)
