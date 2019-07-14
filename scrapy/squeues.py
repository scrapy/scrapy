"""
Scheduler queues
"""

import errno
import marshal
import os
import os.path
from six.moves import cPickle as pickle

from queuelib import queue

from scrapy.utils.reqser import request_to_dict, request_from_dict


def _with_mkdir(queue_class):

    class DirectoriesCreated(queue_class):

        def __init__(self, path, *args, **kwargs):
            dirname = os.path.dirname(path)
            if not os.path.exists(dirname):
                os.makedirs(dirname)

            super(DirectoriesCreated, self).__init__(path, *args, **kwargs)

    return DirectoriesCreated


def _serializable_queue(queue_class, serialize, deserialize):

    class SerializableQueue(queue_class):

        def push(self, obj):
            s = serialize(obj)
            super(SerializableQueue, self).push(s)

        def pop(self):
            s = super(SerializableQueue, self).pop()
            if s:
                return deserialize(s)

    return SerializableQueue


def _scrapy_serialization_queue(queue_class):

    class ScrapyRequestQueue(queue_class):

        def __init__(self, crawler, downstream_queue_cls, key, startprios):
            self.spider = crawler.spider
            super(ScrapyRequestQueue, self).__init__(key)

        def push(self, request):
            request = request_to_dict(request, self.spider)
            return super(ScrapyRequestQueue, self).push(request)

        def pop(self):
            request = super(ScrapyRequestQueue, self).pop()

            if not request:
                return None

            request = request_from_dict(request, self.spider)
            return request

    return ScrapyRequestQueue


def _scrapy_in_memory_queue(queue_class):

    class ScrapyRequestQueue(queue_class):
        def __init__(self, crawler, downstream_queue_cls, key, startprios):
            super(ScrapyRequestQueue, self).__init__()

    return ScrapyRequestQueue


def _pickle_serialize(obj):
    try:
        return pickle.dumps(obj, protocol=2)
    # Python <= 3.4 raises pickle.PicklingError here while
    # 3.5 <= Python < 3.6 raises AttributeError and
    # Python >= 3.6 raises TypeError
    except (pickle.PicklingError, AttributeError, TypeError) as e:
        raise ValueError(str(e))


PickleFifoDiskQueueNonRequest = _serializable_queue(_with_mkdir(queue.FifoDiskQueue),
   _pickle_serialize, pickle.loads)
PickleLifoDiskQueueNonRequest = _serializable_queue(_with_mkdir(queue.LifoDiskQueue),
   _pickle_serialize, pickle.loads)
MarshalFifoDiskQueueNonRequest = _serializable_queue(_with_mkdir(queue.FifoDiskQueue),
   marshal.dumps, marshal.loads)
MarshalLifoDiskQueueNonRequest = _serializable_queue(_with_mkdir(queue.LifoDiskQueue),
    marshal.dumps, marshal.loads)

PickleFifoDiskQueue = _scrapy_serialization_queue(PickleFifoDiskQueueNonRequest)
PickleLifoDiskQueue = _scrapy_serialization_queue(PickleLifoDiskQueueNonRequest)
MarshalFifoDiskQueue = _scrapy_serialization_queue(MarshalFifoDiskQueueNonRequest)
MarshalLifoDiskQueue = _scrapy_serialization_queue(MarshalLifoDiskQueueNonRequest)
FifoMemoryQueue = _scrapy_in_memory_queue(queue.FifoMemoryQueue)
LifoMemoryQueue = _scrapy_in_memory_queue(queue.LifoMemoryQueue)
