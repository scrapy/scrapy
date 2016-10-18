# -*- test-case-name: twisted.cred.test.test_cred -*-

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
The point of integration of application and authentication.
"""

from __future__ import division, absolute_import

from twisted.internet import defer
from twisted.internet.defer import maybeDeferred
from twisted.python import failure, reflect
from twisted.cred import error
from zope.interface import providedBy, Interface


class IRealm(Interface):
    """
    The realm connects application-specific objects to the
    authentication system.
    """
    def requestAvatar(avatarId, mind, *interfaces):
        """
        Return avatar which provides one of the given interfaces.

        @param avatarId: a string that identifies an avatar, as returned by
            L{ICredentialsChecker.requestAvatarId<twisted.cred.checkers.ICredentialsChecker.requestAvatarId>}
            (via a Deferred).  Alternatively, it may be
            C{twisted.cred.checkers.ANONYMOUS}.
        @param mind: usually None.  See the description of mind in
            L{Portal.login}.
        @param interfaces: the interface(s) the returned avatar should
            implement, e.g.  C{IMailAccount}.  See the description of
            L{Portal.login}.

        @returns: a deferred which will fire a tuple of (interface,
            avatarAspect, logout), or the tuple itself.  The interface will be
            one of the interfaces passed in the 'interfaces' argument.  The
            'avatarAspect' will implement that interface.  The 'logout' object
            is a callable which will detach the mind from the avatar.
        """


class Portal(object):
    """
    A mediator between clients and a realm.

    A portal is associated with one Realm and zero or more credentials checkers.
    When a login is attempted, the portal finds the appropriate credentials
    checker for the credentials given, invokes it, and if the credentials are
    valid, retrieves the appropriate avatar from the Realm.

    This class is not intended to be subclassed.  Customization should be done
    in the realm object and in the credentials checker objects.
    """
    def __init__(self, realm, checkers=()):
        """
        Create a Portal to a L{IRealm}.
        """
        self.realm = realm
        self.checkers = {}
        for checker in checkers:
            self.registerChecker(checker)


    def listCredentialsInterfaces(self):
        """
        Return list of credentials interfaces that can be used to login.
        """
        return list(self.checkers.keys())


    def registerChecker(self, checker, *credentialInterfaces):
        if not credentialInterfaces:
            credentialInterfaces = checker.credentialInterfaces
        for credentialInterface in credentialInterfaces:
            self.checkers[credentialInterface] = checker


    def login(self, credentials, mind, *interfaces):
        """
        @param credentials: an implementor of
            L{twisted.cred.credentials.ICredentials}

        @param mind: an object which implements a client-side interface for
            your particular realm.  In many cases, this may be None, so if the
            word 'mind' confuses you, just ignore it.

        @param interfaces: list of interfaces for the perspective that the mind
            wishes to attach to. Usually, this will be only one interface, for
            example IMailAccount. For highly dynamic protocols, however, this
            may be a list like (IMailAccount, IUserChooser, IServiceInfo).  To
            expand: if we are speaking to the system over IMAP, any information
            that will be relayed to the user MUST be returned as an
            IMailAccount implementor; IMAP clients would not be able to
            understand anything else. Any information about unusual status
            would have to be relayed as a single mail message in an
            otherwise-empty mailbox. However, in a web-based mail system, or a
            PB-based client, the ``mind'' object inside the web server
            (implemented with a dynamic page-viewing mechanism such as a
            Twisted Web Resource) or on the user's client program may be
            intelligent enough to respond to several ``server''-side
            interfaces.

        @return: A deferred which will fire a tuple of (interface,
            avatarAspect, logout).  The interface will be one of the interfaces
            passed in the 'interfaces' argument.  The 'avatarAspect' will
            implement that interface. The 'logout' object is a callable which
            will detach the mind from the avatar. It must be called when the
            user has conceptually disconnected from the service. Although in
            some cases this will not be in connectionLost (such as in a
            web-based session), it will always be at the end of a user's
            interactive session.
        """
        for i in self.checkers:
            if i.providedBy(credentials):
                return maybeDeferred(self.checkers[i].requestAvatarId, credentials
                    ).addCallback(self.realm.requestAvatar, mind, *interfaces
                    )
        ifac = providedBy(credentials)
        return defer.fail(failure.Failure(error.UnhandledCredentials(
            "No checker for %s" % ', '.join(map(reflect.qual, ifac)))))
