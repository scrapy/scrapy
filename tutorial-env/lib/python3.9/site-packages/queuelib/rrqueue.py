from collections import deque
from typing import Any, Callable, Hashable, Iterable, List, Optional

from queuelib.queue import BaseQueue


class RoundRobinQueue:
    """A round robin queue implemented using multiple internal queues (typically,
    FIFO queues). The internal queue must implement the following methods:
        * push(obj)
        * pop()
        * peek()
        * close()
        * __len__()
    The constructor receives a qfactory argument, which is a callable used to
    instantiate a new (internal) queue when a new key is allocated. The
    qfactory function is called with the key number as first and only argument.
    start_domains is a sequence of domains to initialize the queue with. If the
    queue was previously closed leaving some domain buckets non-empty, those
    domains should be passed in start_domains.

    The queue maintains a fifo queue of keys. The key that went last is popped
    first and the next queue for that key is then popped.
    """

    def __init__(self, qfactory: Callable[[Hashable], BaseQueue], start_domains: Iterable[Hashable] = ()) -> None:
        self.queues = {}
        self.qfactory = qfactory
        for key in start_domains:
            self.queues[key] = self.qfactory(key)
        self.key_queue = deque(start_domains)

    def push(self, obj: Any, key: Hashable) -> None:
        if key not in self.key_queue:
            self.queues[key] = self.qfactory(key)
            self.key_queue.appendleft(key)  # it's new, might as well pop first
        q = self.queues[key]
        q.push(obj)  # this may fail (eg. serialization error)

    def peek(self) -> Optional[Any]:
        try:
            key = self.key_queue[-1]
        except IndexError:
            return None
        return self.queues[key].peek()

    def pop(self) -> Optional[Any]:
        # pop until we find a valid object, closing necessary queues
        while True:
            try:
                key = self.key_queue.pop()
            except IndexError:
                return None

            q = self.queues[key]
            m = q.pop()

            if len(q) == 0:
                del self.queues[key]
                q.close()
            else:
                self.key_queue.appendleft(key)

            if m:
                return m

    def close(self) -> List[Hashable]:
        active = []
        for k, q in self.queues.items():
            if len(q):
                active.append(k)
            q.close()
        return active

    def __len__(self) -> int:
        return sum(len(x) for x in self.queues.values()) if self.queues else 0
