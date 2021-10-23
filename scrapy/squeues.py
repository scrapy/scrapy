"""
Scheduler queues
"""

import marshal
import os
import pickle

from queuelib import queue

from scrapy.utils.deprecate import create_deprecated_class
from scrapy.utils.request import request_from_dict


def _with_mkdir(queue_class):

    class DirectoriesCreated(queue_class):

        def __init__(self, path, *args, **kwargs):
            dirname = os.path.dirname(path)
            if not os.path.exists(dirname):
                os.makedirs(dirname, exist_ok=True)
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
                raise NotImplementedError("The underlying queue class does not implement 'peek'") from ex
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
                raise NotImplementedError("The underlying queue class does not implement 'peek'") from ex
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
    _with_mkdir(queue.FifoDiskQueue),
    _pickle_serialize,
    pickle.loads
)
_PickleLifoSerializationDiskQueue = _serializable_queue(
    _with_mkdir(queue.LifoDiskQueue),
    _pickle_serialize,
    pickle.loads
)
_MarshalFifoSerializationDiskQueue = _serializable_queue(
    _with_mkdir(queue.FifoDiskQueue),
    marshal.dumps,
    marshal.loads
)
_MarshalLifoSerializationDiskQueue = _serializable_queue(
    _with_mkdir(queue.LifoDiskQueue),
    marshal.dumps,
    marshal.loads
)

# public queue classes
PickleFifoDiskQueue = _scrapy_serialization_queue(_PickleFifoSerializationDiskQueue)
PickleLifoDiskQueue = _scrapy_serialization_queue(_PickleLifoSerializationDiskQueue)
MarshalFifoDiskQueue = _scrapy_serialization_queue(_MarshalFifoSerializationDiskQueue)
MarshalLifoDiskQueue = _scrapy_serialization_queue(_MarshalLifoSerializationDiskQueue)
FifoMemoryQueue = _scrapy_non_serialization_queue(queue.FifoMemoryQueue)
LifoMemoryQueue = _scrapy_non_serialization_queue(queue.LifoMemoryQueue)


# deprecated queue classes
_subclass_warn_message = "{cls} inherits from deprecated class {old}"
_instance_warn_message = "{cls} is deprecated"
PickleFifoDiskQueueNonRequest = create_deprecated_class(
    name="PickleFifoDiskQueueNonRequest",
    new_class=_PickleFifoSerializationDiskQueue,
    subclass_warn_message=_subclass_warn_message,
    instance_warn_message=_instance_warn_message,
)
PickleLifoDiskQueueNonRequest = create_deprecated_class(
    name="PickleLifoDiskQueueNonRequest",
    new_class=_PickleLifoSerializationDiskQueue,
    subclass_warn_message=_subclass_warn_message,
    instance_warn_message=_instance_warn_message,
)
MarshalFifoDiskQueueNonRequest = create_deprecated_class(
    name="MarshalFifoDiskQueueNonRequest",
    new_class=_MarshalFifoSerializationDiskQueue,
    subclass_warn_message=_subclass_warn_message,
    instance_warn_message=_instance_warn_message,
)
MarshalLifoDiskQueueNonRequest = create_deprecated_class(
    name="MarshalLifoDiskQueueNonRequest",
    new_class=_MarshalLifoSerializationDiskQueue,
    subclass_warn_message=_subclass_warn_message,
    instance_warn_message=_instance_warn_message,
)
