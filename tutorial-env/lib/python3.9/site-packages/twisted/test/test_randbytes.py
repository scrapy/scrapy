# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.python.randbytes}.
"""


from twisted.python import randbytes
from twisted.trial import unittest


class SecureRandomTestCaseBase:
    """
    Base class for secureRandom test cases.
    """

    def _check(self, source):
        """
        The given random bytes source should return the number of bytes
        requested each time it is called and should probably not return the
        same bytes on two consecutive calls (although this is a perfectly
        legitimate occurrence and rejecting it may generate a spurious failure
        -- maybe we'll get lucky and the heat death with come first).
        """
        for nbytes in range(17, 25):
            s = source(nbytes)
            self.assertEqual(len(s), nbytes)
            s2 = source(nbytes)
            self.assertEqual(len(s2), nbytes)
            # This is crude but hey
            self.assertNotEqual(s2, s)


class SecureRandomTests(SecureRandomTestCaseBase, unittest.TestCase):
    """
    Test secureRandom under normal conditions.
    """

    def test_normal(self):
        """
        L{randbytes.secureRandom} should return a string of the requested
        length and make some effort to make its result otherwise unpredictable.
        """
        self._check(randbytes.secureRandom)


class ConditionalSecureRandomTests(
    SecureRandomTestCaseBase, unittest.SynchronousTestCase
):
    """
    Test random sources one by one, then remove it to.
    """

    def setUp(self):
        """
        Create a L{randbytes.RandomFactory} to use in the tests.
        """
        self.factory = randbytes.RandomFactory()

    def errorFactory(self, nbytes):
        """
        A factory raising an error when a source is not available.
        """
        raise randbytes.SourceNotAvailable()

    def test_osUrandom(self):
        """
        L{RandomFactory._osUrandom} should work as a random source whenever
        L{os.urandom} is available.
        """
        self._check(self.factory._osUrandom)

    def test_withoutAnything(self):
        """
        Remove all secure sources and assert it raises a failure. Then try the
        fallback parameter.
        """
        self.factory._osUrandom = self.errorFactory
        self.assertRaises(
            randbytes.SecureRandomNotAvailable, self.factory.secureRandom, 18
        )

        def wrapper():
            return self.factory.secureRandom(18, fallback=True)

        s = self.assertWarns(
            RuntimeWarning,
            "urandom unavailable - "
            "proceeding with non-cryptographically secure random source",
            __file__,
            wrapper,
        )
        self.assertEqual(len(s), 18)


class RandomBaseTests(SecureRandomTestCaseBase, unittest.SynchronousTestCase):
    """
    'Normal' random test cases.
    """

    def test_normal(self):
        """
        Test basic case.
        """
        self._check(randbytes.insecureRandom)

    def test_withoutGetrandbits(self):
        """
        Test C{insecureRandom} without C{random.getrandbits}.
        """
        factory = randbytes.RandomFactory()
        factory.getrandbits = None
        self._check(factory.insecureRandom)
