from __future__ import with_statement
import os
import timeit
import random
from optparse import OptionParser
from tempfile import mktemp
from pq_classes import *

TESTID = os.getpid()

TESTCASES = [
       ("heapq", PriorityQueue1),
       #("heapq+int", PriorityQueue1b),
       ("dict+deque", PriorityQueue2),
       ("deque+heapq", PriorityQueue3),
       #("deque+heapq+int", PriorityQueue3b),
       ("deque+defaultdict+deque", PriorityQueue4),
       #('list+deque', PriorityQueue5),
       ('list+deque+cache', PriorityQueue5b),
       #('list+deque+cache+islice', PriorityQueue5c),
       ]


stmt_fmt = """
for n, prio in enumerate(randomprio):
    q.push(n, prio)

try:
    while True:
        q.pop()
except IndexError:
    pass
"""

setup_fmt = """
from collections import deque
from __main__ import %(PriorityClass)s as PriorityQueue
q = PriorityQueue(%(priorities)i)

randomprio = deque()
with open('%(samplefile)s') as samples:
    for line in samples:
        prio = int(line.strip())
        randomprio.append(prio)
"""

# def gen_random_priority(priorities):
#     return int(random.random() * priorities) - (priorities / 2)

def uniform_priority(priorities):
    return int(random.random() * priorities) - (priorities / 2)

def normal_priority(priorities):
    prio = int(random.normalvariate(priorities/2, priorities/4)) - (priorities / 2)
    return min(max(prio, -priorities/2), priorities/2)


PRIORITY_DISTRIBUTIONS = {
        'uniform': uniform_priority,
        'normal': normal_priority,
        }


def gen_samples(count, priorities, priority_distribution=uniform_priority):
    fn = '/tmp/pq-%i-%i-%i' % (TESTID, priorities, count)

    with open(fn, 'w') as samplefile:
        for n in xrange(count):
            prio = priority_distribution(priorities)
            samplefile.write('%i\n' % prio)
    return fn

def runtests(pushpops=50*1000, times=30, priorities=1, samplefile=None, priority_distribution=uniform_priority):
    samplefile = samplefile or gen_samples(pushpops, priorities)

    print "\n== With %s priorities (%s) ==\n" % (priorities, samplefile)
    print "pushpops = %s, times = %s" % (pushpops, times)


    stmt = stmt_fmt
    for name, cls in TESTCASES:
        setup = setup_fmt % {
                'PriorityClass': cls.__name__,
                'priorities': priorities,
                'samplefile': samplefile,
                }
        t = timeit.Timer(stmt, setup)
        print "%s implementation: %s" % (name, t.timeit(number=times))


if __name__ == '__main__':
    o = OptionParser()
    o.add_option('-n', '--samples-count', type='int', default=50000, metavar='NUMBER',
            help='The max number or samples to generate')
    o.add_option('-r', '--retry-times', type='int', default=30, metavar='NUMBER',
            help='the times to retry each test')
    o.add_option('-s', '--samplefile', default=None, metavar='FILENAME',
            help='load samples from file, default: use sample generator')
    o.add_option('-p', '--priorities', default='1,3,5,10,100', metavar='CSV_PRIOLIST',
            help='a comma separated list of priorities to test')
    o.add_option('-d', '--priority-distribution', default='uniform', metavar='DISTRIBUTION',
            help='distribution used for random priority generator, default: uniform. possibles: %s' \
                    % ','.join(PRIORITY_DISTRIBUTIONS.keys()))

    opt, args = o.parse_args()

    priolist = map(int, opt.priorities.split(','))
    distribution = PRIORITY_DISTRIBUTIONS[opt.priority_distribution]
    for prio in priolist:
        runtests(pushpops=opt.samples_count, priorities=prio, times=opt.retry_times,
                samplefile=opt.samplefile, priority_distribution=distribution)

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
