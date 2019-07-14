"""
Scheduler queues
"""

import marshal
from six.moves import cPickle as pickle

from queuelib import queue

from scrapy.utils.reqser import request_to_dict, request_from_dict


def _serializable_queue(queue_class, serialize, deserialize):

    class SerializableQueue(queue_class):

        def __init__(self, crawler, key):
            self.spider = crawler.spider
            super(SerializableQueue, self).__init__(key)

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


PickleFifoDiskQueue = _serializable_queue(queue.FifoDiskQueue,
    _pickle_serialize, pickle.loads)
PickleLifoDiskQueue = _serializable_queue(queue.LifoDiskQueue,
    _pickle_serialize, pickle.loads)
MarshalFifoDiskQueue = _serializable_queue(queue.FifoDiskQueue,
    marshal.dumps, marshal.loads)
MarshalLifoDiskQueue = _serializable_queue(queue.LifoDiskQueue,
    marshal.dumps, marshal.loads)
FifoMemoryQueue = queue.FifoMemoryQueue
LifoMemoryQueue = queue.LifoMemoryQueue
