"""
Scheduler queues
"""

import marshal
from six.moves import cPickle as pickle

from queuelib import queue


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


def _pickle_serialize(obj):
    try:
        return pickle.dumps(obj, protocol=2)
    # Python <= 3.4 raises pickle.PicklingError here while
    # 3.5 <= Python < 3.6 raises AttributeError and
    # Python >= 3.6 raises TypeError
    except (pickle.PicklingError, AttributeError, TypeError) as e:
        raise ValueError(str(e))


PickleFifoDiskQueue = _serializable_queue(
    queue_class=queue.FifoDiskQueue,
    serialize=_pickle_serialize,
    deserialize=pickle.loads
)
PickleLifoDiskQueue = _serializable_queue(
    queue_class=queue.LifoDiskQueue,
    serialize=_pickle_serialize,
    deserialize=pickle.loads
)
MarshalFifoDiskQueue = _serializable_queue(
    queue_class=queue.FifoDiskQueue,
    serialize=marshal.dumps,
    deserialize=marshal.loads
)
MarshalLifoDiskQueue = _serializable_queue(
    queue_class=queue.LifoDiskQueue,
    serialize=marshal.dumps,
    deserialize=marshal.loads
)
FifoMemoryQueue = queue.FifoMemoryQueue
LifoMemoryQueue = queue.LifoMemoryQueue
