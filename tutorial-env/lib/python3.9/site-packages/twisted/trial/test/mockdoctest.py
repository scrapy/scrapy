# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

# this module is a trivial class with doctests to test trial's doctest
# support.


class Counter:
    """a simple counter object for testing trial's doctest support

    >>> c = Counter()
    >>> c.value()
    0
    >>> c += 3
    >>> c.value()
    3
    >>> c.incr()
    >>> c.value() == 4
    True
    >>> c == 4
    True
    >>> c != 9
    True

    """

    _count = 0

    def __init__(self, initialValue=0, maxval=None):
        self._count = initialValue
        self.maxval = maxval

    def __iadd__(self, other):
        """add other to my value and return self

        >>> c = Counter(100)
        >>> c += 333
        >>> c == 433
        True
        """
        if self.maxval is not None and ((self._count + other) > self.maxval):
            raise ValueError("sorry, counter got too big")
        else:
            self._count += other
        return self

    def __eq__(self, other: object) -> bool:
        """equality operator, compare other to my value()

        >>> c = Counter()
        >>> c == 0
        True
        >>> c += 10
        >>> c.incr()
        >>> c == 10   # fail this test on purpose
        True

        """
        return self._count == other

    def __ne__(self, other: object) -> bool:
        """inequality operator

        >>> c = Counter()
        >>> c != 10
        True
        """
        return not self.__eq__(other)

    def incr(self):
        """increment my value by 1

        >>> from twisted.trial.test.mockdoctest import Counter
        >>> c = Counter(10, 11)
        >>> c.incr()
        >>> c.value() == 11
        True
        >>> c.incr()
        Traceback (most recent call last):
          File "<stdin>", line 1, in ?
          File "twisted/trial/test/mockdoctest.py", line 51, in incr
            self.__iadd__(1)
          File "twisted/trial/test/mockdoctest.py", line 39, in __iadd__
            raise ValueError, "sorry, counter got too big"
        ValueError: sorry, counter got too big
        """
        self.__iadd__(1)

    def value(self):
        """return this counter's value

        >>> c = Counter(555)
        >>> c.value() == 555
        True
        """
        return self._count

    def unexpectedException(self):
        """i will raise an unexpected exception...
        ... *CAUSE THAT'S THE KINDA GUY I AM*

              >>> 1/0
        """
