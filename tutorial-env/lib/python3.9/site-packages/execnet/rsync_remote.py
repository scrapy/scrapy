"""
(c) 2006-2013, Armin Rigo, Holger Krekel, Maciej Fijalkowski
"""


def serve_rsync(channel):
    import os
    import stat
    import shutil
    from hashlib import md5

    destdir, options = channel.receive()
    modifiedfiles = []

    def remove(path):
        assert path.startswith(destdir)
        try:
            os.unlink(path)
        except OSError:
            # assume it's a dir
            shutil.rmtree(path, True)

    def receive_directory_structure(path, relcomponents):
        try:
            st = os.lstat(path)
        except OSError:
            st = None
        msg = channel.receive()
        if isinstance(msg, list):
            if st and not stat.S_ISDIR(st.st_mode):
                os.unlink(path)
                st = None
            if not st:
                os.makedirs(path)
            mode = msg.pop(0)
            if mode:
                # Ensure directories are writable, otherwise a
                # permission denied error (EACCES) would be raised
                # when attempting to receive read-only directory
                # structures.
                os.chmod(path, mode | 0o700)
            entrynames = {}
            for entryname in msg:
                destpath = os.path.join(path, entryname)
                receive_directory_structure(destpath, relcomponents + [entryname])
                entrynames[entryname] = True
            if options.get("delete"):
                for othername in os.listdir(path):
                    if othername not in entrynames:
                        otherpath = os.path.join(path, othername)
                        remove(otherpath)
        elif msg is not None:
            assert isinstance(msg, tuple)
            checksum = None
            if st:
                if stat.S_ISREG(st.st_mode):
                    msg_mode, msg_mtime, msg_size = msg
                    if msg_size != st.st_size:
                        pass
                    elif msg_mtime != st.st_mtime:
                        f = open(path, "rb")
                        checksum = md5(f.read()).digest()
                        f.close()
                    elif msg_mode and msg_mode != st.st_mode:
                        os.chmod(path, msg_mode | 0o700)
                        return
                    else:
                        return  # already fine
                else:
                    remove(path)
            channel.send(("send", (relcomponents, checksum)))
            modifiedfiles.append((path, msg))

    receive_directory_structure(destdir, [])

    STRICT_CHECK = False  # seems most useful this way for py.test
    channel.send(("list_done", None))

    for path, (mode, time, size) in modifiedfiles:
        data = channel.receive()
        channel.send(("ack", path[len(destdir) + 1 :]))
        if data is not None:
            if STRICT_CHECK and len(data) != size:
                raise OSError(f"file modified during rsync: {path!r}")
            f = open(path, "wb")
            f.write(data)
            f.close()
        try:
            if mode:
                os.chmod(path, mode)
            os.utime(path, (time, time))
        except OSError:
            pass
        del data
    channel.send(("links", None))

    msg = channel.receive()
    while msg != 42:
        # we get symlink
        _type, relpath, linkpoint = msg
        path = os.path.join(destdir, relpath)
        try:
            remove(path)
        except OSError:
            pass
        if _type == "linkbase":
            src = os.path.join(destdir, linkpoint)
        else:
            assert _type == "link", _type
            src = linkpoint
        os.symlink(src, path)
        msg = channel.receive()
    channel.send(("done", None))


if __name__ == "__channelexec__":
    serve_rsync(channel)  # type: ignore[name-defined]
