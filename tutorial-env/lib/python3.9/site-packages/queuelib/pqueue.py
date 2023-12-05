from typing import Any, Callable, Iterable, List, Optional

from queuelib.queue import BaseQueue


class PriorityQueue:
    """A priority queue implemented using multiple internal queues (typically,
    FIFO queues). The internal queue must implement the following methods:

        * push(obj)
        * pop()
        * peek()
        * close()
        * __len__()

    The constructor receives a qfactory argument, which is a callable used to
    instantiate a new (internal) queue when a new priority is allocated. The
    qfactory function is called with the priority number as first and only
    argument.

    Only integer priorities should be used. Lower numbers are higher
    priorities.

    startprios is a sequence of priorities to start with. If the queue was
    previously closed leaving some priority buckets non-empty, those priorities
    should be passed in startprios.

    """

    def __init__(self, qfactory: Callable[[int], BaseQueue], startprios: Iterable[int] = ()) -> None:
        self.queues = {}
        self.qfactory = qfactory
        for p in startprios:
            self.queues[p] = self.qfactory(p)
        self.curprio = min(startprios) if startprios else None

    def push(self, obj: Any, priority: int = 0) -> None:
        if priority not in self.queues:
            self.queues[priority] = self.qfactory(priority)
        q = self.queues[priority]
        q.push(obj)  # this may fail (eg. serialization error)
        if self.curprio is None or priority < self.curprio:
            self.curprio = priority

    def pop(self) -> Optional[Any]:
        if self.curprio is None:
            return None
        q = self.queues[self.curprio]
        m = q.pop()
        if len(q) == 0:
            del self.queues[self.curprio]
            q.close()
            prios = [p for p, q in self.queues.items() if len(q) > 0]
            self.curprio = min(prios) if prios else None
        return m

    def peek(self) -> Optional[Any]:
        if self.curprio is None:
            return None
        return self.queues[self.curprio].peek()

    def close(self) -> List[int]:
        active = []
        for p, q in self.queues.items():
            if len(q):
                active.append(p)
            q.close()
        return active

    def __len__(self) -> int:
        return sum(len(x) for x in self.queues.values()) if self.queues else 0
