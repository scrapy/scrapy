from __future__ import annotations

import sys
from argparse import ArgumentParser
from pathlib import Path
from shutil import rmtree
from subprocess import PIPE, Popen
from tempfile import mkdtemp

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

from tests.utils import get_script_run_env


class MockFTPServer:
    """Creates an FTP server on port 2121 with a default passwordless user
    (anonymous) and a temporary root path that you can read from the
    :attr:`path` attribute."""

    def __enter__(self):
        self.path = Path(mkdtemp())
        self.proc = Popen(
            [sys.executable, "-u", "-m", "tests.mockserver.ftp", "-d", str(self.path)],
            stderr=PIPE,
            env=get_script_run_env(),
        )
        for line in self.proc.stderr:
            if b"starting FTP server" in line:
                break
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        rmtree(str(self.path))
        self.proc.kill()
        self.proc.communicate()

    def url(self, path):
        return "ftp://127.0.0.1:2121/" + path


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("-d", "--directory")
    args = parser.parse_args()

    authorizer = DummyAuthorizer()
    full_permissions = "elradfmwMT"
    authorizer.add_anonymous(args.directory, perm=full_permissions)
    handler = FTPHandler
    handler.authorizer = authorizer
    address = ("127.0.0.1", 2121)
    server = FTPServer(address, handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
