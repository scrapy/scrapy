from posixpath import dirname


def sftp_makedirs(sftp, path):
    """Creates the `path` directory and its parent directories if they do not
    exist. The `sftp` parameter must be an already connected and logged in
    paramiko.SFTPClient object.
    """
    path = path.rstrip("/")
    cwd = sftp.getcwd()  # Remember the current working dir
    try:
        sftp.chdir(path)
    except IOError:
        # Directory `path` does not exist yet.
        sftp_makedirs(sftp, dirname(path))  # Make parent directories
        sftp.mkdir(path)  # Make directory
    sftp.chdir(cwd)  # Restore the original working directory.
