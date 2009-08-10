"""
This module contains some assorted functions used in tests
"""

import os

import libxml2

from scrapy.xpath.document import Libxml2Document

def libxml2debug(testfunction):
    """Decorator for debugging libxml2 memory leaks inside a function.
    
    We've found libxml2 memory leaks are something very weird, and can happen
    sometimes depending on the order where tests are run. So this decorator
    enables libxml2 memory leaks debugging only when the environment variable
    LIBXML2_DEBUGLEAKS is set.

    """
    def newfunc(*args, **kwargs):
        libxml2.debugMemory(1)
        testfunction(*args, **kwargs)
        libxml2.cleanupParser()
        leaked_bytes = libxml2.debugMemory(0) 
        assert leaked_bytes == 0, "libxml2 memory leak detected: %d bytes" % leaked_bytes

    if 'LIBXML2_DEBUGLEAKS' in os.environ:
        return newfunc
    else:
        return testfunction
