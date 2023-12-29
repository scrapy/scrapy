"""
Scheduler queues
"""

import marshal
import pickle
from os import PathLike
from pathlib import Path
from typing import Union

from queuelib import queue

from scrapy.utils.request import request_from_dict


def _with_mkdir(queue_class):
    class DirectoriesCreated(queue_class):
        def __init__(self, path: Union[str, PathLike], *args, **kwargs):
            dirname = Path(path).parent
            if not dirname.exists():
                dirname.mkdir(parents=True, exist_ok=True)
            super().__init__(path, *args, **kwargs)

    return DirectoriesCreated


def _serializable_queue(queue_class, serialize, deserialize):
    class SerializableQueue(queue_class):
        def push(self, obj):
            s = serialize(obj)
            super().push(s)

        def pop(self):
            s = super().pop()
            if s:
                return deserialize(s)

        def peek(self):
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

    return SerializableQueue


def _scrapy_serialization_queue(queue_class):
    class ScrapyRequestQueue(queue_class):
        def __init__(self, crawler, key):
            self.spider = crawler.spider
            super().__init__(key)

        @classmethod
        def from_crawler(cls, crawler, key, *args, **kwargs):
            return cls(crawler, key)

        def push(self, request):
            request = request.to_dict(spider=self.spider)
            return super().push(request)

        def pop(self):
            request = super().pop()
            if not request:
                return None
            return request_from_dict(request, spider=self.spider)

        def peek(self):
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


def _scrapy_non_serialization_queue(queue_class):
    class ScrapyRequestQueue(queue_class):
        @classmethod
        def from_crawler(cls, crawler, *args, **kwargs):
            return cls()

        def peek(self):
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


def _pickle_serialize(obj):
    try:
        return pickle.dumps(obj, protocol=4)
    # Both pickle.PicklingError and AttributeError can be raised by pickle.dump(s)
    # TypeError is raised from parsel.Selector
    except (pickle.PicklingError, AttributeError, TypeError) as e:
        raise ValueError(str(e)) from e


_PickleFifoSerializationDiskQueue = _serializable_queue(
    _with_mkdir(queue.FifoDiskQueue), _pickle_serialize, pickle.loads
)
_PickleLifoSerializationDiskQueue = _serializable_queue(
    _with_mkdir(queue.LifoDiskQueue), _pickle_serialize, pickle.loads
)
_MarshalFifoSerializationDiskQueue = _serializable_queue(
    _with_mkdir(queue.FifoDiskQueue), marshal.dumps, marshal.loads
)
_MarshalLifoSerializationDiskQueue = _serializable_queue(
    _with_mkdir(queue.LifoDiskQueue), marshal.dumps, marshal.loads
)

# public queue classes
PickleFifoDiskQueue = _scrapy_serialization_queue(_PickleFifoSerializationDiskQueue)
PickleLifoDiskQueue = _scrapy_serialization_queue(_PickleLifoSerializationDiskQueue)
MarshalFifoDiskQueue = _scrapy_serialization_queue(_MarshalFifoSerializationDiskQueue)
MarshalLifoDiskQueue = _scrapy_serialization_queue(_MarshalLifoSerializationDiskQueue)
FifoMemoryQueue = _scrapy_non_serialization_queue(queue.FifoMemoryQueue)
LifoMemoryQueue = _scrapy_non_serialization_queue(queue.LifoMemoryQueue)
