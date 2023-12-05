# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

"""An "authorizer" is a class handling authentications and permissions
of the FTP server. It is used by pyftpdlib.handlers.FTPHandler
class for:

- verifying user password
- getting user home directory
- checking user permissions when a filesystem read/write event occurs
- changing user when accessing the filesystem

DummyAuthorizer is the main class which handles virtual users.

UnixAuthorizer and WindowsAuthorizer are platform specific and
interact with UNIX and Windows password database.
"""


import errno
import os
import warnings

from ._compat import PY3
from ._compat import getcwdu
from ._compat import unicode


__all__ = ['DummyAuthorizer',
           # 'BaseUnixAuthorizer', 'UnixAuthorizer',
           # 'BaseWindowsAuthorizer', 'WindowsAuthorizer',
           ]


# ===================================================================
# --- exceptions
# ===================================================================

class AuthorizerError(Exception):
    """Base class for authorizer exceptions."""


class AuthenticationFailed(Exception):
    """Exception raised when authentication fails for any reason."""


# ===================================================================
# --- base class
# ===================================================================

class DummyAuthorizer:
    """Basic "dummy" authorizer class, suitable for subclassing to
    create your own custom authorizers.

    An "authorizer" is a class handling authentications and permissions
    of the FTP server.  It is used inside FTPHandler class for verifying
    user's password, getting users home directory, checking user
    permissions when a file read/write event occurs and changing user
    before accessing the filesystem.

    DummyAuthorizer is the base authorizer, providing a platform
    independent interface for managing "virtual" FTP users. System
    dependent authorizers can by written by subclassing this base
    class and overriding appropriate methods as necessary.
    """

    read_perms = "elr"
    write_perms = "adfmwMT"

    def __init__(self):
        self.user_table = {}

    def add_user(self, username, password, homedir, perm='elr',
                 msg_login="Login successful.", msg_quit="Goodbye."):
        """Add a user to the virtual users table.

        AuthorizerError exceptions raised on error conditions such as
        invalid permissions, missing home directory or duplicate usernames.

        Optional perm argument is a string referencing the user's
        permissions explained below:

        Read permissions:
         - "e" = change directory (CWD command)
         - "l" = list files (LIST, NLST, STAT, MLSD, MLST, SIZE, MDTM commands)
         - "r" = retrieve file from the server (RETR command)

        Write permissions:
         - "a" = append data to an existing file (APPE command)
         - "d" = delete file or directory (DELE, RMD commands)
         - "f" = rename file or directory (RNFR, RNTO commands)
         - "m" = create directory (MKD command)
         - "w" = store a file to the server (STOR, STOU commands)
         - "M" = change file mode (SITE CHMOD command)
         - "T" = update file last modified time (MFMT command)

        Optional msg_login and msg_quit arguments can be specified to
        provide customized response strings when user log-in and quit.
        """
        if self.has_user(username):
            raise ValueError('user %r already exists' % username)
        if not isinstance(homedir, unicode):
            homedir = homedir.decode('utf8')
        if not os.path.isdir(homedir):
            raise ValueError('no such directory: %r' % homedir)
        homedir = os.path.realpath(homedir)
        self._check_permissions(username, perm)
        dic = {'pwd': str(password),
               'home': homedir,
               'perm': perm,
               'operms': {},
               'msg_login': str(msg_login),
               'msg_quit': str(msg_quit)
               }
        self.user_table[username] = dic

    def add_anonymous(self, homedir, **kwargs):
        """Add an anonymous user to the virtual users table.

        AuthorizerError exception raised on error conditions such as
        invalid permissions, missing home directory, or duplicate
        anonymous users.

        The keyword arguments in kwargs are the same expected by
        add_user method: "perm", "msg_login" and "msg_quit".

        The optional "perm" keyword argument is a string defaulting to
        "elr" referencing "read-only" anonymous user's permissions.

        Using write permission values ("adfmwM") results in a
        RuntimeWarning.
        """
        DummyAuthorizer.add_user(self, 'anonymous', '', homedir, **kwargs)

    def remove_user(self, username):
        """Remove a user from the virtual users table."""
        del self.user_table[username]

    def override_perm(self, username, directory, perm, recursive=False):
        """Override permissions for a given directory."""
        self._check_permissions(username, perm)
        if not os.path.isdir(directory):
            raise ValueError('no such directory: %r' % directory)
        directory = os.path.normcase(os.path.realpath(directory))
        home = os.path.normcase(self.get_home_dir(username))
        if directory == home:
            raise ValueError("can't override home directory permissions")
        if not self._issubpath(directory, home):
            raise ValueError("path escapes user home directory")
        self.user_table[username]['operms'][directory] = perm, recursive

    def validate_authentication(self, username, password, handler):
        """Raises AuthenticationFailed if supplied username and
        password don't match the stored credentials, else return
        None.
        """
        msg = "Authentication failed."
        if not self.has_user(username):
            if username == 'anonymous':
                msg = "Anonymous access not allowed."
            raise AuthenticationFailed(msg)
        if username != 'anonymous':
            if self.user_table[username]['pwd'] != password:
                raise AuthenticationFailed(msg)

    def get_home_dir(self, username):
        """Return the user's home directory.
        Since this is called during authentication (PASS),
        AuthenticationFailed can be freely raised by subclasses in case
        the provided username no longer exists.
        """
        return self.user_table[username]['home']

    def impersonate_user(self, username, password):
        """Impersonate another user (noop).

        It is always called before accessing the filesystem.
        By default it does nothing.  The subclass overriding this
        method is expected to provide a mechanism to change the
        current user.
        """

    def terminate_impersonation(self, username):
        """Terminate impersonation (noop).

        It is always called after having accessed the filesystem.
        By default it does nothing.  The subclass overriding this
        method is expected to provide a mechanism to switch back
        to the original user.
        """

    def has_user(self, username):
        """Whether the username exists in the virtual users table."""
        return username in self.user_table

    def has_perm(self, username, perm, path=None):
        """Whether the user has permission over path (an absolute
        pathname of a file or a directory).

        Expected perm argument is one of the following letters:
        "elradfmwMT".
        """
        if path is None:
            return perm in self.user_table[username]['perm']

        path = os.path.normcase(path)
        for dir in self.user_table[username]['operms']:
            operm, recursive = self.user_table[username]['operms'][dir]
            if self._issubpath(path, dir):
                if recursive:
                    return perm in operm
                if (path == dir or os.path.dirname(path) == dir and not
                        os.path.isdir(path)):
                    return perm in operm

        return perm in self.user_table[username]['perm']

    def get_perms(self, username):
        """Return current user permissions."""
        return self.user_table[username]['perm']

    def get_msg_login(self, username):
        """Return the user's login message."""
        return self.user_table[username]['msg_login']

    def get_msg_quit(self, username):
        """Return the user's quitting message."""
        try:
            return self.user_table[username]['msg_quit']
        except KeyError:
            return "Goodbye."

    def _check_permissions(self, username, perm):
        warned = 0
        for p in perm:
            if p not in self.read_perms + self.write_perms:
                raise ValueError('no such permission %r' % p)
            if username == 'anonymous' and \
                    p in self.write_perms and not \
                    warned:
                warnings.warn("write permissions assigned to anonymous user.",
                              RuntimeWarning, stacklevel=2)
                warned = 1

    def _issubpath(self, a, b):
        """Return True if a is a sub-path of b or if the paths are equal."""
        p1 = a.rstrip(os.sep).split(os.sep)
        p2 = b.rstrip(os.sep).split(os.sep)
        return p1[:len(p2)] == p2


