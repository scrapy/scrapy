"""
Write to stdout the command line args it received, one per line.
"""

from __future__ import print_function

import sys


for x in sys.argv[1:]:
    print(x)
