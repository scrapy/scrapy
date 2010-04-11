"""
This module provides functions added in Python 2.6, which weren't yet available
in Python 2.5. The Python 2.6 function is used when available.
"""

import sys, os

try:
    import multiprocessing
    cpu_count = multiprocessing.cpu_count
except ImportError:
    def cpu_count():
        '''
        Returns the number of CPUs in the system
        '''
        if sys.platform == 'win32':
            try:
                num = int(os.environ['NUMBER_OF_PROCESSORS'])
            except (ValueError, KeyError):
                num = 0
        elif 'bsd' in sys.platform or sys.platform == 'darwin':
            try:
                num = int(os.popen('sysctl -n hw.ncpu').read())
            except ValueError:
                num = 0
        else:
            try:
                num = os.sysconf('SC_NPROCESSORS_ONLN')
            except (ValueError, OSError, AttributeError):
                num = 0

        if num >= 1:
            return num
        else:
            raise NotImplementedError('cannot determine number of cpus')