def replace_anonymous(callable):
    """A decorator to replace anonymous user string passed to authorizer
    methods as first argument with the actual user used to handle
    anonymous sessions.
    """

    def wrapper(self, username, *args, **kwargs):
        if username == 'anonymous':
            username = self.anonymous_user or username
        return callable(self, username, *args, **kwargs)
    return wrapper


# ===================================================================
# --- platform specific authorizers
# ===================================================================

class _Base:
    """Methods common to both Unix and Windows authorizers.
    Not supposed to be used directly.
    """

    msg_no_such_user = "Authentication failed."
    msg_wrong_password = "Authentication failed."
    msg_anon_not_allowed = "Anonymous access not allowed."
    msg_invalid_shell = "User %s doesn't have a valid shell."
    msg_rejected_user = "User %s is not allowed to login."

    def __init__(self):
        """Check for errors in the constructor."""
        if self.rejected_users and self.allowed_users:
            raise AuthorizerError("rejected_users and allowed_users options "
                                  "are mutually exclusive")

        users = self._get_system_users()
        for user in (self.allowed_users or self.rejected_users):
            if user == 'anonymous':
                raise AuthorizerError('invalid username "anonymous"')
            if user not in users:
                raise AuthorizerError('unknown user %s' % user)

        if self.anonymous_user is not None:
            if not self.has_user(self.anonymous_user):
                raise AuthorizerError('no such user %s' % self.anonymous_user)
            home = self.get_home_dir(self.anonymous_user)
            if not os.path.isdir(home):
                raise AuthorizerError('no valid home set for user %s'
                                      % self.anonymous_user)

    def override_user(self, username, password=None, homedir=None, perm=None,
                      msg_login=None, msg_quit=None):
        """Overrides the options specified in the class constructor
        for a specific user.
        """
        if (not password and not homedir and not perm and not msg_login and not
                msg_quit):
            raise AuthorizerError(
                "at least one keyword argument must be specified")
        if self.allowed_users and username not in self.allowed_users:
            raise AuthorizerError('%s is not an allowed user' % username)
        if self.rejected_users and username in self.rejected_users:
            raise AuthorizerError('%s is not an allowed user' % username)
        if username == "anonymous" and password:
            raise AuthorizerError("can't assign password to anonymous user")
        if not self.has_user(username):
            raise AuthorizerError('no such user %s' % username)
        if homedir is not None and not isinstance(homedir, unicode):
            homedir = homedir.decode('utf8')

        if username in self._dummy_authorizer.user_table:
            # re-set parameters
            del self._dummy_authorizer.user_table[username]
        self._dummy_authorizer.add_user(username,
                                        password or "",
                                        homedir or getcwdu(),
                                        perm or "",
                                        msg_login or "",
                                        msg_quit or "")
        if homedir is None:
            self._dummy_authorizer.user_table[username]['home'] = ""

    def get_msg_login(self, username):
        return self._get_key(username, 'msg_login') or self.msg_login

    def get_msg_quit(self, username):
        return self._get_key(username, 'msg_quit') or self.msg_quit

    def get_perms(self, username):
        overridden_perms = self._get_key(username, 'perm')
        if overridden_perms:
            return overridden_perms
        if username == 'anonymous':
            return 'elr'
        return self.global_perm

    def has_perm(self, username, perm, path=None):
        return perm in self.get_perms(username)

    def _get_key(self, username, key):
        if self._dummy_authorizer.has_user(username):
            return self._dummy_authorizer.user_table[username][key]

    def _is_rejected_user(self, username):
        """Return True if the user has been black listed via
        allowed_users or rejected_users options.
        """
        if self.allowed_users and username not in self.allowed_users:
            return True
        if self.rejected_users and username in self.rejected_users:
            return True
        return False


