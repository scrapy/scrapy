from collections import deque, defaultdict
from heapq import heappush, heappop
import time
from itertools import chain


class PriorityQueue1(object):
    """A simple priority queue"""

    def __init__(self, size=1):
        self.items = []

    def push(self, item, priority=0):
        heappush(self.items, (priority, time.time(), item))

    def pop(self):
        priority, _, item = heappop(self.items)
        return item, priority

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return ((item, priority) for priority, _, item in self.items)

    def __nonzero__(self):
        return bool(self.items)

class PriorityQueue2(object):
    """
    Faster priority queue implementation, based on a dictionary of lists
    @author: Federico Feroldi <federico@cloudify.me>
    """
    def __init__(self, size=1):
        self.items = defaultdict(deque)

    def push(self, item, priority=0):
        self.items[priority].appendleft(item)

    def pop(self):
        priorities = self.items.keys()
        priorities.sort()

        for priority in priorities:
            if len(self.items[priority]) > 0:
                return (self.items[priority].pop(), priority)

        raise IndexError

    def __len__(self):
        totlen = 0
        for q in self.items.values():
            totlen += len(q)
        return totlen

    def __iter__(self):
        priorities = self.items.keys()
        priorities.sort()

        for priority in priorities:
            for i in self.items[priority]:
                yield (i, priority)

    def __nonzero__(self):
        for q in self.items.values():
            if len(q) > 0:
                return True
        return False

class PriorityQueue3(object):
    """Priority queue using a deque for priority 0"""

    def __init__(self, size=1):
        self.negitems = []
        self.pzero = deque()
        self.positems = []

    def push(self, item, priority=0):
        if priority == 0:
            self.pzero.appendleft(item)
        elif priority < 0:
            heappush(self.negitems, (priority, time.time(), item))
        else:
            heappush(self.positems, (priority, time.time(), item))

    def pop(self):
        if self.negitems:
            priority, _, item = heappop(self.negitems)
            return item, priority
        elif self.pzero:
            return (self.pzero.pop(), 0)
        else:
            priority, _, item = heappop(self.positems)
            return item, priority

    def __len__(self):
        return len(self.negitems) + len(self.pzero) + len(self.positems)

    def __iter__(self):
        for priority, _, item in self.negitems:
            yield (item, priority)
        for item in self.pzero:
            yield (item, 0)
        for priority, _, item in self.positems:
            yield (item, priority)

    def __nonzero__(self):
        return bool(self.negitems and self.pzero and self.positems)


#------------------------------------------------------------------------------

class PriorityQueue4(object):
    """Priority queue using a deque for priority 0"""

    def __init__(self, size=1):
        self.negitems = defaultdict(deque)
        self.pzero = deque()
        self.positems = defaultdict(deque)

    def push(self, item, priority=0):
        if priority == 0:
            self.pzero.appendleft(item)
        elif priority < 0:
            self.negitems[priority].appendleft(item)
        else:
            self.positems[priority].appendleft(item)

    def pop(self):
        if self.negitems:
            priorities = self.negitems.keys()
            priorities.sort()
            for priority in priorities:
                deq = self.negitems[priority]
                if deq:
                    t = (deq.pop(), priority)
                    if not deq:
                        del self.negitems[priority]
                    return t
        elif self.pzero:
            return (self.pzero.pop(), 0)
        else:
            priorities = self.positems.keys()
            priorities.sort()
            for priority in priorities:
                deq = self.positems[priority]
                if deq:
                    t = (deq.pop(), priority)
                    if not deq:
                        del self.positems[priority]
                    return t
        raise IndexError("pop from an empty queue")

    def __len__(self):
        total = sum(len(v) for v in self.negitems.values()) + \
                len(self.pzero) + \
                sum(len(v) for v in self.positems.values())
        return total

    def __iter__(self):
        gen_negs = ((i, priority) 
                    for priority in sorted(self.negitems.keys())
                    for i in reversed(self.negitems[priority]))
        gen_zeros = ((item,0) for item in self.pzero)
        gen_pos = ((i, priority) 
                    for priority in sorted(self.positems.keys())
                    for i in reversed(self.positems[priority]))
        return chain(gen_negs, gen_zeros, gen_pos)


    def __nonzero__(self):
        return bool(self.negitems or self.pzero or self.positems)

#------------------------------------------------------------------------------

class PriorityQueue5(object):
    """Priority queue using a deque for priority 0"""

    def __init__(self, size=1):
        # preallocate deques for a fixed number of priorities
        size = size if size % 2 else size + 1
        self.zero = size // 2
        self.priolist = [deque() for _ in range(size)]

    def push(self, item, priority=0):
        self.priolist[priority + self.zero].appendleft(item)

    def pop(self):
        for prio, queue in enumerate(self.priolist):
            if len(queue):
                final = prio - self.zero
                return (queue.pop(), final)

        raise IndexError("pop from an empty queue")

    def __len__(self):
        return sum(len(v) for v in self.priolist)

    def __iter__(self):
        for prio, queue in enumerate(self.priolist):
            final = prio - self.zero
            for i in reversed(queue):
                yield (i, final)

    def __nonzero__(self):
        return bool(len(self))

class PriorityQueue6(object):
    """Priority queue using a deque for priority 0"""

    def __init__(self, size=1):
        # preallocate deques for a fixed number of priorities
        size = size if size % 2 else size + 1
        self.zero = size // 2
        self.index = 0
        self.priolist = [deque() for _ in range(size)]

    def push(self, item, priority=0):
        final = priority + self.zero
        if self.index > final:
            self.index = final
        self.priolist[final].appendleft(item)

    def pop(self):
        cached = self.priolist[self.index]
        if len(cached):
            return (cached.pop(), self.index - self.zero)

        for prio, queue in enumerate(self.priolist[self.index:]):
            if len(queue):
                final = prio + self.index - self.zero
                return (queue.pop(), final)

        raise IndexError("pop from an empty queue")

    def __len__(self):
        return sum(len(v) for v in self.priolist)

    def __iter__(self):
        for prio, queue in enumerate(self.priolist):
            final = prio - self.zero
            for i in reversed(queue):
                yield (i, final)

    def __nonzero__(self):
        return bool(len(self))



