# NB: This file is used in the documentation, if you make changes, ensure
#     you update the line numbers in popen.txt!
"""
A sample module containing the kind of code that
testfixtures helps with testing
"""

from testfixtures.tests.sample1 import X, z

try:
    from guppy import hpy
    guppy = True
except ImportError:
    guppy = False


def dump(path):
    if guppy:
        hpy().heap().stat.dump(path)
