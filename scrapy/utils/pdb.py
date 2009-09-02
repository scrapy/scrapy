"""
Function for invoking the Python Debugger from Scrapy
"""

from __future__ import absolute_import, with_statement

from pdb import Pdb

from scrapy import log

class ScrapyPdb(Pdb):

    def setup(self, f, t):
        Pdb.setup(self, f, t)
        self.curindex -= 2

def set_trace():
    """Like pdb.set_trace() but works nice with the Scrapy log"""
    with log._std_descriptors():
        ScrapyPdb().set_trace()
