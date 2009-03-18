import timeit
from pq_classes import *

TESTCASES = [
       ("heapq", PriorityQueue1),
       ("dict+deque", PriorityQueue2),
       ("deque+heapq", PriorityQueue3),
       ("deque+defaultdict+deque", PriorityQueue4),
       ('list+deque', PriorityQueue5),
       ('list+deque+cache', PriorityQueue6),
       ]


stmt_single = """
for n in xrange(%(pushpops)s):
    q.push(n)

for n in xrange(%(pushpops)s):
    q.pop()
"""

stmt_multi = """
for n in xrange(%(pushpops)s):
    q.push(n, int(random.random() * %(priorities)s) - %(priorities)s / 2)

for n in xrange(%(pushpops)s):
    q.pop()
"""

setup_fmt = """
import random
from __main__ import %(PriorityClass)s as PriorityQueue
q = PriorityQueue(%(priorities)i)
"""


def runtests(pushpops=50*1000, times=30, priorities=1):
    print "\n== With %s priorities ==\n" % priorities
    print "pushpops = %s, times = %s" % (pushpops, times)

    stmt_fmt = stmt_multi if priorities > 1 else stmt_single
    stmt = stmt_fmt % {'priorities': priorities, 'pushpops': pushpops}

    for name, cls in TESTCASES:
        setup = setup_fmt % {'PriorityClass': cls.__name__, 'priorities': priorities}
        t = timeit.Timer(stmt, setup)
        print "%s implementation: %s" % (name, t.timeit(number=times))

if __name__ == '__main__':
    runtests()
    runtests(priorities=5)
    runtests(priorities=10)
    runtests(priorities=100)

# Results (in seconds, on an intel core2 2.16ghz):
# == Without priorities ==

# pushpops = 50000, times = 30
# heapq implementation: 7.7959010601
# dict+deque implementation: 5.6420109272
# deque+heapq implementation: 3.57563900948

# == With 5 priorities ==

# pushpops = 50000, times = 30
# heapq implementation: 9.83902192116
# dict+deque implementation: 9.21094298363
# deque+heapq implementation: 9.05321097374

# == With 10 priorities ==

# pushpops = 50000, times = 30
# heapq implementation: 9.97831392288
# dict+deque implementation: 11.9721341133
# deque+heapq implementation: 9.79048800468

# == With 100 priorities ==

# pushpops = 50000, times = 30
# heapq implementation: 10.4782910347
# dict+deque implementation: 64.6989660263
# deque+heapq implementation: 10.858932972
