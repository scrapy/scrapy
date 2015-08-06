"""
Scheduler queues
"""

import types
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


def _sane_pickle_serialize(obj):
    try:
        return pickle.dumps(obj, protocol=2)
    except pickle.PicklingError as e:
        raise ValueError(str(e))


# Workaround for Python2.7 + Twisted 15.3.0 bug, see #7989.
def _py27_pickle_serialize(obj):
    try:
        return pickle.dumps(obj, protocol=2)
    except pickle.PicklingError as e:
        raise ValueError(str(e))
    except AttributeError as e:
        if '__qualname__' in str(e):
            raise ValueError("can't pickle function objects")
        raise

# Workaround for Python3.3 bug serializing lambda objects
def _py33_pickle_serialize(obj):
    if isinstance(obj, types.FunctionType) and obj.__name__ == "<lambda>":
        raise ValueError("can't pickle function objects")

    try:
        return pickle.dumps(obj, protocol=2)
    except pickle.PicklingError as e:
        raise ValueError(str(e))


# The following module is imported by twisted.web.server
# and has the undesired side effect of altering pickle register
import twisted.persisted.styles  # NOQA
try:
    _sane_pickle_serialize(lambda x: x)
except ValueError:
    _pickle_serialize = _sane_pickle_serialize
except AttributeError:
    _pickle_serialize = _py27_pickle_serialize
else:
    _pickle_serialize = _py33_pickle_serialize

# Double check lambdas are not serializables
try:
    _pickle_serialize(lambda x: x)
except ValueError:
    pass
else:
    assert False, "Lambda functions are serializables"


PickleFifoDiskQueue = _serializable_queue(queue.FifoDiskQueue, \
    _pickle_serialize, pickle.loads)
PickleLifoDiskQueue = _serializable_queue(queue.LifoDiskQueue, \
    _pickle_serialize, pickle.loads)
MarshalFifoDiskQueue = _serializable_queue(queue.FifoDiskQueue, \
    marshal.dumps, marshal.loads)
MarshalLifoDiskQueue = _serializable_queue(queue.LifoDiskQueue, \
    marshal.dumps, marshal.loads)
FifoMemoryQueue = queue.FifoMemoryQueue
LifoMemoryQueue = queue.LifoMemoryQueue
