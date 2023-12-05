# -*- test-case-name: twisted.words.test.test_jabberjid -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Jabber Identifier support.

This module provides an object to represent Jabber Identifiers (JIDs) and
parse string representations into them with proper checking for illegal
characters, case folding and canonicalisation through
L{stringprep<twisted.words.protocols.jabber.xmpp_stringprep>}.
"""

from typing import Dict

from twisted.words.protocols.jabber.xmpp_stringprep import (
    nameprep,
    nodeprep,
    resourceprep,
)


class InvalidFormat(Exception):
    """
    The given string could not be parsed into a valid Jabber Identifier (JID).
    """


def parse(jidstring):
    """
    Parse given JID string into its respective parts and apply stringprep.

    @param jidstring: string representation of a JID.
    @type jidstring: L{str}
    @return: tuple of (user, host, resource), each of type L{str} as
             the parsed and stringprep'd parts of the given JID. If the
             given string did not have a user or resource part, the respective
             field in the tuple will hold L{None}.
    @rtype: L{tuple}
    """
    user = None
    host = None
    resource = None

    # Search for delimiters
    user_sep = jidstring.find("@")
    res_sep = jidstring.find("/")

    if user_sep == -1:
        if res_sep == -1:
            # host
            host = jidstring
        else:
            # host/resource
            host = jidstring[0:res_sep]
            resource = jidstring[res_sep + 1 :] or None
    else:
        if res_sep == -1:
            # user@host
            user = jidstring[0:user_sep] or None
            host = jidstring[user_sep + 1 :]
        else:
            if user_sep < res_sep:
                # user@host/resource
                user = jidstring[0:user_sep] or None
                host = jidstring[user_sep + 1 : user_sep + (res_sep - user_sep)]
                resource = jidstring[res_sep + 1 :] or None
            else:
                # host/resource (with an @ in resource)
                host = jidstring[0:res_sep]
                resource = jidstring[res_sep + 1 :] or None

    return prep(user, host, resource)


def prep(user, host, resource):
    """
    Perform stringprep on all JID fragments.

    @param user: The user part of the JID.
    @type user: L{str}
    @param host: The host part of the JID.
    @type host: L{str}
    @param resource: The resource part of the JID.
    @type resource: L{str}
    @return: The given parts with stringprep applied.
    @rtype: L{tuple}
    """

    if user:
        try:
            user = nodeprep.prepare(str(user))
        except UnicodeError:
            raise InvalidFormat("Invalid character in username")
    else:
        user = None

    if not host:
        raise InvalidFormat("Server address required.")
    else:
        try:
            host = nameprep.prepare(str(host))
        except UnicodeError:
            raise InvalidFormat("Invalid character in hostname")

    if resource:
        try:
            resource = resourceprep.prepare(str(resource))
        except UnicodeError:
            raise InvalidFormat("Invalid character in resource")
    else:
        resource = None

    return (user, host, resource)


__internJIDs: Dict[str, "JID"] = {}


def internJID(jidstring):
    """
    Return interned JID.

    @rtype: L{JID}
    """

    if jidstring in __internJIDs:
        return __internJIDs[jidstring]
    else:
        j = JID(jidstring)
        __internJIDs[jidstring] = j
        return j


class JID:
    """
    Represents a stringprep'd Jabber ID.

    JID objects are hashable so they can be used in sets and as keys in
    dictionaries.
    """

    def __init__(self, str=None, tuple=None):
        if not (str or tuple):
            raise RuntimeError(
                "You must provide a value for either 'str' or " "'tuple' arguments."
            )

        if str:
            user, host, res = parse(str)
        else:
            user, host, res = prep(*tuple)

        self.user = user
        self.host = host
        self.resource = res

    def userhost(self):
        """
        Extract the bare JID as a unicode string.

        A bare JID does not have a resource part, so this returns either
        C{user@host} or just C{host}.

        @rtype: L{str}
        """
        if self.user:
            return f"{self.user}@{self.host}"
        else:
            return self.host

    def userhostJID(self):
        """
        Extract the bare JID.

        A bare JID does not have a resource part, so this returns a
        L{JID} object representing either C{user@host} or just C{host}.

        If the object this method is called upon doesn't have a resource
        set, it will return itself. Otherwise, the bare JID object will
        be created, interned using L{internJID}.

        @rtype: L{JID}
        """
        if self.resource:
            return internJID(self.userhost())
        else:
            return self

    def full(self):
        """
        Return the string representation of this JID.

        @rtype: L{str}
        """
        if self.user:
            if self.resource:
                return f"{self.user}@{self.host}/{self.resource}"
            else:
                return f"{self.user}@{self.host}"
        else:
            if self.resource:
                return f"{self.host}/{self.resource}"
            else:
                return self.host

    def __eq__(self, other: object) -> bool:
        """
        Equality comparison.

        L{JID}s compare equal if their user, host and resource parts all
        compare equal.  When comparing against instances of other types, it
        uses the default comparison.
        """
        if isinstance(other, JID):
            return (
                self.user == other.user
                and self.host == other.host
                and self.resource == other.resource
            )
        else:
            return NotImplemented

    def __hash__(self):
        """
        Calculate hash.

        L{JID}s with identical constituent user, host and resource parts have
        equal hash values.  In combination with the comparison defined on JIDs,
        this allows for using L{JID}s in sets and as dictionary keys.
        """
        return hash((self.user, self.host, self.resource))

    def __unicode__(self):
        """
        Get unicode representation.

        Return the string representation of this JID as a unicode string.
        @see: L{full}
        """

        return self.full()

    __str__ = __unicode__

    def __repr__(self) -> str:
        """
        Get object representation.

        Returns a string that would create a new JID object that compares equal
        to this one.
        """
        return "JID(%r)" % self.full()
