"""
Write to stdout the command line args it received, one per line.
"""


import sys

for x in sys.argv[1:]:
    print(x)
