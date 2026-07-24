from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from itemadapter import ItemAdapter, is_item

from scrapy.contracts import Contract
from scrapy.exceptions import ContractFail
from scrapy.http import Request

if TYPE_CHECKING:
    from collections.abc import Callable


# contracts
class UrlContract(Contract):
    """Sets (``@url``) the sample URL used when checking the other contract
    conditions of a callback.

    This contract is mandatory: callbacks lacking it are ignored when running
    the checks.

    .. code-block:: none

        @url url
    """

    name = "url"

    def adjust_request_args(self, args: dict[str, Any]) -> dict[str, Any]:
        args["url"] = self.args[0]
        return args


class CallbackKeywordArgumentsContract(Contract):
    """Sets (``@cb_kwargs``) the :attr:`cb_kwargs <scrapy.Request.cb_kwargs>`
    attribute of the sample request.

    Its value must be a valid JSON dictionary.

    .. code-block:: none

        @cb_kwargs {"arg1": "value1", "arg2": "value2", ...}
    """

    name = "cb_kwargs"

    def adjust_request_args(self, args: dict[str, Any]) -> dict[str, Any]:
        args["cb_kwargs"] = json.loads(" ".join(self.args))
        return args


class MetadataContract(Contract):
    """Sets (``@meta``) the :attr:`meta <scrapy.Request.meta>` attribute of the
    sample request.

    Its value must be a valid JSON dictionary.

    .. code-block:: none

        @meta {"arg1": "value1", "arg2": "value2", ...}
    """

    name = "meta"

    def adjust_request_args(self, args: dict[str, Any]) -> dict[str, Any]:
        args["meta"] = json.loads(" ".join(self.args))
        return args


class ReturnsContract(Contract):
    """Sets (``@returns``) lower and upper bounds for the items and requests
    returned by a callback.

    The upper bound is optional:

    .. code-block:: none

        @returns item(s)|request(s) [min [max]]

    For example:

    .. code-block:: none

        @returns request
        @returns request 2
        @returns request 2 10
        @returns request 0 10

    Set both bounds to the same value to require an exact number:

    .. code-block:: none

        @returns request 2 2
    """

    name = "returns"
    object_type_verifiers: ClassVar[dict[str | None, Callable[[Any], bool]]] = {
        "request": lambda x: isinstance(x, Request),
        "requests": lambda x: isinstance(x, Request),
        "item": is_item,
        "items": is_item,
    }

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        if len(self.args) not in {1, 2, 3}:
            raise ValueError(
                f"Incorrect argument quantity: expected 1, 2 or 3, got {len(self.args)}"
            )
        self.obj_name = self.args[0] or None
        self.obj_type_verifier = self.object_type_verifiers[self.obj_name]

        try:
            self.min_bound: float = int(self.args[1])
        except IndexError:
            self.min_bound = 1

        try:
            self.max_bound: float = int(self.args[2])
        except IndexError:
            self.max_bound = float("inf")

    def post_process(self, output: list[Any]) -> None:
        occurrences = 0
        for x in output:
            if self.obj_type_verifier(x):
                occurrences += 1

        assertion = self.min_bound <= occurrences <= self.max_bound

        if not assertion:
            if self.min_bound == self.max_bound:
                expected = str(self.min_bound)
            else:
                expected = f"{self.min_bound}..{self.max_bound}"

            raise ContractFail(
                f"Returned {occurrences} {self.obj_name}, expected {expected}"
            )


class ScrapesContract(Contract):
    """Checks (``@scrapes``) that all items returned by a callback have the
    specified fields.

    .. code-block:: none

        @scrapes field_1 field_2 ...
    """

    name = "scrapes"

    def post_process(self, output: list[Any]) -> None:
        for x in output:
            if is_item(x):
                missing = [arg for arg in self.args if arg not in ItemAdapter(x)]
                if missing:
                    missing_fields = ", ".join(missing)
                    raise ContractFail(f"Missing fields: {missing_fields}")
