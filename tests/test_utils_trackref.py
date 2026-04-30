import sys
from io import StringIO
from unittest import mock

import pytest

from scrapy.utils import trackref
from scrapy.utils.python import garbage_collect


class Foo(trackref.object_ref):
    pass


class Bar(trackref.object_ref):
    pass


@pytest.fixture(autouse=True)
def clear_refs() -> None:
    trackref.live_refs.clear()


def test_format_live_refs():
    o1 = Foo()  # noqa: F841
    o2 = Bar()  # noqa: F841
    o3 = Foo()  # noqa: F841
    assert (
        trackref.format_live_refs()
        == """\
Live References

Bar                                 1   oldest: 0s ago
Foo                                 2   oldest: 0s ago
"""
    )

    assert (
        trackref.format_live_refs(ignore=Foo)
        == """\
Live References

Bar                                 1   oldest: 0s ago
"""
    )


@mock.patch("sys.stdout", new_callable=StringIO)
def test_print_live_refs_empty(stdout):
    trackref.print_live_refs()
    assert stdout.getvalue() == "Live References\n\n\n"


@mock.patch("sys.stdout", new_callable=StringIO)
def test_print_live_refs_with_objects(stdout):
    o1 = Foo()  # noqa: F841
    trackref.print_live_refs()
    assert (
        stdout.getvalue()
        == """\
Live References

Foo                                 1   oldest: 0s ago\n\n"""
    )


_IS_PYPY = "PyPy" in sys.version


def test_get_oldest():
    """
    Verify that `get_oldest` returns the oldest live instance of a class.

    The test runs in two passes to expose differences between:
    - CPython (reference counting, immediate destruction)
    - PyPy (tracing GC, delayed destruction)

    Since `trackref` relies on weak references, delayed GC on PyPy can leave
    stale entries in `live_refs`, affecting results unless explicitly cleared.
    """

    def _delete_o1():
        """Delete `o1` and ensure it is actually collected on PyPy."""
        nonlocal o1
        del o1

        if _IS_PYPY:
            # On PyPy, `del` only removes the local reference. The object may
            # still exist until the GC runs, so we force a collection cycle.
            garbage_collect()

    def _do_asserts():
        assert trackref.get_oldest("Foo") is o1
        assert trackref.get_oldest("Bar") is o2
        # Ensure the newer Foo is not incorrectly considered the oldest
        assert trackref.get_oldest("Foo") is not o3
        assert trackref.get_oldest("XXX") is None

    o1, o2, o3 = Foo(), Bar(), Foo()

    _do_asserts()

    # Remove the oldest Foo instance; o3 should now become the oldest
    _delete_o1()
    assert trackref.get_oldest("Foo") is o3

    # PyPy-specific behavior where stale references may persist
    # unless the registry is explicitly cleared.
    if _IS_PYPY:
        trackref.live_refs.clear()

    o1, o2, o3 = Foo(), Bar(), Foo()

    _do_asserts()

    _delete_o1()
    assert trackref.get_oldest("Foo") is o3


def test_iter_all():
    o1 = Foo()
    o2 = Bar()  # noqa: F841
    o3 = Foo()
    assert set(trackref.iter_all("Foo")) == {o1, o3}
