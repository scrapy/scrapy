# -*- test-case-name: twisted.python.test.test_fakepwd -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
L{twisted.python.fakepwd} provides a fake implementation of the L{pwd} API.
"""

from __future__ import absolute_import, division

__all__ = ['UserDatabase', 'ShadowDatabase']


class _UserRecord(object):
    """
    L{_UserRecord} holds the user data for a single user in L{UserDatabase}.
    It corresponds to L{pwd.struct_passwd}.  See that class for attribute
    documentation.
    """
    def __init__(self, name, password, uid, gid, gecos, home, shell):
        self.pw_name = name
        self.pw_passwd = password
        self.pw_uid = uid
        self.pw_gid = gid
        self.pw_gecos = gecos
        self.pw_dir = home
        self.pw_shell = shell


    def __len__(self):
        return 7


    def __getitem__(self, index):
        return (
            self.pw_name, self.pw_passwd, self.pw_uid,
            self.pw_gid, self.pw_gecos, self.pw_dir, self.pw_shell)[index]



class UserDatabase(object):
    """
    L{UserDatabase} holds a traditional POSIX user data in memory and makes it
    available via the same API as L{pwd}.

    @ivar _users: A C{list} of L{_UserRecord} instances holding all user data
        added to this database.
    """
    def __init__(self):
        self._users = []


    def addUser(self, username, password, uid, gid, gecos, home, shell):
        """
        Add a new user record to this database.

        @param username: The value for the C{pw_name} field of the user
            record to add.
        @type username: C{str}

        @param password: The value for the C{pw_passwd} field of the user
            record to add.
        @type password: C{str}

        @param uid: The value for the C{pw_uid} field of the user record to
            add.
        @type uid: C{int}

        @param gid: The value for the C{pw_gid} field of the user record to
            add.
        @type gid: C{int}

        @param gecos: The value for the C{pw_gecos} field of the user record
            to add.
        @type gecos: C{str}

        @param home: The value for the C{pw_dir} field of the user record to
            add.
        @type home: C{str}

        @param shell: The value for the C{pw_shell} field of the user record to
            add.
        @type shell: C{str}
        """
        self._users.append(_UserRecord(
            username, password, uid, gid, gecos, home, shell))


    def getpwuid(self, uid):
        """
        Return the user record corresponding to the given uid.
        """
        for entry in self._users:
            if entry.pw_uid == uid:
                return entry
        raise KeyError()


    def getpwnam(self, name):
        """
        Return the user record corresponding to the given username.
        """
        for entry in self._users:
            if entry.pw_name == name:
                return entry
        raise KeyError()


    def getpwall(self):
        """
        Return a list of all user records.
        """
        return self._users



class _ShadowRecord(object):
    """
    L{_ShadowRecord} holds the shadow user data for a single user in
    L{ShadowDatabase}.  It corresponds to C{spwd.struct_spwd}.  See that class
    for attribute documentation.
    """
    def __init__(self, username, password, lastChange, min, max, warn, inact,
                 expire, flag):
        self.sp_nam = username
        self.sp_pwd = password
        self.sp_lstchg = lastChange
        self.sp_min = min
        self.sp_max = max
        self.sp_warn = warn
        self.sp_inact = inact
        self.sp_expire = expire
        self.sp_flag = flag


    def __len__(self):
        return 9


    def __getitem__(self, index):
        return (
            self.sp_nam, self.sp_pwd, self.sp_lstchg, self.sp_min,
            self.sp_max, self.sp_warn, self.sp_inact, self.sp_expire,
            self.sp_flag)[index]



class ShadowDatabase(object):
    """
    L{ShadowDatabase} holds a shadow user database in memory and makes it
    available via the same API as C{spwd}.

    @ivar _users: A C{list} of L{_ShadowRecord} instances holding all user data
        added to this database.

    @since: 12.0
    """
    def __init__(self):
        self._users = []


    def addUser(self, username, password, lastChange, min, max, warn, inact,
                expire, flag):
        """
        Add a new user record to this database.

        @param username: The value for the C{sp_nam} field of the user record to
            add.
        @type username: C{str}

        @param password: The value for the C{sp_pwd} field of the user record to
            add.
        @type password: C{str}

        @param lastChange: The value for the C{sp_lstchg} field of the user
            record to add.
        @type lastChange: C{int}

        @param min: The value for the C{sp_min} field of the user record to add.
        @type min: C{int}

        @param max: The value for the C{sp_max} field of the user record to add.
        @type max: C{int}

        @param warn: The value for the C{sp_warn} field of the user record to
            add.
        @type warn: C{int}

        @param inact: The value for the C{sp_inact} field of the user record to
            add.
        @type inact: C{int}

        @param expire: The value for the C{sp_expire} field of the user record
            to add.
        @type expire: C{int}

        @param flag: The value for the C{sp_flag} field of the user record to
            add.
        @type flag: C{int}
        """
        self._users.append(_ShadowRecord(
                username, password, lastChange,
                min, max, warn, inact, expire, flag))


    def getspnam(self, username):
        """
        Return the shadow user record corresponding to the given username.
        """
        for entry in self._users:
            if entry.sp_nam == username:
                return entry
        raise KeyError


    def getspall(self):
        """
        Return a list of all shadow user records.
        """
        return self._users
