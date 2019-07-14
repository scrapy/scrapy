"""
Scheduler queues
"""

import marshal
import os
import os.path
from six.moves import cPickle as pickle

from queuelib import queue

from scrapy.utils.reqser import request_to_dict, request_from_dict


def _with_mkdir(queue_class):

    class DirectoriesCreated(queue_class):
        def __init__(self, path, *args, **kwargs):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            super(DirectoriesCreated, self).__init__(path, *args, **kwargs)

    return DirectoriesCreated


def _scrapy_queue(queue_class, serialize, deserialize, *, use_key=False):

    class SerializableQueue(queue_class):

        def __init__(self, crawler, key, _):
            self.spider = crawler.spider
            args_ = []
            if use_key:
                args_ = [key]
            super(SerializableQueue, self).__init__(*args_)

        def push(self, request):
            if serialize:
                request = request_to_dict(request, self.spider)
                request = serialize(request)

            return super(SerializableQueue, self).push(request)

        def pop(self):
            request = super(SerializableQueue, self).pop()

            if not request:
                return None

            if deserialize:
                request = deserialize(request)
                request = request_from_dict(request, self.spider)

            return request

    return SerializableQueue


def _pickle_serialize(obj):
    try:
        return pickle.dumps(obj, protocol=2)
    # Python <= 3.4 raises pickle.PicklingError here while
    # 3.5 <= Python < 3.6 raises AttributeError and
    # Python >= 3.6 raises TypeError
    except (pickle.PicklingError, AttributeError, TypeError) as e:
        raise ValueError(str(e))


PickleFifoDiskQueue = _scrapy_queue(_with_mkdir(queue.FifoDiskQueue),
    _pickle_serialize, pickle.loads, use_key=True)
PickleLifoDiskQueue = _scrapy_queue(_with_mkdir(queue.LifoDiskQueue),
    _pickle_serialize, pickle.loads, use_key=True)
MarshalFifoDiskQueue = _scrapy_queue(_with_mkdir(queue.FifoDiskQueue),
    marshal.dumps, marshal.loads, use_key=True)
MarshalLifoDiskQueue = _scrapy_queue(_with_mkdir(queue.LifoDiskQueue),
    marshal.dumps, marshal.loads, use_key=True)
FifoMemoryQueue = _scrapy_queue(queue.FifoMemoryQueue,
    None, None, use_key=False)
LifoMemoryQueue = _scrapy_queue(queue.LifoMemoryQueue,
    None, None, use_key=False)
