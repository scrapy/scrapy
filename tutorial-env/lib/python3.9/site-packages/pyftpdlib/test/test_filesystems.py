# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

import os
import tempfile
import unittest

from pyftpdlib._compat import getcwdu
from pyftpdlib._compat import u
from pyftpdlib.filesystems import AbstractedFS
from pyftpdlib.test import HOME
from pyftpdlib.test import POSIX
from pyftpdlib.test import PyftpdlibTestCase
from pyftpdlib.test import safe_rmpath
from pyftpdlib.test import touch


if POSIX:
    from pyftpdlib.filesystems import UnixFilesystem


class TestAbstractedFS(PyftpdlibTestCase):
    """Test for conversion utility methods of AbstractedFS class."""

    def test_ftpnorm(self):
        # Tests for ftpnorm method.
        ae = self.assertEqual
        fs = AbstractedFS(u('/'), None)

        fs._cwd = u('/')
        ae(fs.ftpnorm(u('')), u('/'))
        ae(fs.ftpnorm(u('/')), u('/'))
        ae(fs.ftpnorm(u('.')), u('/'))
        ae(fs.ftpnorm(u('..')), u('/'))
        ae(fs.ftpnorm(u('a')), u('/a'))
        ae(fs.ftpnorm(u('/a')), u('/a'))
        ae(fs.ftpnorm(u('/a/')), u('/a'))
        ae(fs.ftpnorm(u('a/..')), u('/'))
        ae(fs.ftpnorm(u('a/b')), '/a/b')
        ae(fs.ftpnorm(u('a/b/..')), u('/a'))
        ae(fs.ftpnorm(u('a/b/../..')), u('/'))
        fs._cwd = u('/sub')
        ae(fs.ftpnorm(u('')), u('/sub'))
        ae(fs.ftpnorm(u('/')), u('/'))
        ae(fs.ftpnorm(u('.')), u('/sub'))
        ae(fs.ftpnorm(u('..')), u('/'))
        ae(fs.ftpnorm(u('a')), u('/sub/a'))
        ae(fs.ftpnorm(u('a/')), u('/sub/a'))
        ae(fs.ftpnorm(u('a/..')), u('/sub'))
        ae(fs.ftpnorm(u('a/b')), u('/sub/a/b'))
        ae(fs.ftpnorm(u('a/b/')), u('/sub/a/b'))
        ae(fs.ftpnorm(u('a/b/..')), u('/sub/a'))
        ae(fs.ftpnorm(u('a/b/../..')), u('/sub'))
        ae(fs.ftpnorm(u('a/b/../../..')), u('/'))
        ae(fs.ftpnorm(u('//')), u('/'))  # UNC paths must be collapsed

    def test_ftp2fs(self):
        # Tests for ftp2fs method.
        def join(x, y):
            return os.path.join(x, y.replace('/', os.sep))

        ae = self.assertEqual
        fs = AbstractedFS(u('/'), None)

        def goforit(root):
            fs._root = root
            fs._cwd = u('/')
            ae(fs.ftp2fs(u('')), root)
            ae(fs.ftp2fs(u('/')), root)
            ae(fs.ftp2fs(u('.')), root)
            ae(fs.ftp2fs(u('..')), root)
            ae(fs.ftp2fs(u('a')), join(root, u('a')))
            ae(fs.ftp2fs(u('/a')), join(root, u('a')))
            ae(fs.ftp2fs(u('/a/')), join(root, u('a')))
            ae(fs.ftp2fs(u('a/..')), root)
            ae(fs.ftp2fs(u('a/b')), join(root, u(r'a/b')))
            ae(fs.ftp2fs(u('/a/b')), join(root, u(r'a/b')))
            ae(fs.ftp2fs(u('/a/b/..')), join(root, u('a')))
            ae(fs.ftp2fs(u('/a/b/../..')), root)
            fs._cwd = u('/sub')
            ae(fs.ftp2fs(u('')), join(root, u('sub')))
            ae(fs.ftp2fs(u('/')), root)
            ae(fs.ftp2fs(u('.')), join(root, u('sub')))
            ae(fs.ftp2fs(u('..')), root)
            ae(fs.ftp2fs(u('a')), join(root, u('sub/a')))
            ae(fs.ftp2fs(u('a/')), join(root, u('sub/a')))
            ae(fs.ftp2fs(u('a/..')), join(root, u('sub')))
            ae(fs.ftp2fs(u('a/b')), join(root, 'sub/a/b'))
            ae(fs.ftp2fs(u('a/b/..')), join(root, u('sub/a')))
            ae(fs.ftp2fs(u('a/b/../..')), join(root, u('sub')))
            ae(fs.ftp2fs(u('a/b/../../..')), root)
            # UNC paths must be collapsed
            ae(fs.ftp2fs(u('//a')), join(root, u('a')))

        if os.sep == '\\':
            goforit(u(r'C:\dir'))
            goforit(u('C:\\'))
            # on DOS-derived filesystems (e.g. Windows) this is the same
            # as specifying the current drive directory (e.g. 'C:\\')
            goforit(u('\\'))
        elif os.sep == '/':
            goforit(u('/home/user'))
            goforit(u('/'))
        else:
            # os.sep == ':'? Don't know... let's try it anyway
            goforit(getcwdu())

    def test_fs2ftp(self):
        # Tests for fs2ftp method.
        def join(x, y):
            return os.path.join(x, y.replace('/', os.sep))

        ae = self.assertEqual
        fs = AbstractedFS(u('/'), None)

        def goforit(root):
            fs._root = root
            ae(fs.fs2ftp(root), u('/'))
            ae(fs.fs2ftp(join(root, u('/'))), u('/'))
            ae(fs.fs2ftp(join(root, u('.'))), u('/'))
            # can't escape from root
            ae(fs.fs2ftp(join(root, u('..'))), u('/'))
            ae(fs.fs2ftp(join(root, u('a'))), u('/a'))
            ae(fs.fs2ftp(join(root, u('a/'))), u('/a'))
            ae(fs.fs2ftp(join(root, u('a/..'))), u('/'))
            ae(fs.fs2ftp(join(root, u('a/b'))), u('/a/b'))
            ae(fs.fs2ftp(join(root, u('a/b'))), u('/a/b'))
            ae(fs.fs2ftp(join(root, u('a/b/..'))), u('/a'))
            ae(fs.fs2ftp(join(root, u('/a/b/../..'))), u('/'))
            fs._cwd = u('/sub')
            ae(fs.fs2ftp(join(root, 'a/')), u('/a'))

        if os.sep == '\\':
            goforit(u(r'C:\dir'))
            goforit(u('C:\\'))
            # on DOS-derived filesystems (e.g. Windows) this is the same
            # as specifying the current drive directory (e.g. 'C:\\')
            goforit(u('\\'))
            fs._root = u(r'C:\dir')
            ae(fs.fs2ftp(u('C:\\')), u('/'))
            ae(fs.fs2ftp(u('D:\\')), u('/'))
            ae(fs.fs2ftp(u('D:\\dir')), u('/'))
        elif os.sep == '/':
            goforit(u('/'))
            if os.path.realpath('/__home/user') != '/__home/user':
                self.fail('Test skipped (symlinks not allowed).')
            goforit(u('/__home/user'))
            fs._root = u('/__home/user')
            ae(fs.fs2ftp(u('/__home')), u('/'))
            ae(fs.fs2ftp(u('/')), u('/'))
            ae(fs.fs2ftp(u('/__home/userx')), u('/'))
        else:
            # os.sep == ':'? Don't know... let's try it anyway
            goforit(getcwdu())

    def test_validpath(self):
        # Tests for validpath method.
        fs = AbstractedFS(u('/'), None)
        fs._root = HOME
        self.assertTrue(fs.validpath(HOME))
        self.assertTrue(fs.validpath(HOME + '/'))
        self.assertFalse(fs.validpath(HOME + 'bar'))

    if hasattr(os, 'symlink'):

        def test_validpath_validlink(self):
            # Test validpath by issuing a symlink pointing to a path
            # inside the root directory.
            testfn = self.get_testfn()
            testfn2 = self.get_testfn()
            fs = AbstractedFS(u('/'), None)
            fs._root = HOME
            touch(testfn)
            os.symlink(testfn, testfn2)
            self.assertTrue(fs.validpath(u(testfn)))

        def test_validpath_external_symlink(self):
            # Test validpath by issuing a symlink pointing to a path
            # outside the root directory.
            fs = AbstractedFS(u('/'), None)
            fs._root = HOME
            # tempfile should create our file in /tmp directory
            # which should be outside the user root.  If it is
            # not we just skip the test.
            testfn = self.get_testfn()
            with tempfile.NamedTemporaryFile() as file:
                try:
                    if os.path.dirname(file.name) == HOME:
                        return
                    os.symlink(file.name, testfn)
                    self.assertFalse(fs.validpath(u(testfn)))
                finally:
                    safe_rmpath(testfn)


@unittest.skipUnless(POSIX, "UNIX only")
class TestUnixFilesystem(PyftpdlibTestCase):

    def test_case(self):
        root = getcwdu()
        fs = UnixFilesystem(root, None)
        self.assertEqual(fs.root, root)
        self.assertEqual(fs.cwd, root)
        cdup = os.path.dirname(root)
        self.assertEqual(fs.ftp2fs(u('..')), cdup)
        self.assertEqual(fs.fs2ftp(root), root)


if __name__ == '__main__':
    from pyftpdlib.test.runner import run_from_name
    run_from_name(__file__)