# ===================================================================
# --- UNIX
# ===================================================================

try:
    import crypt
    import pwd
    import spwd
except ImportError:
    pass
else:
    __all__.extend(['BaseUnixAuthorizer', 'UnixAuthorizer'])

    # the uid/gid the server runs under
    PROCESS_UID = os.getuid()
    PROCESS_GID = os.getgid()

    class BaseUnixAuthorizer:
        """An authorizer compatible with Unix user account and password
        database.
        This class should not be used directly unless for subclassing.
        Use higher-level UnixAuthorizer class instead.
        """

        def __init__(self, anonymous_user=None):
            if os.geteuid() != 0 or not spwd.getspall():
                raise AuthorizerError("super user privileges are required")
            self.anonymous_user = anonymous_user

            if self.anonymous_user is not None:
                try:
                    pwd.getpwnam(self.anonymous_user).pw_dir  # noqa
                except KeyError:
                    raise AuthorizerError('no such user %s' % anonymous_user)

        # --- overridden / private API

        def validate_authentication(self, username, password, handler):
            """Authenticates against shadow password db; raises
            AuthenticationFailed in case of failed authentication.
            """
            if username == "anonymous":
                if self.anonymous_user is None:
                    raise AuthenticationFailed(self.msg_anon_not_allowed)
            else:
                try:
                    pw1 = spwd.getspnam(username).sp_pwd
                    pw2 = crypt.crypt(password, pw1)
                except KeyError:  # no such username
                    raise AuthenticationFailed(self.msg_no_such_user)
                else:
                    if pw1 != pw2:
                        raise AuthenticationFailed(self.msg_wrong_password)

        @replace_anonymous
        def impersonate_user(self, username, password):
            """Change process effective user/group ids to reflect
            logged in user.
            """
            try:
                pwdstruct = pwd.getpwnam(username)
            except KeyError:
                raise AuthorizerError(self.msg_no_such_user)
            else:
                os.setegid(pwdstruct.pw_gid)
                os.seteuid(pwdstruct.pw_uid)

        def terminate_impersonation(self, username):
            """Revert process effective user/group IDs."""
            os.setegid(PROCESS_GID)
            os.seteuid(PROCESS_UID)

        @replace_anonymous
        def has_user(self, username):
            """Return True if user exists on the Unix system.
            If the user has been black listed via allowed_users or
            rejected_users options always return False.
            """
            return username in self._get_system_users()

        @replace_anonymous
        def get_home_dir(self, username):
            """Return user home directory."""
            try:
                home = pwd.getpwnam(username).pw_dir
            except KeyError:
                raise AuthorizerError(self.msg_no_such_user)
            else:
                if not PY3:
                    home = home.decode('utf8')
                return home

        @staticmethod
        def _get_system_users():
            """Return all users defined on the UNIX system."""
            # there should be no need to convert usernames to unicode
            # as UNIX does not allow chars outside of ASCII set
            return [entry.pw_name for entry in pwd.getpwall()]

        def get_msg_login(self, username):
            return "Login successful."

        def get_msg_quit(self, username):
            return "Goodbye."

        def get_perms(self, username):
            return "elradfmwMT"

        def has_perm(self, username, perm, path=None):
            return perm in self.get_perms(username)

    class UnixAuthorizer(_Base, BaseUnixAuthorizer):
        """A wrapper on top of BaseUnixAuthorizer providing options
        to specify what users should be allowed to login, per-user
        options, etc.

        Example usages:

         >>> from pyftpdlib.authorizers import UnixAuthorizer
         >>> # accept all except root
         >>> auth = UnixAuthorizer(rejected_users=["root"])
         >>>
         >>> # accept some users only
         >>> auth = UnixAuthorizer(allowed_users=["matt", "jay"])
         >>>
         >>> # accept everybody and don't care if they have not a valid shell
         >>> auth = UnixAuthorizer(require_valid_shell=False)
         >>>
         >>> # set specific options for a user
         >>> auth.override_user("matt", password="foo", perm="elr")
        """

        # --- public API

        def __init__(self, global_perm="elradfmwMT",
                     allowed_users=None,
                     rejected_users=None,
                     require_valid_shell=True,
                     anonymous_user=None,
                     msg_login="Login successful.",
                     msg_quit="Goodbye."):
            """Parameters:

             - (string) global_perm:
                a series of letters referencing the users permissions;
                defaults to "elradfmwMT" which means full read and write
                access for everybody (except anonymous).

             - (list) allowed_users:
                a list of users which are accepted for authenticating
                against the FTP server; defaults to [] (no restrictions).

             - (list) rejected_users:
                a list of users which are not accepted for authenticating
                against the FTP server; defaults to [] (no restrictions).

             - (bool) require_valid_shell:
                Deny access for those users which do not have a valid shell
                binary listed in /etc/shells.
                If /etc/shells cannot be found this is a no-op.
                Anonymous user is not subject to this option, and is free
                to not have a valid shell defined.
                Defaults to True (a valid shell is required for login).

             - (string) anonymous_user:
                specify it if you intend to provide anonymous access.
                The value expected is a string representing the system user
                to use for managing anonymous sessions;  defaults to None
                (anonymous access disabled).

             - (string) msg_login:
                the string sent when client logs in.

             - (string) msg_quit:
                the string sent when client quits.
            """
            BaseUnixAuthorizer.__init__(self, anonymous_user)
            if allowed_users is None:
                allowed_users = []
            if rejected_users is None:
                rejected_users = []
            self.global_perm = global_perm
            self.allowed_users = allowed_users
            self.rejected_users = rejected_users
            self.anonymous_user = anonymous_user
            self.require_valid_shell = require_valid_shell
            self.msg_login = msg_login
            self.msg_quit = msg_quit

            self._dummy_authorizer = DummyAuthorizer()
            self._dummy_authorizer._check_permissions('', global_perm)
            _Base.__init__(self)
            if require_valid_shell:
                for username in self.allowed_users:
                    if not self._has_valid_shell(username):
                        raise AuthorizerError("user %s has not a valid shell"
                                              % username)

        def override_user(self, username, password=None, homedir=None,
                          perm=None, msg_login=None, msg_quit=None):
            """Overrides the options specified in the class constructor
            for a specific user.
            """
            if self.require_valid_shell and username != 'anonymous':
                if not self._has_valid_shell(username):
                    raise AuthorizerError(self.msg_invalid_shell % username)
            _Base.override_user(self, username, password, homedir, perm,
                                msg_login, msg_quit)

        # --- overridden / private API

        def validate_authentication(self, username, password, handler):
            if username == "anonymous":
                if self.anonymous_user is None:
                    raise AuthenticationFailed(self.msg_anon_not_allowed)
                return
            if self._is_rejected_user(username):
                raise AuthenticationFailed(self.msg_rejected_user % username)
            overridden_password = self._get_key(username, 'pwd')
            if overridden_password:
                if overridden_password != password:
                    raise AuthenticationFailed(self.msg_wrong_password)
            else:
                BaseUnixAuthorizer.validate_authentication(self, username,
                                                           password, handler)
            if self.require_valid_shell and username != 'anonymous':
                if not self._has_valid_shell(username):
                    raise AuthenticationFailed(
                        self.msg_invalid_shell % username)

        @replace_anonymous
        def has_user(self, username):
            if self._is_rejected_user(username):
                return False
            return username in self._get_system_users()

        @replace_anonymous
        def get_home_dir(self, username):
            overridden_home = self._get_key(username, 'home')
            if overridden_home:
                return overridden_home
            return BaseUnixAuthorizer.get_home_dir(self, username)

        @staticmethod
        def _has_valid_shell(username):
            """Return True if the user has a valid shell binary listed
            in /etc/shells. If /etc/shells can't be found return True.
            """
            try:
                file = open('/etc/shells')
            except IOError as err:
                if err.errno == errno.ENOENT:
                    return True
                raise
            else:
                with file:
                    try:
                        shell = pwd.getpwnam(username).pw_shell
                    except KeyError:  # invalid user
                        return False
                    for line in file:
                        if line.startswith('#'):
                            continue
                        line = line.strip()
                        if line == shell:
                            return True
                    return False


