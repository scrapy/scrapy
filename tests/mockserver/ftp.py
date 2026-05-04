from __future__ import annotations

import re
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
    """Creates an FTP server on a random port with a default passwordless user
    (anonymous) and a temporary root path that you can read from the
    :attr:`path` attribute."""

    def __init__(self) -> None:
        self.proc: Popen[str] | None = None
        self.host: str = "127.0.0.1"
        self.port: int | None = None
        self.path: Path | None = None

    def __enter__(self):
        self.path = Path(mkdtemp())
        self.proc = Popen(
            [sys.executable, "-u", "-m", "tests.mockserver.ftp", "-d", str(self.path)],
            stderr=PIPE,
            env=get_script_run_env(),
            text=True,
        )
        for line in self.proc.stderr:
            if "starting FTP server" in line and (
                m := re.search(r"starting FTP server on ([^ :]+):(\d+),", line)
            ):
                self.port = int(m.group(2))
                break
        else:
            self.proc.kill()
            self.proc.communicate()
            raise RuntimeError(
                "The FTP server failed to start or the output is unrecognized"
            )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        rmtree(str(self.path))
        self.proc.kill()
        self.proc.communicate()

    def url(self, path):
        return f"ftp://{self.host}:{self.port}/{path}"


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("-d", "--directory", required=True)
    args = parser.parse_args()

    authorizer = DummyAuthorizer()
    full_permissions = "elradfmwMT"
    authorizer.add_anonymous(args.directory, perm=full_permissions)
    handler = FTPHandler
    handler.authorizer = authorizer
    address = ("127.0.0.1", 0)
    server = FTPServer(address, handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
