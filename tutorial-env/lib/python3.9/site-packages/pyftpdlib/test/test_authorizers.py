# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

import os
import random
import string
import sys
import unittest
import warnings

from pyftpdlib._compat import getcwdu
from pyftpdlib._compat import super
from pyftpdlib._compat import unicode
from pyftpdlib.authorizers import AuthenticationFailed
from pyftpdlib.authorizers import AuthorizerError
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.test import HOME
from pyftpdlib.test import PASSWD
from pyftpdlib.test import POSIX
from pyftpdlib.test import USER
from pyftpdlib.test import WINDOWS
from pyftpdlib.test import PyftpdlibTestCase
from pyftpdlib.test import touch


if POSIX:
    import pwd
    try:
        from pyftpdlib.authorizers import UnixAuthorizer
    except ImportError:
        UnixAuthorizer = None
else:
    UnixAuthorizer = None

if WINDOWS:
    from pywintypes import error as Win32ExtError

    from pyftpdlib.authorizers import WindowsAuthorizer
else:
    WindowsAuthorizer = None


class TestDummyAuthorizer(PyftpdlibTestCase):
    """Tests for DummyAuthorizer class."""

    # temporarily change warnings to exceptions for the purposes of testing
    def setUp(self):
        super().setUp()
        self.tempdir = os.path.abspath(self.get_testfn())
        self.subtempdir = os.path.join(self.tempdir, self.get_testfn())
        self.tempfile = os.path.join(self.tempdir, self.get_testfn())
        self.subtempfile = os.path.join(self.subtempdir, self.get_testfn())
        os.mkdir(self.tempdir)
        os.mkdir(self.subtempdir)
        touch(self.tempfile)
        touch(self.subtempfile)
        warnings.filterwarnings("error")

    def tearDown(self):
        os.remove(self.tempfile)
        os.remove(self.subtempfile)
        os.rmdir(self.subtempdir)
        os.rmdir(self.tempdir)
        warnings.resetwarnings()
        super().tearDown()

    def test_common_methods(self):
        auth = DummyAuthorizer()
        # create user
        auth.add_user(USER, PASSWD, HOME)
        auth.add_anonymous(HOME)
        # check credentials
        auth.validate_authentication(USER, PASSWD, None)
        self.assertRaises(AuthenticationFailed,
                          auth.validate_authentication, USER, 'wrongpwd', None)
        auth.validate_authentication('anonymous', 'foo', None)
        auth.validate_authentication('anonymous', '', None)  # empty passwd
        # remove them
        auth.remove_user(USER)
        auth.remove_user('anonymous')
        # raise exc if user does not exists
        self.assertRaises(KeyError, auth.remove_user, USER)
        # raise exc if path does not exist
        self.assertRaisesRegex(ValueError,
                               'no such directory',
                               auth.add_user, USER, PASSWD, '?:\\')
        self.assertRaisesRegex(ValueError,
                               'no such directory',
                               auth.add_anonymous, '?:\\')
        # raise exc if user already exists
        auth.add_user(USER, PASSWD, HOME)
        auth.add_anonymous(HOME)
        self.assertRaisesRegex(ValueError,
                               'user %r already exists' % USER,
                               auth.add_user, USER, PASSWD, HOME)
        self.assertRaisesRegex(ValueError,
                               "user 'anonymous' already exists",
                               auth.add_anonymous, HOME)
        auth.remove_user(USER)
        auth.remove_user('anonymous')
        # raise on wrong permission
        self.assertRaisesRegex(ValueError,
                               "no such permission",
                               auth.add_user, USER, PASSWD, HOME, perm='?')
        self.assertRaisesRegex(ValueError,
                               "no such permission",
                               auth.add_anonymous, HOME, perm='?')
        # expect warning on write permissions assigned to anonymous user
        for x in "adfmw":
            self.assertRaisesRegex(
                RuntimeWarning,
                "write permissions assigned to anonymous user.",
                auth.add_anonymous, HOME, perm=x)

    def test_override_perm_interface(self):
        auth = DummyAuthorizer()
        auth.add_user(USER, PASSWD, HOME, perm='elr')
        # raise exc if user does not exists
        self.assertRaises(KeyError, auth.override_perm, USER + 'w',
                          HOME, 'elr')
        # raise exc if path does not exist or it's not a directory
        self.assertRaisesRegex(ValueError,
                               'no such directory',
                               auth.override_perm, USER, '?:\\', 'elr')
        self.assertRaisesRegex(ValueError,
                               'no such directory',
                               auth.override_perm, USER, self.tempfile, 'elr')
        # raise on wrong permission
        self.assertRaisesRegex(ValueError,
                               "no such permission", auth.override_perm,
                               USER, HOME, perm='?')
        # expect warning on write permissions assigned to anonymous user
        auth.add_anonymous(HOME)
        for p in "adfmw":
            self.assertRaisesRegex(
                RuntimeWarning,
                "write permissions assigned to anonymous user.",
                auth.override_perm, 'anonymous', HOME, p)
        # raise on attempt to override home directory permissions
        self.assertRaisesRegex(ValueError,
                               "can't override home directory permissions",
                               auth.override_perm, USER, HOME, perm='w')
        # raise on attempt to override a path escaping home directory
        if os.path.dirname(HOME) != HOME:
            self.assertRaisesRegex(ValueError,
                                   "path escapes user home directory",
                                   auth.override_perm, USER,
                                   os.path.dirname(HOME), perm='w')
        # try to re-set an overridden permission
        auth.override_perm(USER, self.tempdir, perm='w')
        auth.override_perm(USER, self.tempdir, perm='wr')

    def test_override_perm_recursive_paths(self):
        auth = DummyAuthorizer()
        auth.add_user(USER, PASSWD, HOME, perm='elr')
        self.assertEqual(auth.has_perm(USER, 'w', self.tempdir), False)
        auth.override_perm(USER, self.tempdir, perm='w', recursive=True)
        self.assertEqual(auth.has_perm(USER, 'w', HOME), False)
        self.assertEqual(auth.has_perm(USER, 'w', self.tempdir), True)
        self.assertEqual(auth.has_perm(USER, 'w', self.tempfile), True)
        self.assertEqual(auth.has_perm(USER, 'w', self.subtempdir), True)
        self.assertEqual(auth.has_perm(USER, 'w', self.subtempfile), True)

        self.assertEqual(auth.has_perm(USER, 'w', HOME + '@'), False)
        self.assertEqual(auth.has_perm(USER, 'w', self.tempdir + '@'), False)
        path = os.path.join(self.tempdir + '@',
                            os.path.basename(self.tempfile))
        self.assertEqual(auth.has_perm(USER, 'w', path), False)
        # test case-sensitiveness
        if (os.name in ('nt', 'ce')) or (sys.platform == 'cygwin'):
            self.assertTrue(auth.has_perm(USER, 'w', self.tempdir.upper()))

    def test_override_perm_not_recursive_paths(self):
        auth = DummyAuthorizer()
        auth.add_user(USER, PASSWD, HOME, perm='elr')
        self.assertEqual(auth.has_perm(USER, 'w', self.tempdir), False)
        auth.override_perm(USER, self.tempdir, perm='w')
        self.assertEqual(auth.has_perm(USER, 'w', HOME), False)
        self.assertEqual(auth.has_perm(USER, 'w', self.tempdir), True)
        self.assertEqual(auth.has_perm(USER, 'w', self.tempfile), True)
        self.assertEqual(auth.has_perm(USER, 'w', self.subtempdir), False)
        self.assertEqual(auth.has_perm(USER, 'w', self.subtempfile), False)

        self.assertEqual(auth.has_perm(USER, 'w', HOME + '@'), False)
        self.assertEqual(auth.has_perm(USER, 'w', self.tempdir + '@'), False)
        path = os.path.join(self.tempdir + '@',
                            os.path.basename(self.tempfile))
        self.assertEqual(auth.has_perm(USER, 'w', path), False)
        # test case-sensitiveness
        if (os.name in ('nt', 'ce')) or (sys.platform == 'cygwin'):
            self.assertEqual(auth.has_perm(USER, 'w', self.tempdir.upper()),
                             True)


