from __future__ import annotations

import pickle
import sys
from typing import TYPE_CHECKING, Any, cast

import pytest

from scrapy.http import Request
from scrapy.item import Field, Item
from scrapy.loader import ItemLoader
from scrapy.selector import Selector
from scrapy.squeues import (
    _MarshalFifoSerializationDiskQueue,
    _MarshalFifoSerializationSQLiteQueue,
    _MarshalLifoSerializationDiskQueue,
    _MarshalLifoSerializationSQLiteQueue,
    _PickleFifoSerializationDiskQueue,
    _PickleFifoSerializationSQLiteQueue,
    _PickleLifoSerializationDiskQueue,
    _PickleLifoSerializationSQLiteQueue,
    _scrapy_non_serialization_queue,
    _serializable_queue,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

_PICKLE_QUEUES = [
    pytest.param(_PickleFifoSerializationDiskQueue, id="pickle-fifo-disk"),
    pytest.param(_PickleLifoSerializationDiskQueue, id="pickle-lifo-disk"),
    pytest.param(_PickleFifoSerializationSQLiteQueue, id="pickle-fifo-sqlite"),
    pytest.param(_PickleLifoSerializationSQLiteQueue, id="pickle-lifo-sqlite"),
]
_QUEUES = [
    *_PICKLE_QUEUES,
    pytest.param(_MarshalFifoSerializationDiskQueue, id="marshal-fifo-disk"),
    pytest.param(_MarshalLifoSerializationDiskQueue, id="marshal-lifo-disk"),
    pytest.param(_MarshalFifoSerializationSQLiteQueue, id="marshal-fifo-sqlite"),
    pytest.param(_MarshalLifoSerializationSQLiteQueue, id="marshal-lifo-sqlite"),
]


@pytest.fixture
def q(queue_cls: Any, tmp_path: Path) -> Generator[Any]:
    queue = queue_cls(str(tmp_path / "queue"))
    try:
        yield queue
    finally:
        queue.close()


class MyItem(Item):
    name = Field()


class NoPeekQueue:
    """Queue class without the optional peek method."""


_no_peek_queue = cast("Any", NoPeekQueue)


@pytest.mark.parametrize(
    "queue_class",
    [
        _serializable_queue(_no_peek_queue, pickle.dumps, pickle.loads),
        _scrapy_non_serialization_queue(_no_peek_queue),
    ],
)
def test_peek_unsupported(queue_class):
    with pytest.raises(
        NotImplementedError,
        match="The underlying queue class does not implement 'peek'",
    ):
        queue_class().peek()


def _test_procesor(x):
    return x + x


class MyLoader(ItemLoader):
    default_item_class = MyItem
    name_out = staticmethod(_test_procesor)


@pytest.mark.parametrize("queue_cls", _QUEUES)
def test_serialize(q: Any) -> None:
    for value in ["a", 123, {"a": "dict"}]:
        q.push(value)
        assert q.pop() == value


@pytest.mark.parametrize("queue_cls", _QUEUES)
def test_nonserializable_object(q: Any) -> None:
    with pytest.raises(
        ValueError,
        match=r"unmarshallable object|Can't (get|pickle) local object|Can't pickle .*: it's not found as",
    ):
        q.push(lambda x: x)
    # Selectors should fail (lxml.html.HtmlElement objects can't be pickled)
    sel = Selector(text="<html><body><p>some text</p></body></html>")
    with pytest.raises(
        ValueError, match=r"unmarshallable object|can't pickle Selector objects"
    ):
        q.push(sel)


@pytest.mark.parametrize("queue_cls", _PICKLE_QUEUES)
def test_serialize_item(q: Any) -> None:
    i = MyItem(name="foo")
    q.push(i)
    i2 = q.pop()
    assert isinstance(i2, MyItem)
    assert i == i2


@pytest.mark.parametrize("queue_cls", _PICKLE_QUEUES)
def test_serialize_loader(q: Any) -> None:
    loader = MyLoader()
    q.push(loader)
    loader2 = q.pop()
    assert isinstance(loader2, MyLoader)
    assert loader2.default_item_class is MyItem
    assert loader2.name_out("x") == "xx"


@pytest.mark.parametrize("queue_cls", _PICKLE_QUEUES)
def test_serialize_request_recursive(q: Any) -> None:
    r = Request("http://www.example.com")
    r.meta["request"] = r
    q.push(r)
    r2 = q.pop()
    assert isinstance(r2, Request)
    assert r.url == r2.url
    assert r2.meta["request"] is r2


@pytest.mark.parametrize("queue_cls", _PICKLE_QUEUES)
def test_non_pickable_object(q: Any) -> None:
    with pytest.raises(
        ValueError,
        match=r"Can't (get|pickle) local object|Can't pickle .*: it's not found as",
    ) as exc_info:
        q.push(lambda x: x)
    if sys.version_info >= (3, 14):
        assert isinstance(exc_info.value.__context__, pickle.PicklingError)
    else:
        assert isinstance(exc_info.value.__context__, AttributeError)
    sel = Selector(text="<html><body><p>some text</p></body></html>")
    with pytest.raises(ValueError, match="can't pickle Selector objects") as exc_info:
        q.push(sel)
    assert isinstance(exc_info.value.__context__, TypeError)
