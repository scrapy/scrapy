"""
Scheduler queues
"""

import marshal
import os
import pickle

from queuelib import queue

from scrapy.exceptions import SerializationError
from scrapy.utils.reqser import request_to_dict, request_from_dict


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

    return SerializableQueue


def _scrapy_serialization_queue(queue_class):

    class ScrapyRequestQueue(queue_class):

        def __init__(self, crawler, key, *args, **kwargs):
            self.spider = crawler.spider
            super().__init__(key, crawler, *args, **kwargs)

        @classmethod
        def from_crawler(cls, crawler, key, *args, **kwargs):
            return cls(crawler, key, *args, **kwargs)

        def push(self, request):
            request = request_to_dict(request, self.spider)
            return super().push(request)

        def pop(self):
            request = super().pop()

            if not request:
                return None

            request = request_from_dict(request, self.spider)
            return request

    return ScrapyRequestQueue


def _scrapy_non_serialization_queue(queue_class):

    class ScrapyRequestQueue(queue_class):
        @classmethod
        def from_crawler(cls, crawler, *args, **kwargs):
            return cls()

    return ScrapyRequestQueue


def _pickle_serialize(obj):
    try:
        return pickle.dumps(obj, protocol=4)
    # Both pickle.PicklingError and AttributeError can be raised by pickle.dump(s)
    # TypeError is raised from parsel.Selector
    except (pickle.PicklingError, AttributeError, TypeError) as e:
        raise SerializationError(str(e)) from e


def _ignore_args_kwargs_passed_to_constructor(queue_class, used_kwargs):
    class AcceptingQueue(queue_class):
        def __init__(self, path, *_, **kwargs):
            new_kwargs = {k: kwargs[k] for k in used_kwargs if k in kwargs}
            super().__init__(path, **new_kwargs)

    return AcceptingQueue


PickleFifoDiskQueueNonRequest = _serializable_queue(
    _with_mkdir(_ignore_args_kwargs_passed_to_constructor(
        queue.FifoDiskQueue,
        ['chunksize'],
    )),
    _pickle_serialize,
    pickle.loads
)
PickleLifoDiskQueueNonRequest = _serializable_queue(
    _with_mkdir(_ignore_args_kwargs_passed_to_constructor(
        queue.LifoDiskQueue,
        ['chunksize'],
    )),
    _pickle_serialize,
    pickle.loads
)
MarshalFifoDiskQueueNonRequest = _serializable_queue(
    _with_mkdir(_ignore_args_kwargs_passed_to_constructor(
        queue.FifoDiskQueue,
        ['chunksize'],
    )),
    marshal.dumps,
    marshal.loads
)
MarshalLifoDiskQueueNonRequest = _serializable_queue(
    _with_mkdir(_ignore_args_kwargs_passed_to_constructor(
        queue.LifoDiskQueue,
        ['chunksize'],
    )),
    marshal.dumps,
    marshal.loads
)

PickleFifoDiskQueue = _scrapy_serialization_queue(
    PickleFifoDiskQueueNonRequest
)
PickleLifoDiskQueue = _scrapy_serialization_queue(
    PickleLifoDiskQueueNonRequest
)
MarshalFifoDiskQueue = _scrapy_serialization_queue(
    MarshalFifoDiskQueueNonRequest
)
MarshalLifoDiskQueue = _scrapy_serialization_queue(
    MarshalLifoDiskQueueNonRequest
)
FifoMemoryQueue = _scrapy_non_serialization_queue(queue.FifoMemoryQueue)
LifoMemoryQueue = _scrapy_non_serialization_queue(queue.LifoMemoryQueue)
