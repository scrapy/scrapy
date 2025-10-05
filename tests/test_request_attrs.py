from typing import Any

import pytest

from scrapy.http.request import NO_CALLBACK, Request
from scrapy.http.request.form import FormRequest
from scrapy.http.request.json_request import JsonRequest

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
}


def _assert_equal_attribute(obj: Request, attr: str, expected: Any):
    val = getattr(obj, attr)
    if attr == "headers":
        # Headers object -> dict
        assert dict(val) == dict(expected)
    elif attr == "body":
        # body should be bytes
        assert val == expected
    else:
        assert val == expected


@pytest.mark.parametrize("request_class", [Request, JsonRequest, FormRequest])
@pytest.mark.parametrize("attr", Request.attributes)
def test_attribute_setattr_and_replace_behavior(
    request_class: type[Request], attr: str
):
    """Ensure current assignment and replace semantics for Request.attributes.

    - If setattr(obj, attr, val) works today, it must keep working and
      replace() should carry the value over.
    - If setattr(obj, attr, val) raises AttributeError today (read-only),
      replace(**{attr: val}) should still allow creating a Request with that attr.
    """
    r = request_class("http://example.com/")

    if attr not in _attr_value_map:
        return

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
