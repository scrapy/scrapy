# -*- test-case-name: twisted.conch.test.test_cftp -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

import array
import stat
from time import localtime, strftime, time

# Locale-independent month names to use instead of strftime's
_MONTH_NAMES = dict(
    list(
        zip(
            list(range(1, 13)),
            "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(),
        )
    )
)


def lsLine(name, s):
    """
    Build an 'ls' line for a file ('file' in its generic sense, it
    can be of any type).
    """
    mode = s.st_mode
    perms = array.array("B", b"-" * 10)
    ft = stat.S_IFMT(mode)
    if stat.S_ISDIR(ft):
        perms[0] = ord("d")
    elif stat.S_ISCHR(ft):
        perms[0] = ord("c")
    elif stat.S_ISBLK(ft):
        perms[0] = ord("b")
    elif stat.S_ISREG(ft):
        perms[0] = ord("-")
    elif stat.S_ISFIFO(ft):
        perms[0] = ord("f")
    elif stat.S_ISLNK(ft):
        perms[0] = ord("l")
    elif stat.S_ISSOCK(ft):
        perms[0] = ord("s")
    else:
        perms[0] = ord("!")
    # User
    if mode & stat.S_IRUSR:
        perms[1] = ord("r")
    if mode & stat.S_IWUSR:
        perms[2] = ord("w")
    if mode & stat.S_IXUSR:
        perms[3] = ord("x")
    # Group
    if mode & stat.S_IRGRP:
        perms[4] = ord("r")
    if mode & stat.S_IWGRP:
        perms[5] = ord("w")
    if mode & stat.S_IXGRP:
        perms[6] = ord("x")
    # Other
    if mode & stat.S_IROTH:
        perms[7] = ord("r")
    if mode & stat.S_IWOTH:
        perms[8] = ord("w")
    if mode & stat.S_IXOTH:
        perms[9] = ord("x")
    # Suid/sgid
    if mode & stat.S_ISUID:
        if perms[3] == ord("x"):
            perms[3] = ord("s")
        else:
            perms[3] = ord("S")
    if mode & stat.S_ISGID:
        if perms[6] == ord("x"):
            perms[6] = ord("s")
        else:
            perms[6] = ord("S")

    if isinstance(name, bytes):
        name = name.decode("utf-8")
    lsPerms = perms.tobytes()
    lsPerms = lsPerms.decode("utf-8")

    lsresult = [
        lsPerms,
        str(s.st_nlink).rjust(5),
        " ",
        str(s.st_uid).ljust(9),
        str(s.st_gid).ljust(9),
        str(s.st_size).rjust(8),
        " ",
    ]
    # Need to specify the month manually, as strftime depends on locale
    ttup = localtime(s.st_mtime)
    sixmonths = 60 * 60 * 24 * 7 * 26
    if s.st_mtime + sixmonths < time():  # Last edited more than 6mo ago
        strtime = strftime("%%s %d  %Y ", ttup)
    else:
        strtime = strftime("%%s %d %H:%M ", ttup)
    lsresult.append(strtime % (_MONTH_NAMES[ttup[1]],))

    lsresult.append(name)
    return "".join(lsresult)


__all__ = ["lsLine"]
