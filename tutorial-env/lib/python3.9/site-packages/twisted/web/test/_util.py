# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
General helpers for L{twisted.web} unit tests.
"""


from typing import Type

from twisted.internet.defer import Deferred, succeed
from twisted.trial.unittest import SynchronousTestCase
from twisted.web import server
from twisted.web._flatten import flattenString
from twisted.web.error import FlattenerError
from twisted.web.template import Flattenable


def _render(resource, request):
    result = resource.render(request)
    if isinstance(result, bytes):
        request.write(result)
        request.finish()
        return succeed(None)
    elif result is server.NOT_DONE_YET:
        if request.finished:
            return succeed(None)
        else:
            return request.notifyFinish()
    else:
        raise ValueError(f"Unexpected return value: {result!r}")


class FlattenTestCase(SynchronousTestCase):
    """
    A test case that assists with testing L{twisted.web._flatten}.
    """

    def assertFlattensTo(self, root: Flattenable, target: bytes) -> Deferred[bytes]:
        """
        Assert that a root element, when flattened, is equal to a string.
        """

        def check(result: bytes) -> bytes:
            self.assertEqual(result, target)
            return result

        d: Deferred[bytes] = flattenString(None, root)
        d.addCallback(check)
        return d

    def assertFlattensImmediately(self, root: Flattenable, target: bytes) -> bytes:
        """
        Assert that a root element, when flattened, is equal to a string, and
        performs no asynchronus Deferred anything.

        This version is more convenient in tests which wish to make multiple
        assertions about flattening, since it can be called multiple times
        without having to add multiple callbacks.

        @return: the result of rendering L{root}, which should be equivalent to
            L{target}.
        @rtype: L{bytes}
        """
        return self.successResultOf(self.assertFlattensTo(root, target))

    def assertFlatteningRaises(self, root: Flattenable, exn: Type[Exception]) -> None:
        """
        Assert flattening a root element raises a particular exception.
        """
        failure = self.failureResultOf(self.assertFlattensTo(root, b""), FlattenerError)
        self.assertIsInstance(failure.value._exception, exn)


def assertIsFilesystemTemporary(case, fileObj):
    """
    Assert that C{fileObj} is a temporary file on the filesystem.

    @param case: A C{TestCase} instance to use to make the assertion.

    @raise: C{case.failureException} if C{fileObj} is not a temporary file on
        the filesystem.
    """
    # The tempfile API used to create content returns an instance of a
    # different type depending on what platform we're running on.  The point
    # here is to verify that the request body is in a file that's on the
    # filesystem.  Having a fileno method that returns an int is a somewhat
    # close approximation of this. -exarkun
    case.assertIsInstance(fileObj.fileno(), int)


__all__ = ["_render", "FlattenTestCase", "assertIsFilesystemTemporary"]
