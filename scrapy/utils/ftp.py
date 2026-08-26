import posixpath
from contextlib import closing
from ftplib import FTP, FTP_TLS, error_perm
from posixpath import dirname
from ssl import create_default_context
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
    tls: bool = False,
) -> None:
    """Opens a FTP connection with passed credentials, sets current directory
    to the directory extracted from given path, then uploads the file to server.

    If *tls* is ``True``, the connection is secured with TLS (FTPS), and the
    certificate of the server is verified.
    """
    ftp = FTP_TLS(context=create_default_context()) if tls else FTP()
    with ftp, closing(file):
        ftp.connect(host, port)
        ftp.login(username, password)
        if isinstance(ftp, FTP_TLS):
            ftp.prot_p()
        if use_active_mode:
            ftp.set_pasv(False)
        file.seek(0)
        dirname, filename = posixpath.split(path)
        ftp_makedirs_cwd(ftp, dirname)
        command = "STOR" if overwrite else "APPE"
        ftp.storbinary(f"{command} {filename}", file)
