from itertools import imap
from twisted.trial import unittest

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from scrapy.utils.defer import mustbe_deferred


class MustbeDeferredTest(unittest.TestCase):
    def test_success_function(self):
        steps = []
        def _append(v):
            steps.append(v)
            return steps

        dfd = mustbe_deferred(_append, 1)
        dfd.addCallback(self.assertEqual, [1,2]) # it is [1] with maybeDeferred
        steps.append(2) # add another value, that should be catched by assertEqual
        return dfd

    def test_unfired_deferred(self):
        steps = []
        def _append(v):
            steps.append(v)
            dfd = Deferred()
            reactor.callLater(0, dfd.callback, steps)
            return dfd

        dfd = mustbe_deferred(_append, 1)
        dfd.addCallback(self.assertEqual, [1,2]) # it is [1] with maybeDeferred
        steps.append(2) # add another value, that should be catched by assertEqual
        return dfd

