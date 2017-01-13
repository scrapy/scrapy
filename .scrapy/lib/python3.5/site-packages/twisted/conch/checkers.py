# -*- test-case-name: twisted.conch.test.test_checkers -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Provide L{ICredentialsChecker} implementations to be used in Conch protocols.
"""

from __future__ import absolute_import, division

import sys
import binascii
import errno

try:
    import pwd
except ImportError:
    pwd = None
else:
    import crypt

try:
    import spwd
except ImportError:
    spwd = None

from zope.interface import providedBy, implementer, Interface

from twisted.conch import error
from twisted.conch.ssh import keys
from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.credentials import IUsernamePassword, ISSHPrivateKey
from twisted.cred.error import UnauthorizedLogin, UnhandledCredentials
from twisted.internet import defer
from twisted.python.compat import _keys, _PY3, _b64decodebytes
from twisted.python import failure, reflect, log
from twisted.python.deprecate import deprecatedModuleAttribute
from twisted.python.util import runAsEffectiveUser
from twisted.python.filepath import FilePath
from twisted.python.versions import Version



def verifyCryptedPassword(crypted, pw):
    """
    Check that the password, when crypted, matches the stored crypted password.

    @param crypted: The stored crypted password.
    @type crypted: L{str}
    @param pw: The password the user has given.
    @type pw: L{str}

    @rtype: L{bool}
    """
    return crypt.crypt(pw, crypted) == crypted



def _pwdGetByName(username):
    """
    Look up a user in the /etc/passwd database using the pwd module.  If the
    pwd module is not available, return None.

    @param username: the username of the user to return the passwd database
        information for.
    @type username: L{str}
    """
    if pwd is None:
        return None
    return pwd.getpwnam(username)



def _shadowGetByName(username):
    """
    Look up a user in the /etc/shadow database using the spwd module. If it is
    not available, return L{None}.

    @param username: the username of the user to return the shadow database
        information for.
    @type username: L{str}
    """
    if spwd is not None:
        f = spwd.getspnam
    else:
        return None
    return runAsEffectiveUser(0, 0, f, username)



@implementer(ICredentialsChecker)
class UNIXPasswordDatabase:
    """
    A checker which validates users out of the UNIX password databases, or
    databases of a compatible format.

    @ivar _getByNameFunctions: a C{list} of functions which are called in order
        to valid a user.  The default value is such that the C{/etc/passwd}
        database will be tried first, followed by the C{/etc/shadow} database.
    """
    credentialInterfaces = IUsernamePassword,

    def __init__(self, getByNameFunctions=None):
        if getByNameFunctions is None:
            getByNameFunctions = [_pwdGetByName, _shadowGetByName]
        self._getByNameFunctions = getByNameFunctions


    def requestAvatarId(self, credentials):
        # We get bytes, but the Py3 pwd module uses str. So attempt to decode
        # it using the same method that CPython does for the file on disk.
        if _PY3:
            username = credentials.username.decode(sys.getfilesystemencoding())
            password = credentials.password.decode(sys.getfilesystemencoding())
        else:
            username = credentials.username
            password = credentials.password

        for func in self._getByNameFunctions:
            try:
                pwnam = func(username)
            except KeyError:
                return defer.fail(UnauthorizedLogin("invalid username"))
            else:
                if pwnam is not None:
                    crypted = pwnam[1]
                    if crypted == '':
                        continue

                    if verifyCryptedPassword(crypted, password):
                        return defer.succeed(credentials.username)
        # fallback
        return defer.fail(UnauthorizedLogin("unable to verify password"))



@implementer(ICredentialsChecker)
class SSHPublicKeyDatabase:
    """
    Checker that authenticates SSH public keys, based on public keys listed in
    authorized_keys and authorized_keys2 files in user .ssh/ directories.
    """
    credentialInterfaces = (ISSHPrivateKey,)

    _userdb = pwd

    def requestAvatarId(self, credentials):
        d = defer.maybeDeferred(self.checkKey, credentials)
        d.addCallback(self._cbRequestAvatarId, credentials)
        d.addErrback(self._ebRequestAvatarId)
        return d

    def _cbRequestAvatarId(self, validKey, credentials):
        """
        Check whether the credentials themselves are valid, now that we know
        if the key matches the user.

        @param validKey: A boolean indicating whether or not the public key
            matches a key in the user's authorized_keys file.

        @param credentials: The credentials offered by the user.
        @type credentials: L{ISSHPrivateKey} provider

        @raise UnauthorizedLogin: (as a failure) if the key does not match the
            user in C{credentials}. Also raised if the user provides an invalid
            signature.

        @raise ValidPublicKey: (as a failure) if the key matches the user but
            the credentials do not include a signature. See
            L{error.ValidPublicKey} for more information.

        @return: The user's username, if authentication was successful.
        """
        if not validKey:
            return failure.Failure(UnauthorizedLogin("invalid key"))
        if not credentials.signature:
            return failure.Failure(error.ValidPublicKey())
        else:
            try:
                pubKey = keys.Key.fromString(credentials.blob)
                if pubKey.verify(credentials.signature, credentials.sigData):
                    return credentials.username
            except: # any error should be treated as a failed login
                log.err()
                return failure.Failure(UnauthorizedLogin('error while verifying key'))
        return failure.Failure(UnauthorizedLogin("unable to verify key"))


    def getAuthorizedKeysFiles(self, credentials):
        """
        Return a list of L{FilePath} instances for I{authorized_keys} files
        which might contain information about authorized keys for the given
        credentials.

        On OpenSSH servers, the default location of the file containing the
        list of authorized public keys is
        U{$HOME/.ssh/authorized_keys<http://www.openbsd.org/cgi-bin/man.cgi?query=sshd_config>}.

        I{$HOME/.ssh/authorized_keys2} is also returned, though it has been
        U{deprecated by OpenSSH since
        2001<http://marc.info/?m=100508718416162>}.

        @return: A list of L{FilePath} instances to files with the authorized keys.
        """
        pwent = self._userdb.getpwnam(credentials.username)
        root = FilePath(pwent.pw_dir).child('.ssh')
        files = ['authorized_keys', 'authorized_keys2']
        return [root.child(f) for f in files]


    def checkKey(self, credentials):
        """
        Retrieve files containing authorized keys and check against user
        credentials.
        """
        ouid, ogid = self._userdb.getpwnam(credentials.username)[2:4]
        for filepath in self.getAuthorizedKeysFiles(credentials):
            if not filepath.exists():
                continue
            try:
                lines = filepath.open()
            except IOError as e:
                if e.errno == errno.EACCES:
                    lines = runAsEffectiveUser(ouid, ogid, filepath.open)
                else:
                    raise
            with lines:
                for l in lines:
                    l2 = l.split()
                    if len(l2) < 2:
                        continue
                    try:
                        if _b64decodebytes(l2[1]) == credentials.blob:
                            return True
                    except binascii.Error:
                        continue
        return False

    def _ebRequestAvatarId(self, f):
        if not f.check(UnauthorizedLogin):
            log.msg(f)
            return failure.Failure(UnauthorizedLogin("unable to get avatar id"))
        return f



@implementer(ICredentialsChecker)
class SSHProtocolChecker:
    """
    SSHProtocolChecker is a checker that requires multiple authentications
    to succeed.  To add a checker, call my registerChecker method with
    the checker and the interface.

    After each successful authenticate, I call my areDone method with the
    avatar id.  To get a list of the successful credentials for an avatar id,
    use C{SSHProcotolChecker.successfulCredentials[avatarId]}.  If L{areDone}
    returns True, the authentication has succeeded.
    """

    def __init__(self):
        self.checkers = {}
        self.successfulCredentials = {}

    def get_credentialInterfaces(self):
        return _keys(self.checkers)

    credentialInterfaces = property(get_credentialInterfaces)

    def registerChecker(self, checker, *credentialInterfaces):
        if not credentialInterfaces:
            credentialInterfaces = checker.credentialInterfaces
        for credentialInterface in credentialInterfaces:
            self.checkers[credentialInterface] = checker

    def requestAvatarId(self, credentials):
        """
        Part of the L{ICredentialsChecker} interface.  Called by a portal with
        some credentials to check if they'll authenticate a user.  We check the
        interfaces that the credentials provide against our list of acceptable
        checkers.  If one of them matches, we ask that checker to verify the
        credentials.  If they're valid, we call our L{_cbGoodAuthentication}
        method to continue.

        @param credentials: the credentials the L{Portal} wants us to verify
        """
        ifac = providedBy(credentials)
        for i in ifac:
            c = self.checkers.get(i)
            if c is not None:
                d = defer.maybeDeferred(c.requestAvatarId, credentials)
                return d.addCallback(self._cbGoodAuthentication,
                        credentials)
        return defer.fail(UnhandledCredentials("No checker for %s" % \
            ', '.join(map(reflect.qual, ifac))))

    def _cbGoodAuthentication(self, avatarId, credentials):
        """
        Called if a checker has verified the credentials.  We call our
        L{areDone} method to see if the whole of the successful authentications
        are enough.  If they are, we return the avatar ID returned by the first
        checker.
        """
        if avatarId not in self.successfulCredentials:
            self.successfulCredentials[avatarId] = []
        self.successfulCredentials[avatarId].append(credentials)
        if self.areDone(avatarId):
            del self.successfulCredentials[avatarId]
            return avatarId
        else:
            raise error.NotEnoughAuthentication()

    def areDone(self, avatarId):
        """
        Override to determine if the authentication is finished for a given
        avatarId.

        @param avatarId: the avatar returned by the first checker.  For
            this checker to function correctly, all the checkers must
            return the same avatar ID.
        """
        return True



deprecatedModuleAttribute(
        Version("Twisted", 15, 0, 0),
        ("Please use twisted.conch.checkers.SSHPublicKeyChecker, "
         "initialized with an instance of "
         "twisted.conch.checkers.UNIXAuthorizedKeysFiles instead."),
        __name__, "SSHPublicKeyDatabase")



class IAuthorizedKeysDB(Interface):
    """
    An object that provides valid authorized ssh keys mapped to usernames.

    @since: 15.0
    """
    def getAuthorizedKeys(avatarId):
        """
        Gets an iterable of authorized keys that are valid for the given
        C{avatarId}.

        @param avatarId: the ID of the avatar
        @type avatarId: valid return value of
            L{twisted.cred.checkers.ICredentialsChecker.requestAvatarId}

        @return: an iterable of L{twisted.conch.ssh.keys.Key}
        """



def readAuthorizedKeyFile(fileobj, parseKey=keys.Key.fromString):
    """
    Reads keys from an authorized keys file.  Any non-comment line that cannot
    be parsed as a key will be ignored, although that particular line will
    be logged.

    @param fileobj: something from which to read lines which can be parsed
        as keys
    @type fileobj: L{file}-like object

    @param parseKey: a callable that takes a string and returns a
        L{twisted.conch.ssh.keys.Key}, mainly to be used for testing.  The
        default is L{twisted.conch.ssh.keys.Key.fromString}.
    @type parseKey: L{callable}

    @return: an iterable of L{twisted.conch.ssh.keys.Key}
    @rtype: iterable

    @since: 15.0
    """
    for line in fileobj:
        line = line.strip()
        if line and not line.startswith(b'#'):  # for comments
            try:
                yield parseKey(line)
            except keys.BadKeyError as e:
                log.msg('Unable to parse line "{0}" as a key: {1!s}'
                        .format(line, e))



def _keysFromFilepaths(filepaths, parseKey):
    """
    Helper function that turns an iterable of filepaths into a generator of
    keys.  If any file cannot be read, a message is logged but it is
    otherwise ignored.

    @param filepaths: iterable of L{twisted.python.filepath.FilePath}.
    @type filepaths: iterable

    @param parseKey: a callable that takes a string and returns a
        L{twisted.conch.ssh.keys.Key}
    @type parseKey: L{callable}

    @return: generator of L{twisted.conch.ssh.keys.Key}
    @rtype: generator

    @since: 15.0
    """
    for fp in filepaths:
        if fp.exists():
            try:
                with fp.open() as f:
                    for key in readAuthorizedKeyFile(f, parseKey):
                        yield key
            except (IOError, OSError) as e:
                log.msg("Unable to read {0}: {1!s}".format(fp.path, e))



@implementer(IAuthorizedKeysDB)
class InMemorySSHKeyDB(object):
    """
    Object that provides SSH public keys based on a dictionary of usernames
    mapped to L{twisted.conch.ssh.keys.Key}s.

    @since: 15.0
    """
    def __init__(self, mapping):
        """
        Initializes a new L{InMemorySSHKeyDB}.

        @param mapping: mapping of usernames to iterables of
            L{twisted.conch.ssh.keys.Key}s
        @type mapping: L{dict}

        """
        self._mapping = mapping


    def getAuthorizedKeys(self, username):
        return self._mapping.get(username, [])



@implementer(IAuthorizedKeysDB)
class UNIXAuthorizedKeysFiles(object):
    """
    Object that provides SSH public keys based on public keys listed in
    authorized_keys and authorized_keys2 files in UNIX user .ssh/ directories.
    If any of the files cannot be read, a message is logged but that file is
    otherwise ignored.

    @since: 15.0
    """
    def __init__(self, userdb=None, parseKey=keys.Key.fromString):
        """
        Initializes a new L{UNIXAuthorizedKeysFiles}.

        @param userdb: access to the Unix user account and password database
            (default is the Python module L{pwd})
        @type userdb: L{pwd}-like object

        @param parseKey: a callable that takes a string and returns a
            L{twisted.conch.ssh.keys.Key}, mainly to be used for testing.  The
            default is L{twisted.conch.ssh.keys.Key.fromString}.
        @type parseKey: L{callable}
        """
        self._userdb = userdb
        self._parseKey = parseKey
        if userdb is None:
            self._userdb = pwd


    def getAuthorizedKeys(self, username):
        try:
            passwd = self._userdb.getpwnam(username)
        except KeyError:
            return ()

        root = FilePath(passwd.pw_dir).child('.ssh')
        files = ['authorized_keys', 'authorized_keys2']
        return _keysFromFilepaths((root.child(f) for f in files),
                                  self._parseKey)



@implementer(ICredentialsChecker)
class SSHPublicKeyChecker(object):
    """
    Checker that authenticates SSH public keys, based on public keys listed in
    authorized_keys and authorized_keys2 files in user .ssh/ directories.

    Initializing this checker with a L{UNIXAuthorizedKeysFiles} should be
    used instead of L{twisted.conch.checkers.SSHPublicKeyDatabase}.

    @since: 15.0
    """
    credentialInterfaces = (ISSHPrivateKey,)

    def __init__(self, keydb):
        """
        Initializes a L{SSHPublicKeyChecker}.

        @param keydb: a provider of L{IAuthorizedKeysDB}
        @type keydb: L{IAuthorizedKeysDB} provider
        """
        self._keydb = keydb


    def requestAvatarId(self, credentials):
        d = defer.maybeDeferred(self._sanityCheckKey, credentials)
        d.addCallback(self._checkKey, credentials)
        d.addCallback(self._verifyKey, credentials)
        return d


    def _sanityCheckKey(self, credentials):
        """
        Checks whether the provided credentials are a valid SSH key with a
        signature (does not actually verify the signature).

        @param credentials: the credentials offered by the user
        @type credentials: L{ISSHPrivateKey} provider

        @raise ValidPublicKey: the credentials do not include a signature. See
            L{error.ValidPublicKey} for more information.

        @raise BadKeyError: The key included with the credentials is not
            recognized as a key.

        @return: the key in the credentials
        @rtype: L{twisted.conch.ssh.keys.Key}
        """
        if not credentials.signature:
            raise error.ValidPublicKey()

        return keys.Key.fromString(credentials.blob)


    def _checkKey(self, pubKey, credentials):
        """
        Checks the public key against all authorized keys (if any) for the
        user.

        @param pubKey: the key in the credentials (just to prevent it from
            having to be calculated again)
        @type pubKey:

        @param credentials: the credentials offered by the user
        @type credentials: L{ISSHPrivateKey} provider

        @raise UnauthorizedLogin: If the key is not authorized, or if there
            was any error obtaining a list of authorized keys for the user.

        @return: C{pubKey} if the key is authorized
        @rtype: L{twisted.conch.ssh.keys.Key}
        """
        if any(key == pubKey for key in
               self._keydb.getAuthorizedKeys(credentials.username)):
            return pubKey

        raise UnauthorizedLogin("Key not authorized")


    def _verifyKey(self, pubKey, credentials):
        """
        Checks whether the credentials themselves are valid, now that we know
        if the key matches the user.

        @param pubKey: the key in the credentials (just to prevent it from
            having to be calculated again)
        @type pubKey: L{twisted.conch.ssh.keys.Key}

        @param credentials: the credentials offered by the user
        @type credentials: L{ISSHPrivateKey} provider

        @raise UnauthorizedLogin: If the key signature is invalid or there
            was any error verifying the signature.

        @return: The user's username, if authentication was successful
        @rtype: L{bytes}
        """
        try:
            if pubKey.verify(credentials.signature, credentials.sigData):
                return credentials.username
        except:  # any error should be treated as a failed login
            log.err()
            raise UnauthorizedLogin('Error while verifying key')

        raise UnauthorizedLogin("Key signature invalid.")
