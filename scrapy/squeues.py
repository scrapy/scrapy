"""
Scheduler queues
"""

from __future__ import annotations

import marshal
import pickle  # nosec
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, Type, Union

from queuelib import queue

from scrapy import Request
from scrapy.crawler import Crawler
from scrapy.utils.request import request_from_dict

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self


def _with_mkdir(queue_class: Type[queue.BaseQueue]) -> Type[queue.BaseQueue]:
    class DirectoriesCreated(queue_class):  # type: ignore[valid-type,misc]
        def __init__(self, path: Union[str, PathLike], *args: Any, **kwargs: Any):
            dirname = Path(path).parent
            if not dirname.exists():
                dirname.mkdir(parents=True, exist_ok=True)
            super().__init__(path, *args, **kwargs)

    return DirectoriesCreated


def _serializable_queue(
    queue_class: Type[queue.BaseQueue],
    serialize: Callable[[Any], bytes],
    deserialize: Callable[[bytes], Any],
) -> Type[queue.BaseQueue]:
    class SerializableQueue(queue_class):  # type: ignore[valid-type,misc]
        def push(self, obj: Any) -> None:
            s = serialize(obj)
            super().push(s)

        def pop(self) -> Optional[Any]:
            s = super().pop()
            if s:
                return deserialize(s)
            return None

        def peek(self) -> Optional[Any]:
            """Returns the next object to be returned by :meth:`pop`,
            but without removing it from the queue.

            Raises :exc:`NotImplementedError` if the underlying queue class does
            not implement a ``peek`` method, which is optional for queues.
            """
            try:
                s = super().peek()
            except AttributeError as ex:
                raise NotImplementedError(
                    "The underlying queue class does not implement 'peek'"
                ) from ex
            if s:
                return deserialize(s)
            return None

    return SerializableQueue


def _scrapy_serialization_queue(
    queue_class: Type[queue.BaseQueue],
) -> Type[queue.BaseQueue]:
    class ScrapyRequestQueue(queue_class):  # type: ignore[valid-type,misc]
        def __init__(self, crawler: Crawler, key: str):
            self.spider = crawler.spider
            super().__init__(key)

        @classmethod
        def from_crawler(
            cls, crawler: Crawler, key: str, *args: Any, **kwargs: Any
        ) -> Self:
            return cls(crawler, key)

        def push(self, request: Request) -> None:
            request_dict = request.to_dict(spider=self.spider)
            super().push(request_dict)

        def pop(self) -> Optional[Request]:
            request = super().pop()
            if not request:
                return None
            return request_from_dict(request, spider=self.spider)

        def peek(self) -> Optional[Request]:
            """Returns the next object to be returned by :meth:`pop`,
            but without removing it from the queue.

            Raises :exc:`NotImplementedError` if the underlying queue class does
            not implement a ``peek`` method, which is optional for queues.
            """
            request = super().peek()
            if not request:
                return None
            return request_from_dict(request, spider=self.spider)

    return ScrapyRequestQueue


def _scrapy_non_serialization_queue(
    queue_class: Type[queue.BaseQueue],
) -> Type[queue.BaseQueue]:
    class ScrapyRequestQueue(queue_class):  # type: ignore[valid-type,misc]
        @classmethod
        def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any) -> Self:
            return cls()

        def peek(self) -> Optional[Any]:
            """Returns the next object to be returned by :meth:`pop`,
            but without removing it from the queue.

            Raises :exc:`NotImplementedError` if the underlying queue class does
            not implement a ``peek`` method, which is optional for queues.
            """
            try:
                s = super().peek()
            except AttributeError as ex:
                raise NotImplementedError(
                    "The underlying queue class does not implement 'peek'"
                ) from ex
            return s

    return ScrapyRequestQueue


def _pickle_serialize(obj: Any) -> bytes:
    try:
        return pickle.dumps(obj, protocol=4)
    # Both pickle.PicklingError and AttributeError can be raised by pickle.dump(s)
    # TypeError is raised from parsel.Selector
    except (pickle.PicklingError, AttributeError, TypeError) as e:
        raise ValueError(str(e)) from e


# queue.*Queue aren't subclasses of queue.BaseQueue
_PickleFifoSerializationDiskQueue = _serializable_queue(
    _with_mkdir(queue.FifoDiskQueue), _pickle_serialize, pickle.loads  # type: ignore[arg-type]
)
_PickleLifoSerializationDiskQueue = _serializable_queue(
    _with_mkdir(queue.LifoDiskQueue), _pickle_serialize, pickle.loads  # type: ignore[arg-type]
)
_MarshalFifoSerializationDiskQueue = _serializable_queue(
    _with_mkdir(queue.FifoDiskQueue), marshal.dumps, marshal.loads  # type: ignore[arg-type]
)
_MarshalLifoSerializationDiskQueue = _serializable_queue(
    _with_mkdir(queue.LifoDiskQueue), marshal.dumps, marshal.loads  # type: ignore[arg-type]
)

# public queue classes
PickleFifoDiskQueue = _scrapy_serialization_queue(_PickleFifoSerializationDiskQueue)
PickleLifoDiskQueue = _scrapy_serialization_queue(_PickleLifoSerializationDiskQueue)
MarshalFifoDiskQueue = _scrapy_serialization_queue(_MarshalFifoSerializationDiskQueue)
MarshalLifoDiskQueue = _scrapy_serialization_queue(_MarshalLifoSerializationDiskQueue)
FifoMemoryQueue = _scrapy_non_serialization_queue(queue.FifoMemoryQueue)  # type: ignore[arg-type]
LifoMemoryQueue = _scrapy_non_serialization_queue(queue.LifoMemoryQueue)  # type: ignore[arg-type]
