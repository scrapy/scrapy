class PriorityQueue(object):
    """A priority queue implemented using multiple internal queues (typically,
    FIFO queues). The internal queue must implement the following methods:

        * push(obj)
        * pop()
        * close()
        * __len__()

    The constructor receives a qfactory argument, which is a callable used to
    instantiate a new (internal) queue when a new priority is allocated. The
    qfactory function is called with the priority number as first and only
    argument.

    Only integer priorities should be used. Lower numbers are higher
    priorities.
    """

    def __init__(self, qfactory, startprios=()):
        self.queues = {}
        self.qfactory = qfactory
        for p in startprios:
            q = self.qfactory(p)
            if q:
                self.queues[p] = q
        self.curprio = min(startprios) if startprios else None

    def push(self, obj, priority=0):
        try:
            q = self.queues[priority]
        except KeyError:
            self.queues[priority] = q = self.qfactory(priority)
        q.push(obj)
        if priority < self.curprio or self.curprio is None:
            self.curprio = priority

    def pop(self):
        if self.curprio is None:
            return
        q = self.queues[self.curprio]
        m = q.pop()
        if not q:
            q = self.queues.pop(self.curprio)
            q.close()
            prios = self.queues.keys()
            self.curprio = min(prios) if prios else None
        return m

    def close(self):
        for q in self.queues.values():
            q.close()
        return self.queues.keys()

    def __len__(self):
        return sum(len(x) for x in self.queues.values()) if self.queues else 0

    def __nonzero__(self):
        return bool(self.queues)
