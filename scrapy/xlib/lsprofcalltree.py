# lsprofcalltree.py: lsprof output which is readable by kcachegrind
# David Allouche
# Jp Calderone & Itamar Shtull-Trauring
# Johan Dahlin

from __future__ import print_function
import optparse
import os
import sys

try:
    import cProfile
except ImportError:
    raise SystemExit("This script requires cProfile from Python 2.5")

def label(code):
    if isinstance(code, str):
        return ('~', 0, code)    # built-in functions ('~' sorts at the end)
    else:
        return '%s %s:%d' % (code.co_name,
                             code.co_filename,
                             code.co_firstlineno)

class KCacheGrind(object):
    def __init__(self, profiler):
        self.data = profiler.getstats()
        self.out_file = None

    def output(self, out_file):
        self.out_file = out_file
        print('events: Ticks', file=out_file)
        self._print_summary()
        for entry in self.data:
            self._entry(entry)

    def _print_summary(self):
        max_cost = 0
        for entry in self.data:
            totaltime = int(entry.totaltime * 1000)
            max_cost = max(max_cost, totaltime)
        print('summary: %d' % (max_cost,), file=self.out_file)

    def _entry(self, entry):
        out_file = self.out_file

        code = entry.code
        #print >> out_file, 'ob=%s' % (code.co_filename,)
        if isinstance(code, str):
            print('fi=~', file=out_file)
        else:
            print('fi=%s' % (code.co_filename,), file=out_file)
        print('fn=%s' % (label(code),), file=out_file)

        inlinetime = int(entry.inlinetime * 1000)
        if isinstance(code, str):
            print('0 ', inlinetime, file=out_file)
        else:
            print('%d %d' % (code.co_firstlineno, inlinetime), file=out_file)

        # recursive calls are counted in entry.calls
        if entry.calls:
            calls = entry.calls
        else:
            calls = []

        if isinstance(code, str):
            lineno = 0
        else:
            lineno = code.co_firstlineno

        for subentry in calls:
            self._subentry(lineno, subentry)
        print(file=out_file)

    def _subentry(self, lineno, subentry):
        out_file = self.out_file
        code = subentry.code
        #print >> out_file, 'cob=%s' % (code.co_filename,)
        print('cfn=%s' % (label(code),), file=out_file)
        if isinstance(code, str):
            print('cfi=~', file=out_file)
            print('calls=%d 0' % (subentry.callcount,), file=out_file)
        else:
            print('cfi=%s' % (code.co_filename,), file=out_file)
            print('calls=%d %d' % (
                subentry.callcount, code.co_firstlineno), file=out_file)

        totaltime = int(subentry.totaltime * 1000)
        print('%d %d' % (lineno, totaltime), file=out_file)

def main(args):
    usage = "%s [-o output_file_path] scriptfile [arg] ..."
    parser = optparse.OptionParser(usage=usage % sys.argv[0])
    parser.allow_interspersed_args = False
    parser.add_option('-o', '--outfile', dest="outfile",
                      help="Save stats to <outfile>", default=None)

    if not sys.argv[1:]:
        parser.print_usage()
        sys.exit(2)

    options, args = parser.parse_args()

    if not options.outfile:
        options.outfile = '%s.log' % os.path.basename(args[0])

    sys.argv[:] = args

    prof = cProfile.Profile()
    try:
        try:
            prof = prof.run('execfile(%r)' % (sys.argv[0],))
        except SystemExit:
            pass
    finally:
        kg = KCacheGrind(prof)
        kg.output(file(options.outfile, 'w'))

if __name__ == '__main__':
    sys.exit(main(sys.argv))
