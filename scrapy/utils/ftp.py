from __future__ import annotations

import posixpath
from contextlib import closing
from ftplib import FTP, error_perm
from posixpath import dirname
from typing import IO


def ftp_makedirs_cwd(ftp: FTP, path: str, first_call: bool = True) -> None:
    """Set the current directory of the FTP connection given in the ``ftp``
    argument (as a ftplib.FTP object), creating all parent directories if they
    don't exist. The ftplib.FTP object must be already connected and logged in.
    """
    try:
        ftp.cwd(path)
    except error_perm:
        ftp_makedirs_cwd(ftp, dirname(path), False)
        ftp.mkd(path)
        if first_call:
            ftp.cwd(path)


def _ftp_file_exists_in_cwd(ftp: FTP, filename: str) -> bool:
    try:
        ftp.voidcmd("TYPE I")
        return ftp.size(filename) is not None
    except error_perm:
        # The file does not exist, or the server does not support the SIZE
        # command, or it does not allow us to use it.
        return False


def ftp_store_file(
    *,
    path: str,
    file: IO[bytes],
    host: str,
    port: int,
    username: str,
    password: str,
    use_active_mode: bool = False,
    overwrite: bool = True,
    mode: str | None = None,
) -> None:
    """Opens a FTP connection with passed credentials,sets current directory
    to the directory extracted from given path, then uploads the file to server

    *mode* may be ``"append"``, ``"create"`` or ``"overwrite"``. It takes
    precedence over *overwrite*, which only remains for backward compatibility.

    ``"create"`` is best-effort: FTP has no atomic create-if-absent command, so
    the file is checked for existence right before it is written.
    """
    if mode is None:
        mode = "overwrite" if overwrite else "append"
    with FTP() as ftp, closing(file):
        ftp.connect(host, port)
        ftp.login(username, password)
        if use_active_mode:
            ftp.set_pasv(False)
        file.seek(0)
        dirname, filename = posixpath.split(path)
        ftp_makedirs_cwd(ftp, dirname)
        if mode == "create" and _ftp_file_exists_in_cwd(ftp, filename):
            raise FileExistsError(f"{path} already exists")
        command = "APPE" if mode == "append" else "STOR"
        ftp.storbinary(f"{command} {filename}", file)
