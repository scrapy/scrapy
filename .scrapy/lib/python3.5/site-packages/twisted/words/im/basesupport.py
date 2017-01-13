# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#

"""Instance Messenger base classes for protocol support.

You will find these useful if you're adding a new protocol to IM.
"""

# Abstract representation of chat "model" classes

from twisted.words.im.locals import OFFLINE, OfflineError

from twisted.internet.protocol import Protocol

from twisted.python.reflect import prefixedMethods
from twisted.persisted import styles

from twisted.internet import error

class AbstractGroup:
    def __init__(self, name, account):
        self.name = name
        self.account = account

    def getGroupCommands(self):
        """finds group commands

        these commands are methods on me that start with imgroup_; they are
        called with no arguments
        """
        return prefixedMethods(self, "imgroup_")

    def getTargetCommands(self, target):
        """finds group commands

        these commands are methods on me that start with imgroup_; they are
        called with a user present within this room as an argument

        you may want to override this in your group in order to filter for
        appropriate commands on the given user
        """
        return prefixedMethods(self, "imtarget_")

    def join(self):
        if not self.account.client:
            raise OfflineError
        self.account.client.joinGroup(self.name)

    def leave(self):
        if not self.account.client:
            raise OfflineError
        self.account.client.leaveGroup(self.name)

    def __repr__(self):
        return '<%s %r>' % (self.__class__, self.name)

    def __str__(self):
        return '%s@%s' % (self.name, self.account.accountName)

class AbstractPerson:
    def __init__(self, name, baseAccount):
        self.name = name
        self.account = baseAccount
        self.status = OFFLINE

    def getPersonCommands(self):
        """finds person commands

        these commands are methods on me that start with imperson_; they are
        called with no arguments
        """
        return prefixedMethods(self, "imperson_")

    def getIdleTime(self):
        """
        Returns a string.
        """
        return '--'

    def __repr__(self):
        return '<%s %r/%s>' % (self.__class__, self.name, self.status)

    def __str__(self):
        return '%s@%s' % (self.name, self.account.accountName)

class AbstractClientMixin:
    """Designed to be mixed in to a Protocol implementing class.

    Inherit from me first.

    @ivar _logonDeferred: Fired when I am done logging in.
    """
    def __init__(self, account, chatui, logonDeferred):
        for base in self.__class__.__bases__:
            if issubclass(base, Protocol):
                self.__class__._protoBase = base
                break
        else:
            pass
        self.account = account
        self.chat = chatui
        self._logonDeferred = logonDeferred

    def connectionMade(self):
        self._protoBase.connectionMade(self)

    def connectionLost(self, reason):
        self.account._clientLost(self, reason)
        self.unregisterAsAccountClient()
        return self._protoBase.connectionLost(self, reason)

    def unregisterAsAccountClient(self):
        """Tell the chat UI that I have `signed off'.
        """
        self.chat.unregisterAccountClient(self)


class AbstractAccount(styles.Versioned):
    """Base class for Accounts.

    I am the start of an implementation of L{IAccount<interfaces.IAccount>}, I
    implement L{isOnline} and most of L{logOn}, though you'll need to implement
    L{_startLogOn} in a subclass.

    @cvar _groupFactory: A Callable that will return a L{IGroup} appropriate
        for this account type.
    @cvar _personFactory: A Callable that will return a L{IPerson} appropriate
        for this account type.

    @type _isConnecting: boolean
    @ivar _isConnecting: Whether I am in the process of establishing a
    connection to the server.
    @type _isOnline: boolean
    @ivar _isOnline: Whether I am currently on-line with the server.

    @ivar accountName:
    @ivar autoLogin:
    @ivar username:
    @ivar password:
    @ivar host:
    @ivar port:
    """

    _isOnline = 0
    _isConnecting = 0
    client = None

    _groupFactory = AbstractGroup
    _personFactory = AbstractPerson

    persistanceVersion = 2

    def __init__(self, accountName, autoLogin, username, password, host, port):
        self.accountName = accountName
        self.autoLogin = autoLogin
        self.username = username
        self.password = password
        self.host = host
        self.port = port

        self._groups = {}
        self._persons = {}

    def upgrateToVersion2(self):
        # Added in CVS revision 1.16.
        for k in ('_groups', '_persons'):
            if not hasattr(self, k):
                setattr(self, k, {})

    def __getstate__(self):
        state = styles.Versioned.__getstate__(self)
        for k in ('client', '_isOnline', '_isConnecting'):
            try:
                del state[k]
            except KeyError:
                pass
        return state

    def isOnline(self):
        return self._isOnline

    def logOn(self, chatui):
        """Log on to this account.

        Takes care to not start a connection if a connection is
        already in progress.  You will need to implement
        L{_startLogOn} for this to work, and it would be a good idea
        to override L{_loginFailed} too.

        @returntype: Deferred L{interfaces.IClient}
        """
        if (not self._isConnecting) and (not self._isOnline):
            self._isConnecting = 1
            d = self._startLogOn(chatui)
            d.addCallback(self._cb_logOn)
            # if chatui is not None:
            # (I don't particularly like having to pass chatUI to this function,
            # but we haven't factored it out yet.)
            d.addCallback(chatui.registerAccountClient)
            d.addErrback(self._loginFailed)
            return d
        else:
            raise error.ConnectError("Connection in progress")

    def getGroup(self, name):
        """Group factory.

        @param name: Name of the group on this account.
        @type name: string
        """
        group = self._groups.get(name)
        if group is None:
            group = self._groupFactory(name, self)
            self._groups[name] = group
        return group

    def getPerson(self, name):
        """Person factory.

        @param name: Name of the person on this account.
        @type name: string
        """
        person = self._persons.get(name)
        if person is None:
            person = self._personFactory(name, self)
            self._persons[name] = person
        return person

    def _startLogOn(self, chatui):
        """Start the sign on process.

        Factored out of L{logOn}.

        @returntype: Deferred L{interfaces.IClient}
        """
        raise NotImplementedError()

    def _cb_logOn(self, client):
        self._isConnecting = 0
        self._isOnline = 1
        self.client = client
        return client

    def _loginFailed(self, reason):
        """Errorback for L{logOn}.

        @type reason: Failure

        @returns: I{reason}, for further processing in the callback chain.
        @returntype: Failure
        """
        self._isConnecting = 0
        self._isOnline = 0 # just in case
        return reason

    def _clientLost(self, client, reason):
        self.client = None
        self._isConnecting = 0
        self._isOnline = 0
        return reason

    def __repr__(self):
        return "<%s: %s (%s@%s:%s)>" % (self.__class__,
                                        self.accountName,
                                        self.username,
                                        self.host,
                                        self.port)