# ===================================================================
# --- Windows
# ===================================================================

# Note: requires pywin32 extension
try:
    import pywintypes
    import win32api
    import win32con
    import win32net
    import win32security
except ImportError:
    pass
else:  # pragma: no cover
    if PY3:
        import winreg
    else:
        import _winreg as winreg

    __all__.extend(['BaseWindowsAuthorizer', 'WindowsAuthorizer'])

    class BaseWindowsAuthorizer:
        """An authorizer compatible with Windows user account and
        password database.
        This class should not be used directly unless for subclassing.
        Use higher-level WinowsAuthorizer class instead.
        """

        def __init__(self, anonymous_user=None, anonymous_password=None):
            # actually try to impersonate the user
            self.anonymous_user = anonymous_user
            self.anonymous_password = anonymous_password
            if self.anonymous_user is not None:
                self.impersonate_user(self.anonymous_user,
                                      self.anonymous_password)
                self.terminate_impersonation(None)

        def validate_authentication(self, username, password, handler):
            if username == "anonymous":
                if self.anonymous_user is None:
                    raise AuthenticationFailed(self.msg_anon_not_allowed)
                return
            try:
                win32security.LogonUser(username, None, password,
                                        win32con.LOGON32_LOGON_INTERACTIVE,
                                        win32con.LOGON32_PROVIDER_DEFAULT)
            except pywintypes.error:
                raise AuthenticationFailed(self.msg_wrong_password)

        @replace_anonymous
        def impersonate_user(self, username, password):
            """Impersonate the security context of another user."""
            handler = win32security.LogonUser(
                username, None, password,
                win32con.LOGON32_LOGON_INTERACTIVE,
                win32con.LOGON32_PROVIDER_DEFAULT)
            win32security.ImpersonateLoggedOnUser(handler)
            handler.Close()

        def terminate_impersonation(self, username):
            """Terminate the impersonation of another user."""
            win32security.RevertToSelf()

        @replace_anonymous
        def has_user(self, username):
            return username in self._get_system_users()

        @replace_anonymous
        def get_home_dir(self, username):
            """Return the user's profile directory, the closest thing
            to a user home directory we have on Windows.
            """
            try:
                sid = win32security.ConvertSidToStringSid(
                    win32security.LookupAccountName(None, username)[0])
            except pywintypes.error as err:
                raise AuthorizerError(err)
            path = r"SOFTWARE\Microsoft\Windows NT"
            path += r"\CurrentVersion\ProfileList" + "\\" + sid
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
            except WindowsError:
                raise AuthorizerError(
                    "No profile directory defined for user %s" % username)
            value = winreg.QueryValueEx(key, "ProfileImagePath")[0]
            home = win32api.ExpandEnvironmentStrings(value)
            if not PY3 and not isinstance(home, unicode):
                home = home.decode('utf8')
            return home

        @classmethod
        def _get_system_users(cls):
            """Return all users defined on the Windows system."""
            # XXX - Does Windows allow usernames with chars outside of
            # ASCII set? In that case we need to convert this to unicode.
            return [entry['name'] for entry in
                    win32net.NetUserEnum(None, 0)[0]]

        def get_msg_login(self, username):
            return "Login successful."

        def get_msg_quit(self, username):
            return "Goodbye."

        def get_perms(self, username):
            return "elradfmwMT"

        def has_perm(self, username, perm, path=None):
            return perm in self.get_perms(username)

    class WindowsAuthorizer(_Base, BaseWindowsAuthorizer):
        """A wrapper on top of BaseWindowsAuthorizer providing options
        to specify what users should be allowed to login, per-user
        options, etc.

        Example usages:

         >>> from pyftpdlib.authorizers import WindowsAuthorizer
         >>> # accept all except Administrator
         >>> auth = WindowsAuthorizer(rejected_users=["Administrator"])
         >>>
         >>> # accept some users only
         >>> auth = WindowsAuthorizer(allowed_users=["matt", "jay"])
         >>>
         >>> # set specific options for a user
         >>> auth.override_user("matt", password="foo", perm="elr")
        """

        # --- public API

        def __init__(self,
                     global_perm="elradfmwMT",
                     allowed_users=None,
                     rejected_users=None,
                     anonymous_user=None,
                     anonymous_password=None,
                     msg_login="Login successful.",
                     msg_quit="Goodbye."):
            """Parameters:

             - (string) global_perm:
                a series of letters referencing the users permissions;
                defaults to "elradfmwMT" which means full read and write
                access for everybody (except anonymous).

             - (list) allowed_users:
                a list of users which are accepted for authenticating
                against the FTP server; defaults to [] (no restrictions).

             - (list) rejected_users:
                a list of users which are not accepted for authenticating
                against the FTP server; defaults to [] (no restrictions).

             - (string) anonymous_user:
                specify it if you intend to provide anonymous access.
                The value expected is a string representing the system user
                to use for managing anonymous sessions.
                As for IIS, it is recommended to use Guest account.
                The common practice is to first enable the Guest user, which
                is disabled by default and then assign an empty password.
                Defaults to None (anonymous access disabled).

             - (string) anonymous_password:
                the password of the user who has been chosen to manage the
                anonymous sessions.  Defaults to None (empty password).

             - (string) msg_login:
                the string sent when client logs in.

             - (string) msg_quit:
                the string sent when client quits.
            """
            if allowed_users is None:
                allowed_users = []
            if rejected_users is None:
                rejected_users = []
            self.global_perm = global_perm
            self.allowed_users = allowed_users
            self.rejected_users = rejected_users
            self.anonymous_user = anonymous_user
            self.anonymous_password = anonymous_password
            self.msg_login = msg_login
            self.msg_quit = msg_quit
            self._dummy_authorizer = DummyAuthorizer()
            self._dummy_authorizer._check_permissions('', global_perm)
            _Base.__init__(self)
            # actually try to impersonate the user
            if self.anonymous_user is not None:
                self.impersonate_user(self.anonymous_user,
                                      self.anonymous_password)
                self.terminate_impersonation(None)

        def override_user(self, username, password=None, homedir=None,
                          perm=None, msg_login=None, msg_quit=None):
            """Overrides the options specified in the class constructor
            for a specific user.
            """
            _Base.override_user(self, username, password, homedir, perm,
                                msg_login, msg_quit)

        # --- overridden / private API

        def validate_authentication(self, username, password, handler):
            """Authenticates against Windows user database; return
            True on success.
            """
            if username == "anonymous":
                if self.anonymous_user is None:
                    raise AuthenticationFailed(self.msg_anon_not_allowed)
                return
            if self.allowed_users and username not in self.allowed_users:
                raise AuthenticationFailed(self.msg_rejected_user % username)
            if self.rejected_users and username in self.rejected_users:
                raise AuthenticationFailed(self.msg_rejected_user % username)

            overridden_password = self._get_key(username, 'pwd')
            if overridden_password:
                if overridden_password != password:
                    raise AuthenticationFailed(self.msg_wrong_password)
            else:
                BaseWindowsAuthorizer.validate_authentication(
                    self, username, password, handler)

        def impersonate_user(self, username, password):
            """Impersonate the security context of another user."""
            if username == "anonymous":
                username = self.anonymous_user or ""
                password = self.anonymous_password or ""
            BaseWindowsAuthorizer.impersonate_user(self, username, password)

        @replace_anonymous
        def has_user(self, username):
            if self._is_rejected_user(username):
                return False
            return username in self._get_system_users()

        @replace_anonymous
        def get_home_dir(self, username):
            overridden_home = self._get_key(username, 'home')
            if overridden_home:
                home = overridden_home
            else:
                home = BaseWindowsAuthorizer.get_home_dir(self, username)
            if not PY3 and not isinstance(home, unicode):
                home = home.decode('utf8')
            return home
