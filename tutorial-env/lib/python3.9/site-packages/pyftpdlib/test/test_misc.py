# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

import logging
import os
import sys
import warnings


try:
    from StringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO

import pyftpdlib
import pyftpdlib.__main__
from pyftpdlib._compat import PY3
from pyftpdlib._compat import super
from pyftpdlib.servers import FTPServer
from pyftpdlib.test import PyftpdlibTestCase
from pyftpdlib.test import mock
from pyftpdlib.test import safe_rmpath


class TestCommandLineParser(PyftpdlibTestCase):
    """Test command line parser."""
    SYSARGV = sys.argv
    STDERR = sys.stderr

    def setUp(self):
        super().setUp()

        class DummyFTPServer(FTPServer):
            """An overridden version of FTPServer class which forces
            serve_forever() to return immediately.
            """

            def serve_forever(self, *args, **kwargs):
                return

        if PY3:
            import io
            self.devnull = io.StringIO()
        else:
            self.devnull = BytesIO()
        sys.argv = self.SYSARGV[:]
        sys.stderr = self.STDERR
        self.original_ftpserver_class = FTPServer
        pyftpdlib.__main__.FTPServer = DummyFTPServer

    def tearDown(self):
        self.devnull.close()
        sys.argv = self.SYSARGV[:]
        sys.stderr = self.STDERR
        pyftpdlib.servers.FTPServer = self.original_ftpserver_class
        super().tearDown()

    def test_a_option(self):
        sys.argv += ["-i", "localhost", "-p", "0"]
        pyftpdlib.__main__.main()
        sys.argv = self.SYSARGV[:]

        # no argument
        sys.argv += ["-a"]
        sys.stderr = self.devnull
        self.assertRaises(SystemExit, pyftpdlib.__main__.main)

    def test_p_option(self):
        sys.argv += ["-p", "0"]
        pyftpdlib.__main__.main()

        # no argument
        sys.argv = self.SYSARGV[:]
        sys.argv += ["-p"]
        sys.stderr = self.devnull
        self.assertRaises(SystemExit, pyftpdlib.__main__.main)

        # invalid argument
        sys.argv += ["-p foo"]
        self.assertRaises(SystemExit, pyftpdlib.__main__.main)

    def test_w_option(self):
        sys.argv += ["-w", "-p", "0"]
        with warnings.catch_warnings():
            warnings.filterwarnings("error")
            self.assertRaises(RuntimeWarning, pyftpdlib.__main__.main)

        # unexpected argument
        sys.argv = self.SYSARGV[:]
        sys.argv += ["-w foo"]
        sys.stderr = self.devnull
        self.assertRaises(SystemExit, pyftpdlib.__main__.main)

    def test_d_option(self):
        dirname = self.get_testfn()
        os.mkdir(dirname)
        sys.argv += ["-d", dirname, "-p", "0"]
        pyftpdlib.__main__.main()

        # without argument
        sys.argv = self.SYSARGV[:]
        sys.argv += ["-d"]
        sys.stderr = self.devnull
        self.assertRaises(SystemExit, pyftpdlib.__main__.main)

        # no such directory
        sys.argv = self.SYSARGV[:]
        sys.argv += ["-d %s" % dirname]
        safe_rmpath(dirname)
        self.assertRaises(ValueError, pyftpdlib.__main__.main)

    def test_r_option(self):
        sys.argv += ["-r 60000-61000", "-p", "0"]
        pyftpdlib.__main__.main()

        # without arg
        sys.argv = self.SYSARGV[:]
        sys.argv += ["-r"]
        sys.stderr = self.devnull
        self.assertRaises(SystemExit, pyftpdlib.__main__.main)

        # wrong arg
        sys.argv = self.SYSARGV[:]
        sys.argv += ["-r yyy-zzz"]
        self.assertRaises(SystemExit, pyftpdlib.__main__.main)

    def test_v_option(self):
        sys.argv += ["-v"]
        self.assertRaises(SystemExit, pyftpdlib.__main__.main)

        # unexpected argument
        sys.argv = self.SYSARGV[:]
        sys.argv += ["-v foo"]
        sys.stderr = self.devnull
        self.assertRaises(SystemExit, pyftpdlib.__main__.main)

    def test_D_option(self):
        with mock.patch('pyftpdlib.__main__.config_logging') as fun:
            sys.argv += ["-D", "-p 0"]
            pyftpdlib.__main__.main()
            fun.assert_called_once_with(level=logging.DEBUG)

        # unexpected argument
        sys.argv = self.SYSARGV[:]
        sys.argv += ["-V foo"]
        sys.stderr = self.devnull
        self.assertRaises(SystemExit, pyftpdlib.__main__.main)


if __name__ == '__main__':
    from pyftpdlib.test.runner import run_from_name
    run_from_name(__file__)