class _SharedAuthorizerTests:
    """Tests valid for both UnixAuthorizer and WindowsAuthorizer for
    those parts which share the same API.
    """
    authorizer_class = None
    # --- utils

    def get_users(self):
        return self.authorizer_class._get_system_users()

    @staticmethod
    def get_current_user():
        if POSIX:
            return pwd.getpwuid(os.getuid()).pw_name
        else:
            return os.environ['USERNAME']

    @staticmethod
    def get_current_user_homedir():
        if POSIX:
            return pwd.getpwuid(os.getuid()).pw_dir
        else:
            return os.environ['USERPROFILE']

    def get_nonexistent_user(self):
        # return a user which does not exist on the system
        users = self.get_users()
        letters = string.ascii_lowercase
        while True:
            user = ''.join([random.choice(letters) for i in range(10)])
            if user not in users:
                return user

    def assertRaisesWithMsg(self, excClass, msg, callableObj, *args, **kwargs):
        try:
            callableObj(*args, **kwargs)
        except excClass as err:
            if str(err) == msg:
                return
            raise self.failureException("%s != %s" % (str(err), msg))
        else:
            if hasattr(excClass, '__name__'):
                excName = excClass.__name__
            else:
                excName = str(excClass)
            raise self.failureException("%s not raised" % excName)
    # --- /utils

    def test_get_home_dir(self):
        auth = self.authorizer_class()
        home = auth.get_home_dir(self.get_current_user())
        self.assertIsInstance(home, unicode)
        nonexistent_user = self.get_nonexistent_user()
        self.assertTrue(os.path.isdir(home))
        if auth.has_user('nobody'):
            home = auth.get_home_dir('nobody')
        self.assertRaises(AuthorizerError,
                          auth.get_home_dir, nonexistent_user)

    def test_has_user(self):
        auth = self.authorizer_class()
        current_user = self.get_current_user()
        nonexistent_user = self.get_nonexistent_user()
        self.assertTrue(auth.has_user(current_user))
        self.assertFalse(auth.has_user(nonexistent_user))
        auth = self.authorizer_class(rejected_users=[current_user])
        self.assertFalse(auth.has_user(current_user))

    def test_validate_authentication(self):
        # can't test for actual success in case of valid authentication
        # here as we don't have the user password
        if self.authorizer_class.__name__ == 'UnixAuthorizer':
            auth = self.authorizer_class(require_valid_shell=False)
        else:
            auth = self.authorizer_class()
        current_user = self.get_current_user()
        nonexistent_user = self.get_nonexistent_user()
        self.assertRaises(
            AuthenticationFailed,
            auth.validate_authentication, current_user, 'wrongpasswd', None)
        self.assertRaises(
            AuthenticationFailed,
            auth.validate_authentication, nonexistent_user, 'bar', None)

    def test_impersonate_user(self):
        auth = self.authorizer_class()
        nonexistent_user = self.get_nonexistent_user()
        try:
            if self.authorizer_class.__name__ == 'UnixAuthorizer':
                auth.impersonate_user(self.get_current_user(), '')
                self.assertRaises(
                    AuthorizerError,
                    auth.impersonate_user, nonexistent_user, 'pwd')
            else:
                self.assertRaises(
                    Win32ExtError,
                    auth.impersonate_user, nonexistent_user, 'pwd')
                self.assertRaises(
                    Win32ExtError,
                    auth.impersonate_user, self.get_current_user(), '')
        finally:
            auth.terminate_impersonation('')

    def test_terminate_impersonation(self):
        auth = self.authorizer_class()
        auth.terminate_impersonation('')
        auth.terminate_impersonation('')

    def test_get_perms(self):
        auth = self.authorizer_class(global_perm='elr')
        self.assertIn('r', auth.get_perms(self.get_current_user()))
        self.assertNotIn('w', auth.get_perms(self.get_current_user()))

    def test_has_perm(self):
        auth = self.authorizer_class(global_perm='elr')
        self.assertTrue(auth.has_perm(self.get_current_user(), 'r'))
        self.assertFalse(auth.has_perm(self.get_current_user(), 'w'))

    def test_messages(self):
        auth = self.authorizer_class(msg_login="login", msg_quit="quit")
        self.assertTrue(auth.get_msg_login, "login")
        self.assertTrue(auth.get_msg_quit, "quit")

    def test_error_options(self):
        wrong_user = self.get_nonexistent_user()
        self.assertRaisesWithMsg(
            AuthorizerError,
            "rejected_users and allowed_users options are mutually exclusive",
            self.authorizer_class, allowed_users=['foo'],
            rejected_users=['bar'])
        self.assertRaisesWithMsg(
            AuthorizerError,
            'invalid username "anonymous"',
            self.authorizer_class, allowed_users=['anonymous'])
        self.assertRaisesWithMsg(
            AuthorizerError,
            'invalid username "anonymous"',
            self.authorizer_class, rejected_users=['anonymous'])
        self.assertRaisesWithMsg(
            AuthorizerError,
            'unknown user %s' % wrong_user,
            self.authorizer_class, allowed_users=[wrong_user])
        self.assertRaisesWithMsg(AuthorizerError,
                                 'unknown user %s' % wrong_user,
                                 self.authorizer_class,
                                 rejected_users=[wrong_user])

    def test_override_user_password(self):
        auth = self.authorizer_class()
        user = self.get_current_user()
        auth.override_user(user, password='foo')
        auth.validate_authentication(user, 'foo', None)
        self.assertRaises(AuthenticationFailed, auth.validate_authentication,
                          user, 'bar', None)
        # make sure other settings keep using default values
        self.assertEqual(auth.get_home_dir(user),
                         self.get_current_user_homedir())
        self.assertEqual(auth.get_perms(user), "elradfmwMT")
        self.assertEqual(auth.get_msg_login(user), "Login successful.")
        self.assertEqual(auth.get_msg_quit(user), "Goodbye.")

    def test_override_user_homedir(self):
        auth = self.authorizer_class()
        user = self.get_current_user()
        dir = os.path.dirname(getcwdu())
        auth.override_user(user, homedir=dir)
        self.assertEqual(auth.get_home_dir(user), dir)
        # make sure other settings keep using default values
        # self.assertEqual(auth.get_home_dir(user),
        #                  self.get_current_user_homedir())
        self.assertEqual(auth.get_perms(user), "elradfmwMT")
        self.assertEqual(auth.get_msg_login(user), "Login successful.")
        self.assertEqual(auth.get_msg_quit(user), "Goodbye.")

    def test_override_user_perm(self):
        auth = self.authorizer_class()
        user = self.get_current_user()
        auth.override_user(user, perm="elr")
        self.assertEqual(auth.get_perms(user), "elr")
        # make sure other settings keep using default values
        self.assertEqual(auth.get_home_dir(user),
                         self.get_current_user_homedir())
        # self.assertEqual(auth.get_perms(user), "elradfmwMT")
        self.assertEqual(auth.get_msg_login(user), "Login successful.")
        self.assertEqual(auth.get_msg_quit(user), "Goodbye.")

    def test_override_user_msg_login_quit(self):
        auth = self.authorizer_class()
        user = self.get_current_user()
        auth.override_user(user, msg_login="foo", msg_quit="bar")
        self.assertEqual(auth.get_msg_login(user), "foo")
        self.assertEqual(auth.get_msg_quit(user), "bar")
        # make sure other settings keep using default values
        self.assertEqual(auth.get_home_dir(user),
                         self.get_current_user_homedir())
        self.assertEqual(auth.get_perms(user), "elradfmwMT")
        # self.assertEqual(auth.get_msg_login(user), "Login successful.")
        # self.assertEqual(auth.get_msg_quit(user), "Goodbye.")

    def test_override_user_errors(self):
        if self.authorizer_class.__name__ == 'UnixAuthorizer':
            auth = self.authorizer_class(require_valid_shell=False)
        else:
            auth = self.authorizer_class()
        this_user = self.get_current_user()
        for x in self.get_users():
            if x != this_user:
                another_user = x
                break
        nonexistent_user = self.get_nonexistent_user()
        self.assertRaisesWithMsg(
            AuthorizerError,
            "at least one keyword argument must be specified",
            auth.override_user, this_user)
        self.assertRaisesWithMsg(AuthorizerError,
                                 'no such user %s' % nonexistent_user,
                                 auth.override_user, nonexistent_user,
                                 perm='r')
        if self.authorizer_class.__name__ == 'UnixAuthorizer':
            auth = self.authorizer_class(allowed_users=[this_user],
                                         require_valid_shell=False)
        else:
            auth = self.authorizer_class(allowed_users=[this_user])
        auth.override_user(this_user, perm='r')
        self.assertRaisesWithMsg(AuthorizerError,
                                 '%s is not an allowed user' % another_user,
                                 auth.override_user, another_user, perm='r')
        if self.authorizer_class.__name__ == 'UnixAuthorizer':
            auth = self.authorizer_class(rejected_users=[this_user],
                                         require_valid_shell=False)
        else:
            auth = self.authorizer_class(rejected_users=[this_user])
        auth.override_user(another_user, perm='r')
        self.assertRaisesWithMsg(AuthorizerError,
                                 '%s is not an allowed user' % this_user,
                                 auth.override_user, this_user, perm='r')
        self.assertRaisesWithMsg(AuthorizerError,
                                 "can't assign password to anonymous user",
                                 auth.override_user, "anonymous",
                                 password='foo')


