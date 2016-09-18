"""Multi-consumer multi-producer dispatching mechanism

Originally based on pydispatch (BSD) http://pypi.python.org/pypi/PyDispatcher/2.0.1
See license.txt for original license.

Heavily modified for Django's purposes.
Further modified for Scrapy's purposes.
"""
from __future__ import absolute_import

from scrapy.dispatch.dispatcher import Signal, receiver  # NOQA
