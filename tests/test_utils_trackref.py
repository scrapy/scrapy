from io import StringIO
from unittest import mock

import pytest

from scrapy.utils import trackref


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


def test_get_oldest():
    for _ in range(100_000):  # run test 100_000 times
        o1 = Foo()

        o2 = Bar()

        o3 = Foo()  # noqa: F841
        assert trackref.get_oldest("Foo") is o1
        assert trackref.get_oldest("Bar") is o2
        assert trackref.get_oldest("Foo") is o1
        assert trackref.get_oldest("XXX") is None


def test_iter_all():
    o1 = Foo()
    o2 = Bar()  # noqa: F841
    o3 = Foo()
    assert set(trackref.iter_all("Foo")) == {o1, o3}
