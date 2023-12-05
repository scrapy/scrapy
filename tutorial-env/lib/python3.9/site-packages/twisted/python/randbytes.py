# -*- test-case-name: twisted.test.test_randbytes -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Cryptographically secure random implementation, with fallback on normal random.
"""


import os
import random
import warnings

getrandbits = getattr(random, "getrandbits", None)

_fromhex = bytes.fromhex


class SecureRandomNotAvailable(RuntimeError):
    """
    Exception raised when no secure random algorithm is found.
    """


class SourceNotAvailable(RuntimeError):
    """
    Internal exception used when a specific random source is not available.
    """


class RandomFactory:
    """
    Factory providing L{secureRandom} and L{insecureRandom} methods.

    You shouldn't have to instantiate this class, use the module level
    functions instead: it is an implementation detail and could be removed or
    changed arbitrarily.
    """

    # This variable is no longer used, and will eventually be removed.
    randomSources = ()

    getrandbits = getrandbits

    def _osUrandom(self, nbytes):
        """
        Wrapper around C{os.urandom} that cleanly manage its absence.
        """
        try:
            return os.urandom(nbytes)
        except (AttributeError, NotImplementedError) as e:
            raise SourceNotAvailable(e)

    def secureRandom(self, nbytes, fallback=False):
        """
        Return a number of secure random bytes.

        @param nbytes: number of bytes to generate.
        @type nbytes: C{int}
        @param fallback: Whether the function should fallback on non-secure
            random or not.  Default to C{False}.
        @type fallback: C{bool}

        @return: a string of random bytes.
        @rtype: C{str}
        """
        try:
            return self._osUrandom(nbytes)
        except SourceNotAvailable:
            pass

        if fallback:
            warnings.warn(
                "urandom unavailable - "
                "proceeding with non-cryptographically secure random source",
                category=RuntimeWarning,
                stacklevel=2,
            )
            return self.insecureRandom(nbytes)
        else:
            raise SecureRandomNotAvailable("No secure random source available")

    def _randBits(self, nbytes):
        """
        Wrapper around C{os.getrandbits}.
        """
        if self.getrandbits is not None:
            n = self.getrandbits(nbytes * 8)
            hexBytes = ("%%0%dx" % (nbytes * 2)) % n
            return _fromhex(hexBytes)
        raise SourceNotAvailable("random.getrandbits is not available")

    _maketrans = bytes.maketrans
    _BYTES = _maketrans(b"", b"")

    def _randModule(self, nbytes):
        """
        Wrapper around the C{random} module.
        """
        return b"".join([bytes([random.choice(self._BYTES)]) for i in range(nbytes)])

    def insecureRandom(self, nbytes):
        """
        Return a number of non secure random bytes.

        @param nbytes: number of bytes to generate.
        @type nbytes: C{int}

        @return: a string of random bytes.
        @rtype: C{str}
        """
        for src in ("_randBits", "_randModule"):
            try:
                return getattr(self, src)(nbytes)
            except SourceNotAvailable:
                pass


factory = RandomFactory()

secureRandom = factory.secureRandom

insecureRandom = factory.insecureRandom

del factory


__all__ = ["secureRandom", "insecureRandom", "SecureRandomNotAvailable"]
