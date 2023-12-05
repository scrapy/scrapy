import os

from testfixtures.shouldraise import ShouldAssert
from testfixtures.mock import Mock
from tempfile import mkdtemp
from testfixtures import Replacer, TempDirectory, compare, tempdir
from unittest import TestCase

from ..rmtree import rmtree


class TestTempDir(TestCase):

    @tempdir()
    def test_simple(self, d):
        d.write('something', b'stuff')
        d.write('.svn', b'stuff')
        d.compare((
            '.svn',
            'something',
            ))

    @tempdir()
    def test_subdirs(self, d):
        subdir = ['some', 'thing']
        d.write(subdir+['something'], b'stuff')
        d.write(subdir+['.svn'], b'stuff')
        d.compare(path=subdir, expected=(
            '.svn',
            'something',
            ))

    @tempdir()
    def test_not_same(self, d):
        d.write('something', b'stuff')

        with ShouldAssert(
            "sequence not as expected:\n"
            "\n"
            "same:\n"
            "()\n"
            "\n"
            "expected:\n"
            "('.svn', 'something')\n"
            "\n"
            "actual:\n"
            "('something',)"
        ):
            d.compare(['.svn', 'something'])

    @tempdir(ignore=('.svn', ))
    def test_ignore(self, d):
        d.write('something', b'stuff')
        d.write('.svn', b'stuff')
        d.compare(['something'])

    def test_cleanup_properly(self):
        r = Replacer()
        try:
            m = Mock()
            d = mkdtemp()
            m.return_value = d
            r.replace('testfixtures.tempdirectory.mkdtemp', m)

            self.assertTrue(os.path.exists(d))

            self.assertFalse(m.called)

            @tempdir()
            def test_method(d):
                d.write('something', b'stuff')
                d.compare(['something'])

            self.assertFalse(m.called)
            compare(os.listdir(d), [])

            test_method()

            self.assertTrue(m.called)
            self.assertFalse(os.path.exists(d))

        finally:
            r.restore()
            if os.path.exists(d):
                # only runs if the test fails!
                rmtree(d)  # pragma: no cover

    @tempdir()
    def test_cleanup_test_okay_with_deleted_dir(self, d):
        rmtree(d.path)

    @tempdir()
    def test_decorator_returns_tempdirectory(self, d):
        # check for what we get, so we only have to write
        # tests in test_tempdirectory.py
        self.assertTrue(isinstance(d, TempDirectory))

    def test_dont_create_or_cleanup_with_path(self):
        with Replacer() as r:
            m = Mock()
            r.replace('testfixtures.tempdirectory.mkdtemp', m)
            r.replace('testfixtures.tempdirectory.rmtree', m)

            @tempdir(path='foo')
            def test_method(d):
                compare(d.path, 'foo')

            test_method()

            self.assertFalse(m.called)
