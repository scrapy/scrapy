#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.
#

"""Test SOAP support."""


from unittest import skipIf

from twisted.internet import defer, reactor
from twisted.trial.unittest import TestCase
from twisted.web import error, server

try:
    import SOAPpy  # type: ignore[import]

    from twisted.web import soap
    from twisted.web.soap import SOAPPublisher
except ImportError:
    SOAPpy = None
    SOAPPublisher = object  # type: ignore[misc,assignment]


class Test(SOAPPublisher):
    def soap_add(self, a, b):
        return a + b

    def soap_kwargs(self, a=1, b=2):
        return a + b

    soap_kwargs.useKeywords = True  # type: ignore[attr-defined]

    def soap_triple(self, string, num):
        return [string, num, None]

    def soap_struct(self):
        return SOAPpy.structType({"a": "c"})

    def soap_defer(self, x):
        return defer.succeed(x)

    def soap_deferFail(self):
        return defer.fail(ValueError())

    def soap_fail(self):
        raise RuntimeError

    def soap_deferFault(self):
        return defer.fail(ValueError())

    def soap_complex(self):
        return {"a": ["b", "c", 12, []], "D": "foo"}

    def soap_dict(self, map, key):
        return map[key]


@skipIf(not SOAPpy, "SOAPpy not installed")
class SOAPTests(TestCase):
    def setUp(self):
        self.publisher = Test()
        self.p = reactor.listenTCP(
            0, server.Site(self.publisher), interface="127.0.0.1"
        )
        self.port = self.p.getHost().port

    def tearDown(self):
        return self.p.stopListening()

    def proxy(self):
        return soap.Proxy("http://127.0.0.1:%d/" % self.port)

    def testResults(self):
        inputOutput = [
            ("add", (2, 3), 5),
            ("defer", ("a",), "a"),
            ("dict", ({"a": 1}, "a"), 1),
            ("triple", ("a", 1), ["a", 1, None]),
        ]

        dl = []
        for meth, args, outp in inputOutput:
            d = self.proxy().callRemote(meth, *args)
            d.addCallback(self.assertEqual, outp)
            dl.append(d)

        # SOAPpy kinda blows.
        d = self.proxy().callRemote("complex")
        d.addCallback(lambda result: result._asdict())
        d.addCallback(self.assertEqual, {"a": ["b", "c", 12, []], "D": "foo"})
        dl.append(d)

        # We now return to our regularly scheduled program,
        # already in progress.
        return defer.DeferredList(dl, fireOnOneErrback=True)

    def testMethodNotFound(self):
        """
        Check that a non existing method return error 500.
        """
        d = self.proxy().callRemote("doesntexist")
        self.assertFailure(d, error.Error)

        def cb(err):
            self.assertEqual(int(err.status), 500)

        d.addCallback(cb)
        return d

    def testLookupFunction(self):
        """
        Test lookupFunction method on publisher, to see available remote
        methods.
        """
        self.assertTrue(self.publisher.lookupFunction("add"))
        self.assertTrue(self.publisher.lookupFunction("fail"))
        self.assertFalse(self.publisher.lookupFunction("foobar"))