# =====================================================================
# --- UNIX authorizer
# =====================================================================


@unittest.skipUnless(POSIX, "UNIX only")
@unittest.skipUnless(UnixAuthorizer is not None,
                     "UnixAuthorizer class not available")
class TestUnixAuthorizer(_SharedAuthorizerTests, PyftpdlibTestCase):
    """Unix authorizer specific tests."""

    authorizer_class = UnixAuthorizer

    def setUp(self):
        super().setUp()
        try:
            UnixAuthorizer()
        except AuthorizerError:  # not root
            self.skipTest("need root access")

    def test_get_perms_anonymous(self):
        auth = UnixAuthorizer(
            global_perm='elr', anonymous_user=self.get_current_user())
        self.assertIn('e', auth.get_perms('anonymous'))
        self.assertNotIn('w', auth.get_perms('anonymous'))
        warnings.filterwarnings("ignore")
        auth.override_user('anonymous', perm='w')
        warnings.resetwarnings()
        self.assertIn('w', auth.get_perms('anonymous'))

    def test_has_perm_anonymous(self):
        auth = UnixAuthorizer(
            global_perm='elr', anonymous_user=self.get_current_user())
        self.assertTrue(auth.has_perm(self.get_current_user(), 'r'))
        self.assertFalse(auth.has_perm(self.get_current_user(), 'w'))
        self.assertTrue(auth.has_perm('anonymous', 'e'))
        self.assertFalse(auth.has_perm('anonymous', 'w'))
        warnings.filterwarnings("ignore")
        auth.override_user('anonymous', perm='w')
        warnings.resetwarnings()
        self.assertTrue(auth.has_perm('anonymous', 'w'))

    def test_validate_authentication(self):
        # we can only test for invalid credentials
        auth = UnixAuthorizer(require_valid_shell=False)
        self.assertRaises(AuthenticationFailed,
                          auth.validate_authentication, '?!foo', '?!foo', None)
        auth = UnixAuthorizer(require_valid_shell=True)
        self.assertRaises(AuthenticationFailed,
                          auth.validate_authentication, '?!foo', '?!foo', None)

    def test_validate_authentication_anonymous(self):
        current_user = self.get_current_user()
        auth = UnixAuthorizer(anonymous_user=current_user,
                              require_valid_shell=False)
        self.assertRaises(AuthenticationFailed,
                          auth.validate_authentication, 'foo', 'passwd', None)
        self.assertRaises(
            AuthenticationFailed,
            auth.validate_authentication, current_user, 'passwd', None)
        auth.validate_authentication('anonymous', 'passwd', None)

    def test_require_valid_shell(self):

        def get_fake_shell_user():
            for user in self.get_users():
                shell = pwd.getpwnam(user).pw_shell
                # On linux fake shell is usually /bin/false, on
                # freebsd /usr/sbin/nologin;  in case of other
                # UNIX variants test needs to be adjusted.
                if '/false' in shell or '/nologin' in shell:
                    return user
            self.fail("no user found")

        user = get_fake_shell_user()
        self.assertRaisesWithMsg(
            AuthorizerError,
            "user %s has not a valid shell" % user,
            UnixAuthorizer, allowed_users=[user])
        # commented as it first fails for invalid home
        # self.assertRaisesWithMsg(
        #     ValueError,
        #     "user %s has not a valid shell" % user,
        #     UnixAuthorizer, anonymous_user=user)
        auth = UnixAuthorizer()
        self.assertTrue(auth._has_valid_shell(self.get_current_user()))
        self.assertFalse(auth._has_valid_shell(user))
        self.assertRaisesWithMsg(AuthorizerError,
                                 "User %s doesn't have a valid shell." % user,
                                 auth.override_user, user, perm='r')

    def test_not_root(self):
        # UnixAuthorizer is supposed to work only as super user
        auth = self.authorizer_class()
        try:
            auth.impersonate_user('nobody', '')
            self.assertRaisesWithMsg(AuthorizerError,
                                     "super user privileges are required",
                                     UnixAuthorizer)
        finally:
            auth.terminate_impersonation('nobody')


# =====================================================================
# --- Windows authorizer
# =====================================================================


@unittest.skipUnless(WINDOWS, "Windows only")
class TestWindowsAuthorizer(_SharedAuthorizerTests, PyftpdlibTestCase):
    """Windows authorizer specific tests."""

    authorizer_class = WindowsAuthorizer

    def test_wrong_anonymous_credentials(self):
        user = self.get_current_user()
        self.assertRaises(Win32ExtError, self.authorizer_class,
                          anonymous_user=user,
                          anonymous_password='$|1wrongpasswd')


if __name__ == '__main__':
    from pyftpdlib.test.runner import run_from_name
    run_from_name(__file__)
