import warnings
from collections.abc import Iterable
from typing import Any, NamedTuple

import pytest

from scrapy.http.request import NO_CALLBACK, Request
from scrapy.http.request.form import FormRequest
from scrapy.http.request.json_request import JsonRequest
from scrapy.http.request.rpc import XmlRpcRequest

_attr_value_map: dict[str, Any] = {
    "url": "http://example.com/test",
    "callback": NO_CALLBACK,
    "method": "POST",
    "headers": {
        b"X-Test-Header": [b"1"],
        # `JsonRequest` will eventually add those even if they are not present
        b"Accept": [b"application/json, text/javascript, */*; q=0.01"],
        b"Content-Type": [b"application/json"],
    },
    "body": b"hello",
    "cookies": {"a": "1"},
    "meta": {"k": "v"},
    "encoding": "koi8-r",
    "priority": 5,
    "dont_filter": True,
    "errback": NO_CALLBACK,
    "flags": ["f1", "f2"],
    "cb_kwargs": {"x": 1},
    "dumps_kwargs": {"sort_keys": True, "default": str},
}


def _assert_equal_attribute(obj: Request, attr: str, expected: Any):
    val = getattr(obj, attr)
    if attr == "headers":
        # Headers object -> dict
        assert dict(val) == dict(expected)
    else:
        assert val == expected


class _ReqAttrTestCase(NamedTuple):
    request_class: type[Request]
    attribute_name: str


def _generate_test_cases() -> Iterable[_ReqAttrTestCase]:
    for request_class in (Request, JsonRequest, FormRequest, XmlRpcRequest):
        for attr in request_class.attributes:
            case = _ReqAttrTestCase(request_class, attr)
            if attr in _attr_value_map:
                yield case
            else:
                warnings.warn(f"Unhandled case: {case}", UserWarning)


@pytest.mark.parametrize("req_attr_test_case", _generate_test_cases(), ids=repr)
def test_attribute_setattr_and_replace_behavior(req_attr_test_case: _ReqAttrTestCase):
    """Ensure current assignment and replace semantics for Request.attributes.

    - If setattr(obj, attr, val) works today, it must keep working and
      replace() should carry the value over.
    - If setattr(obj, attr, val) raises AttributeError today (read-only),
      replace(**{attr: val}) should still allow creating a Request with that attr.
    """
    request_class, attr = req_attr_test_case

    r = request_class("http://example.com/")

    val = _attr_value_map[attr]

    # first try direct setattr
    try:
        setattr(r, attr, val)
    except AttributeError:
        # attribute is read-only
        # ensure replace(**{attr: val}) creates a new request with that value
        r2 = r.replace(**{attr: val})
        _assert_equal_attribute(r2, attr, val)
        # original request must remain unchanged (unless replace mutated it)
        # (for read-only attributes we expect original not to equal val)
        if getattr(r, attr) == val:
            pytest.fail(
                f"Attribute {attr} unexpectedly mutated original Request when "
                f"it should have been read-only (direct setattr raised)."
            )
    else:
        # direct setattr succeeded; attribute must reflect assigned value
        _assert_equal_attribute(r, attr, val)

        # and replace() must preserve it (replace uses getattr(self, x))
        r2 = r.replace()
        _assert_equal_attribute(r2, attr, getattr(r, attr))
