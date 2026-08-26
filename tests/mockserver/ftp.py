from __future__ import annotations

import re
import sys
from argparse import ArgumentParser
from pathlib import Path
from shutil import rmtree
from subprocess import PIPE, Popen
from tempfile import mkdtemp
from typing import TYPE_CHECKING

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler, TLS_FTPHandler
from pyftpdlib.servers import FTPServer

from tests.utils import get_script_run_env

if TYPE_CHECKING:
    from types import TracebackType

    # typing.Self requires Python 3.11
    from typing_extensions import Self


class MockFTPServer:
    """Creates an FTP server on a random port with a default passwordless user
    (anonymous) and a temporary root path that you can read from the
    :attr:`path` attribute.

    If *tls* is ``True``, the server requires FTPS, using the test certificate
    from :file:`tests/keys`.
    """

    proc: Popen[str]
    port: int
    path: Path

    def __init__(self, tls: bool = False) -> None:
        self.host: str = "127.0.0.1"
        self.tls: bool = tls

    def __enter__(self) -> Self:
        self.path = Path(mkdtemp())
        self.proc = Popen(
            [sys.executable, "-u", "-m", "tests.mockserver.ftp", "-d", str(self.path)]
            + (["--tls"] if self.tls else []),
            stderr=PIPE,
            env=get_script_run_env(),
            text=True,
        )
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            if m := re.search(r"starting FTPS? .*on ([^ :]+):(\d+),", line):
                self.port = int(m.group(2))
                break
        else:
            self.proc.kill()
            self.proc.communicate()
            raise RuntimeError(
                "The FTP server failed to start or the output is unrecognized"
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        rmtree(str(self.path))
        self.proc.kill()
        self.proc.communicate()

    def url(self, path: str) -> str:
        scheme = "ftps" if self.tls else "ftp"
        return f"{scheme}://{self.host}:{self.port}/{path}"


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("-d", "--directory", required=True)
    parser.add_argument("--tls", action="store_true")
    args = parser.parse_args()

    authorizer = DummyAuthorizer()
    full_permissions = "elradfmwMT"
    authorizer.add_anonymous(args.directory, perm=full_permissions)
    if args.tls:
        keys = Path(__file__).parent.parent / "keys"
        handler = TLS_FTPHandler
        handler.certfile = str(keys / "localhost.crt")
        handler.keyfile = str(keys / "localhost.key")
        handler.tls_control_required = True
        handler.tls_data_required = True
    else:
        handler = FTPHandler
    handler.authorizer = authorizer
    address = ("127.0.0.1", 0)
    server = FTPServer(address, handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
