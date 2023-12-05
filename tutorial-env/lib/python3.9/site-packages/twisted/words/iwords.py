# -*- test-case-name: twisted.words.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from zope.interface import Attribute, Interface


class IProtocolPlugin(Interface):
    """Interface for plugins providing an interface to a Words service"""

    name = Attribute(
        "A single word describing what kind of interface this is (eg, irc or web)"
    )

    def getFactory(realm, portal):
        """Retrieve a C{twisted.internet.interfaces.IServerFactory} provider

        @param realm: An object providing C{twisted.cred.portal.IRealm} and
        L{IChatService}, with which service information should be looked up.

        @param portal: An object providing C{twisted.cred.portal.IPortal},
        through which logins should be performed.
        """


class IGroup(Interface):
    name = Attribute("A short string, unique among groups.")

    def add(user):
        """Include the given user in this group.

        @type user: L{IUser}
        """

    def remove(user, reason=None):
        """Remove the given user from this group.

        @type user: L{IUser}
        @type reason: C{unicode}
        """

    def size():
        """Return the number of participants in this group.

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires with an C{int} representing the
        number of participants in this group.
        """

    def receive(sender, recipient, message):
        """
        Broadcast the given message from the given sender to other
        users in group.

        The message is not re-transmitted to the sender.

        @param sender: L{IUser}

        @type recipient: L{IGroup}
        @param recipient: This is probably a wart.  Maybe it will be removed
        in the future.  For now, it should be the group object the message
        is being delivered to.

        @param message: C{dict}

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires with None when delivery has been
        attempted for all users.
        """

    def setMetadata(meta):
        """Change the metadata associated with this group.

        @type meta: C{dict}
        """

    def iterusers():
        """Return an iterator of all users in this group."""


class IChatClient(Interface):
    """Interface through which IChatService interacts with clients."""

    name = Attribute(
        "A short string, unique among users.  This will be set by the L{IChatService} at login time."
    )

    def receive(sender, recipient, message):
        """
        Callback notifying this user of the given message sent by the
        given user.

        This will be invoked whenever another user sends a message to a
        group this user is participating in, or whenever another user sends
        a message directly to this user.  In the former case, C{recipient}
        will be the group to which the message was sent; in the latter, it
        will be the same object as the user who is receiving the message.

        @type sender: L{IUser}
        @type recipient: L{IUser} or L{IGroup}
        @type message: C{dict}

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires when the message has been delivered,
        or which fails in some way.  If the Deferred fails and the message
        was directed at a group, this user will be removed from that group.
        """

    def groupMetaUpdate(group, meta):
        """
        Callback notifying this user that the metadata for the given
        group has changed.

        @type group: L{IGroup}
        @type meta: C{dict}

        @rtype: L{twisted.internet.defer.Deferred}
        """

    def userJoined(group, user):
        """
        Callback notifying this user that the given user has joined
        the given group.

        @type group: L{IGroup}
        @type user: L{IUser}

        @rtype: L{twisted.internet.defer.Deferred}
        """

    def userLeft(group, user, reason=None):
        """
        Callback notifying this user that the given user has left the
        given group for the given reason.

        @type group: L{IGroup}
        @type user: L{IUser}
        @type reason: C{unicode}

        @rtype: L{twisted.internet.defer.Deferred}
        """


class IUser(Interface):
    """Interface through which clients interact with IChatService."""

    realm = Attribute(
        "A reference to the Realm to which this user belongs.  Set if and only if the user is logged in."
    )
    mind = Attribute(
        "A reference to the mind which logged in to this user.  Set if and only if the user is logged in."
    )
    name = Attribute("A short string, unique among users.")

    lastMessage = Attribute(
        "A POSIX timestamp indicating the time of the last message received from this user."
    )
    signOn = Attribute(
        "A POSIX timestamp indicating this user's most recent sign on time."
    )

    def loggedIn(realm, mind):
        """Invoked by the associated L{IChatService} when login occurs.

        @param realm: The L{IChatService} through which login is occurring.
        @param mind: The mind object used for cred login.
        """

    def send(recipient, message):
        """Send the given message to the given user or group.

        @type recipient: Either L{IUser} or L{IGroup}
        @type message: C{dict}
        """

    def join(group):
        """Attempt to join the given group.

        @type group: L{IGroup}
        @rtype: L{twisted.internet.defer.Deferred}
        """

    def leave(group):
        """Discontinue participation in the given group.

        @type group: L{IGroup}
        @rtype: L{twisted.internet.defer.Deferred}
        """

    def itergroups():
        """
        Return an iterator of all groups of which this user is a
        member.
        """


class IChatService(Interface):
    name = Attribute("A short string identifying this chat service (eg, a hostname)")

    createGroupOnRequest = Attribute(
        "A boolean indicating whether L{getGroup} should implicitly "
        "create groups which are requested but which do not yet exist."
    )

    createUserOnRequest = Attribute(
        "A boolean indicating whether L{getUser} should implicitly "
        "create users which are requested but which do not yet exist."
    )

    def itergroups():
        """Return all groups available on this service.

        @rtype: C{twisted.internet.defer.Deferred}
        @return: A Deferred which fires with a list of C{IGroup} providers.
        """

    def getGroup(name):
        """Retrieve the group by the given name.

        @type name: C{str}

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires with the group with the given
        name if one exists (or if one is created due to the setting of
        L{IChatService.createGroupOnRequest}, or which fails with
        L{twisted.words.ewords.NoSuchGroup} if no such group exists.
        """

    def createGroup(name):
        """Create a new group with the given name.

        @type name: C{str}

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires with the created group, or
        with fails with L{twisted.words.ewords.DuplicateGroup} if a
        group by that name exists already.
        """

    def lookupGroup(name):
        """Retrieve a group by name.

        Unlike C{getGroup}, this will never implicitly create a group.

        @type name: C{str}

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires with the group by the given
        name, or which fails with L{twisted.words.ewords.NoSuchGroup}.
        """

    def getUser(name):
        """Retrieve the user by the given name.

        @type name: C{str}

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires with the user with the given
        name if one exists (or if one is created due to the setting of
        L{IChatService.createUserOnRequest}, or which fails with
        L{twisted.words.ewords.NoSuchUser} if no such user exists.
        """

    def createUser(name):
        """Create a new user with the given name.

        @type name: C{str}

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires with the created user, or
        with fails with L{twisted.words.ewords.DuplicateUser} if a
        user by that name exists already.
        """


__all__ = [
    "IGroup",
    "IChatClient",
    "IUser",
    "IChatService",
]
