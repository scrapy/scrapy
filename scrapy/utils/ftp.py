import posixpath

from ftplib import error_perm, FTP
from posixpath import dirname


def ftp_makedirs_cwd(ftp, path, first_call=True):
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
        *, path, file, host, port,
        username, password, use_active_mode=False):
    """Opens a FTP connection with passed credentials,sets current directory
    to the directory extracted from given path, then uploads the file to server
    """
    with FTP() as ftp:
        ftp.connect(host, port)
        ftp.login(username, password)
        if use_active_mode:
            ftp.set_pasv(False)
        file.seek(0)
        dirname, filename = posixpath.split(path)
        ftp_makedirs_cwd(ftp, dirname)
        ftp.storbinary('STOR %s' % filename, file)
