# -*- test-case-name: twisted.words.test.test_service -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A module that needs a better name.

Implements new cred things for words.

How does this thing work?

  - Network connection on some port expecting to speak some protocol

  - Protocol-specific authentication, resulting in some kind of credentials object

  - twisted.cred.portal login using those credentials for the interface
    IUser and with something implementing IChatClient as the mind

  - successful login results in an IUser avatar the protocol can call
    methods on, and state added to the realm such that the mind will have
    methods called on it as is necessary

  - protocol specific actions lead to calls onto the avatar; remote events
    lead to calls onto the mind

  - protocol specific hangup, realm is notified, user is removed from active
    play, the end.
"""

from time import ctime, time

from zope.interface import implementer

from twisted import copyright
from twisted.cred import credentials, error as ecred, portal
from twisted.internet import defer, protocol
from twisted.python import failure, log, reflect
from twisted.python.components import registerAdapter
from twisted.spread import pb
from twisted.words import ewords, iwords
from twisted.words.protocols import irc


@implementer(iwords.IGroup)
class Group:
    def __init__(self, name):
        self.name = name
        self.users = {}
        self.meta = {
            "topic": "",
            "topic_author": "",
        }

    def _ebUserCall(self, err, p):
        return failure.Failure(Exception(p, err))

    def _cbUserCall(self, results):
        for (success, result) in results:
            if not success:
                user, err = result.value  # XXX
                self.remove(user, err.getErrorMessage())

    def add(self, user):
        assert iwords.IChatClient.providedBy(user), "{!r} is not a chat client".format(
            user
        )
        if user.name not in self.users:
            additions = []
            self.users[user.name] = user
            for p in self.users.values():
                if p is not user:
                    d = defer.maybeDeferred(p.userJoined, self, user)
                    d.addErrback(self._ebUserCall, p=p)
                    additions.append(d)
            defer.DeferredList(additions).addCallback(self._cbUserCall)
        return defer.succeed(None)

    def remove(self, user, reason=None):
        try:
            del self.users[user.name]
        except KeyError:
            pass
        else:
            removals = []
            for p in self.users.values():
                if p is not user:
                    d = defer.maybeDeferred(p.userLeft, self, user, reason)
                    d.addErrback(self._ebUserCall, p=p)
                    removals.append(d)
            defer.DeferredList(removals).addCallback(self._cbUserCall)
        return defer.succeed(None)

    def size(self):
        return defer.succeed(len(self.users))

    def receive(self, sender, recipient, message):
        assert recipient is self
        receives = []
        for p in self.users.values():
            if p is not sender:
                d = defer.maybeDeferred(p.receive, sender, self, message)
                d.addErrback(self._ebUserCall, p=p)
                receives.append(d)
        defer.DeferredList(receives).addCallback(self._cbUserCall)
        return defer.succeed(None)

    def setMetadata(self, meta):
        self.meta = meta
        sets = []
        for p in self.users.values():
            d = defer.maybeDeferred(p.groupMetaUpdate, self, meta)
            d.addErrback(self._ebUserCall, p=p)
            sets.append(d)
        defer.DeferredList(sets).addCallback(self._cbUserCall)
        return defer.succeed(None)

    def iterusers(self):
        # XXX Deferred?
        return iter(self.users.values())


@implementer(iwords.IUser)
class User:
    realm = None
    mind = None

    def __init__(self, name):
        self.name = name
        self.groups = []
        self.lastMessage = time()

    def loggedIn(self, realm, mind):
        self.realm = realm
        self.mind = mind
        self.signOn = time()

    def join(self, group):
        def cbJoin(result):
            self.groups.append(group)
            return result

        return group.add(self.mind).addCallback(cbJoin)

    def leave(self, group, reason=None):
        def cbLeave(result):
            self.groups.remove(group)
            return result

        return group.remove(self.mind, reason).addCallback(cbLeave)

    def send(self, recipient, message):
        self.lastMessage = time()
        return recipient.receive(self.mind, recipient, message)

    def itergroups(self):
        return iter(self.groups)

    def logout(self):
        for g in self.groups[:]:
            self.leave(g)


NICKSERV = "NickServ!NickServ@services"


@implementer(iwords.IChatClient)
class IRCUser(irc.IRC):
    """
    Protocol instance representing an IRC user connected to the server.
    """

    # A list of IGroups in which I am participating
    groups = None

    # A no-argument callable I should invoke when I go away
    logout = None

    # An IUser we use to interact with the chat service
    avatar = None

    # To whence I belong
    realm = None

    # How to handle unicode (TODO: Make this customizable on a per-user basis)
    encoding = "utf-8"

    # Twisted callbacks
    def connectionMade(self):
        self.irc_PRIVMSG = self.irc_NICKSERV_PRIVMSG
        self.realm = self.factory.realm
        self.hostname = self.realm.name

    def connectionLost(self, reason):
        if self.logout is not None:
            self.logout()
            self.avatar = None

    # Make sendMessage a bit more useful to us
    def sendMessage(self, command, *parameter_list, **kw):
        if "prefix" not in kw:
            kw["prefix"] = self.hostname
        if "to" not in kw:
            kw["to"] = self.name.encode(self.encoding)

        arglist = [self, command, kw["to"]] + list(parameter_list)
        arglistUnicode = []
        for arg in arglist:
            if isinstance(arg, bytes):
                arg = arg.decode("utf-8")
            arglistUnicode.append(arg)
        irc.IRC.sendMessage(*arglistUnicode, **kw)

    # IChatClient implementation
    def userJoined(self, group, user):
        self.join(f"{user.name}!{user.name}@{self.hostname}", "#" + group.name)

    def userLeft(self, group, user, reason=None):
        self.part(
            f"{user.name}!{user.name}@{self.hostname}",
            "#" + group.name,
            (reason or "leaving"),
        )

    def receive(self, sender, recipient, message):
        # >> :glyph!glyph@adsl-64-123-27-108.dsl.austtx.swbell.net PRIVMSG glyph_ :hello

        # omg???????????
        if iwords.IGroup.providedBy(recipient):
            recipientName = "#" + recipient.name
        else:
            recipientName = recipient.name

        text = message.get("text", "<an unrepresentable message>")
        for L in text.splitlines():
            self.privmsg(
                f"{sender.name}!{sender.name}@{self.hostname}",
                recipientName,
                L,
            )

    def groupMetaUpdate(self, group, meta):
        if "topic" in meta:
            topic = meta["topic"]
            author = meta.get("topic_author", "")
            self.topic(
                self.name,
                "#" + group.name,
                topic,
                f"{author}!{author}@{self.hostname}",
            )

    # irc.IRC callbacks - starting with login related stuff.
    nickname = None
    password = None

    def irc_PASS(self, prefix, params):
        """
        Password message -- Register a password.

        Parameters: <password>

        [REQUIRED]

        Note that IRC requires the client send this *before* NICK
        and USER.
        """
        self.password = params[-1]

    def irc_NICK(self, prefix, params):
        """
        Nick message -- Set your nickname.

        Parameters: <nickname>

        [REQUIRED]
        """
        nickname = params[0]
        try:
            if isinstance(nickname, bytes):
                nickname = nickname.decode(self.encoding)
        except UnicodeDecodeError:
            self.privmsg(
                NICKSERV,
                repr(nickname),
                "Your nickname cannot be decoded. Please use ASCII or UTF-8.",
            )
            self.transport.loseConnection()
            return

        self.nickname = nickname
        self.name = nickname

        for code, text in self._motdMessages:
            self.sendMessage(code, text % self.factory._serverInfo)

        if self.password is None:
            self.privmsg(NICKSERV, nickname, "Password?")
        else:
            password = self.password
            self.password = None
            self.logInAs(nickname, password)

    def irc_USER(self, prefix, params):
        """
        User message -- Set your realname.

        Parameters: <user> <mode> <unused> <realname>
        """
        # Note: who gives a crap about this?  The IUser has the real
        # information we care about.  Save it anyway, I guess, just
        # for fun.
        self.realname = params[-1]

    def irc_NICKSERV_PRIVMSG(self, prefix, params):
        """
        Send a (private) message.

        Parameters: <msgtarget> <text to be sent>
        """
        target = params[0]
        password = params[-1]

        if self.nickname is None:
            # XXX Send an error response here
            self.transport.loseConnection()
        elif target.lower() != "nickserv":
            self.privmsg(
                NICKSERV,
                self.nickname,
                "Denied.  Please send me (NickServ) your password.",
            )
        else:
            nickname = self.nickname
            self.nickname = None
            self.logInAs(nickname, password)

    def logInAs(self, nickname, password):
        d = self.factory.portal.login(
            credentials.UsernamePassword(nickname, password), self, iwords.IUser
        )
        d.addCallbacks(self._cbLogin, self._ebLogin, errbackArgs=(nickname,))

    _welcomeMessages = [
        (irc.RPL_WELCOME, ":connected to Twisted IRC"),
        (
            irc.RPL_YOURHOST,
            ":Your host is %(serviceName)s, running version %(serviceVersion)s",
        ),
        (irc.RPL_CREATED, ":This server was created on %(creationDate)s"),
        # "Bummer.  This server returned a worthless 004 numeric.
        #  I'll have to guess at all the values"
        #    -- epic
        (
            irc.RPL_MYINFO,
            # w and n are the currently supported channel and user modes
            # -- specify this better
            "%(serviceName)s %(serviceVersion)s w n",
        ),
    ]

    _motdMessages = [
        (irc.RPL_MOTDSTART, ":- %(serviceName)s Message of the Day - "),
        (irc.RPL_ENDOFMOTD, ":End of /MOTD command."),
    ]

    def _cbLogin(self, result):
        (iface, avatar, logout) = result
        assert iface is iwords.IUser, f"Realm is buggy, got {iface!r}"

        # Let them send messages to the world
        del self.irc_PRIVMSG

        self.avatar = avatar
        self.logout = logout
        for code, text in self._welcomeMessages:
            self.sendMessage(code, text % self.factory._serverInfo)

    def _ebLogin(self, err, nickname):
        if err.check(ewords.AlreadyLoggedIn):
            self.privmsg(
                NICKSERV, nickname, "Already logged in.  No pod people allowed!"
            )
        elif err.check(ecred.UnauthorizedLogin):
            self.privmsg(NICKSERV, nickname, "Login failed.  Goodbye.")
        else:
            log.msg("Unhandled error during login:")
            log.err(err)
            self.privmsg(NICKSERV, nickname, "Server error during login.  Sorry.")
        self.transport.loseConnection()

    # Great, now that's out of the way, here's some of the interesting
    # bits
    def irc_PING(self, prefix, params):
        """
        Ping message

        Parameters: <server1> [ <server2> ]
        """
        if self.realm is not None:
            self.sendMessage("PONG", self.hostname)

    def irc_QUIT(self, prefix, params):
        """
        Quit

        Parameters: [ <Quit Message> ]
        """
        self.transport.loseConnection()

    def _channelMode(self, group, modes=None, *args):
        if modes:
            self.sendMessage(irc.ERR_UNKNOWNMODE, ":Unknown MODE flag.")
        else:
            self.channelMode(self.name, "#" + group.name, "+")

    def _userMode(self, user, modes=None):
        if modes:
            self.sendMessage(irc.ERR_UNKNOWNMODE, ":Unknown MODE flag.")
        elif user is self.avatar:
            self.sendMessage(irc.RPL_UMODEIS, "+")
        else:
            self.sendMessage(
                irc.ERR_USERSDONTMATCH, ":You can't look at someone else's modes."
            )

    def irc_MODE(self, prefix, params):
        """
        User mode message

        Parameters: <nickname>
        *( ( "+" / "-" ) *( "i" / "w" / "o" / "O" / "r" ) )

        """
        try:
            channelOrUser = params[0]
            if isinstance(channelOrUser, bytes):
                channelOrUser = channelOrUser.decode(self.encoding)
        except UnicodeDecodeError:
            self.sendMessage(
                irc.ERR_NOSUCHNICK,
                params[0],
                ":No such nickname (could not decode your unicode!)",
            )
            return

        if channelOrUser.startswith("#"):

            def ebGroup(err):
                err.trap(ewords.NoSuchGroup)
                self.sendMessage(
                    irc.ERR_NOSUCHCHANNEL, params[0], ":That channel doesn't exist."
                )

            d = self.realm.lookupGroup(channelOrUser[1:])
            d.addCallbacks(self._channelMode, ebGroup, callbackArgs=tuple(params[1:]))
        else:

            def ebUser(err):
                self.sendMessage(irc.ERR_NOSUCHNICK, ":No such nickname.")

            d = self.realm.lookupUser(channelOrUser)
            d.addCallbacks(self._userMode, ebUser, callbackArgs=tuple(params[1:]))

    def irc_USERHOST(self, prefix, params):
        """
        Userhost message

        Parameters: <nickname> *( SPACE <nickname> )

        [Optional]
        """
        pass

    def irc_PRIVMSG(self, prefix, params):
        """
        Send a (private) message.

        Parameters: <msgtarget> <text to be sent>
        """
        try:
            targetName = params[0]
            if isinstance(targetName, bytes):
                targetName = targetName.decode(self.encoding)
        except UnicodeDecodeError:
            self.sendMessage(
                irc.ERR_NOSUCHNICK,
                params[0],
                ":No such nick/channel (could not decode your unicode!)",
            )
            return

        messageText = params[-1]
        if targetName.startswith("#"):
            target = self.realm.lookupGroup(targetName[1:])
        else:
            target = self.realm.lookupUser(targetName).addCallback(
                lambda user: user.mind
            )

        def cbTarget(targ):
            if targ is not None:
                return self.avatar.send(targ, {"text": messageText})

        def ebTarget(err):
            self.sendMessage(irc.ERR_NOSUCHNICK, targetName, ":No such nick/channel.")

        target.addCallbacks(cbTarget, ebTarget)

    def irc_JOIN(self, prefix, params):
        """
        Join message

        Parameters: ( <channel> *( "," <channel> ) [ <key> *( "," <key> ) ] )
        """
        try:
            groupName = params[0]
            if isinstance(groupName, bytes):
                groupName = groupName.decode(self.encoding)
        except UnicodeDecodeError:
            self.sendMessage(
                irc.ERR_NOSUCHCHANNEL,
                params[0],
                ":No such channel (could not decode your unicode!)",
            )
            return

        if groupName.startswith("#"):
            groupName = groupName[1:]

        def cbGroup(group):
            def cbJoin(ign):
                self.userJoined(group, self)
                self.names(
                    self.name,
                    "#" + group.name,
                    [user.name for user in group.iterusers()],
                )
                self._sendTopic(group)

            return self.avatar.join(group).addCallback(cbJoin)

        def ebGroup(err):
            self.sendMessage(
                irc.ERR_NOSUCHCHANNEL, "#" + groupName, ":No such channel."
            )

        self.realm.getGroup(groupName).addCallbacks(cbGroup, ebGroup)

    def irc_PART(self, prefix, params):
        """
        Part message

        Parameters: <channel> *( "," <channel> ) [ <Part Message> ]
        """
        try:
            groupName = params[0]
            if isinstance(params[0], bytes):
                groupName = params[0].decode(self.encoding)
        except UnicodeDecodeError:
            self.sendMessage(
                irc.ERR_NOTONCHANNEL, params[0], ":Could not decode your unicode!"
            )
            return

        if groupName.startswith("#"):
            groupName = groupName[1:]

        if len(params) > 1:
            reason = params[1]
            if isinstance(reason, bytes):
                reason = reason.decode("utf-8")
        else:
            reason = None

        def cbGroup(group):
            def cbLeave(result):
                self.userLeft(group, self, reason)

            return self.avatar.leave(group, reason).addCallback(cbLeave)

        def ebGroup(err):
            err.trap(ewords.NoSuchGroup)
            self.sendMessage(
                irc.ERR_NOTONCHANNEL, "#" + groupName, ":" + err.getErrorMessage()
            )

        self.realm.lookupGroup(groupName).addCallbacks(cbGroup, ebGroup)

    def irc_NAMES(self, prefix, params):
        """
        Names message

        Parameters: [ <channel> *( "," <channel> ) [ <target> ] ]
        """
        # << NAMES #python
        # >> :benford.openprojects.net 353 glyph = #python :Orban ... @glyph ... Zymurgy skreech
        # >> :benford.openprojects.net 366 glyph #python :End of /NAMES list.
        try:
            channel = params[-1]
            if isinstance(channel, bytes):
                channel = channel.decode(self.encoding)
        except UnicodeDecodeError:
            self.sendMessage(
                irc.ERR_NOSUCHCHANNEL,
                params[-1],
                ":No such channel (could not decode your unicode!)",
            )
            return

        if channel.startswith("#"):
            channel = channel[1:]

        def cbGroup(group):
            self.names(
                self.name, "#" + group.name, [user.name for user in group.iterusers()]
            )

        def ebGroup(err):
            err.trap(ewords.NoSuchGroup)
            # No group?  Fine, no names!
            self.names(self.name, "#" + channel, [])

        self.realm.lookupGroup(channel).addCallbacks(cbGroup, ebGroup)

    def irc_TOPIC(self, prefix, params):
        """
        Topic message

        Parameters: <channel> [ <topic> ]
        """
        try:
            channel = params[0]
            if isinstance(params[0], bytes):
                channel = channel.decode(self.encoding)
        except UnicodeDecodeError:
            self.sendMessage(
                irc.ERR_NOSUCHCHANNEL,
                ":That channel doesn't exist (could not decode your unicode!)",
            )
            return

        if channel.startswith("#"):
            channel = channel[1:]

        if len(params) > 1:
            self._setTopic(channel, params[1])
        else:
            self._getTopic(channel)

    def _sendTopic(self, group):
        """
        Send the topic of the given group to this user, if it has one.
        """
        topic = group.meta.get("topic")
        if topic:
            author = group.meta.get("topic_author") or "<noone>"
            date = group.meta.get("topic_date", 0)
            self.topic(self.name, "#" + group.name, topic)
            self.topicAuthor(self.name, "#" + group.name, author, date)

    def _getTopic(self, channel):
        # << TOPIC #python
        # >> :benford.openprojects.net 332 glyph #python :<churchr> I really did. I sprained all my toes.
        # >> :benford.openprojects.net 333 glyph #python itamar|nyc 994713482
        def ebGroup(err):
            err.trap(ewords.NoSuchGroup)
            self.sendMessage(
                irc.ERR_NOSUCHCHANNEL, "=", channel, ":That channel doesn't exist."
            )

        self.realm.lookupGroup(channel).addCallbacks(self._sendTopic, ebGroup)

    def _setTopic(self, channel, topic):
        # << TOPIC #divunal :foo
        # >> :glyph!glyph@adsl-64-123-27-108.dsl.austtx.swbell.net TOPIC #divunal :foo

        def cbGroup(group):
            newMeta = group.meta.copy()
            newMeta["topic"] = topic
            newMeta["topic_author"] = self.name
            newMeta["topic_date"] = int(time())

            def ebSet(err):
                self.sendMessage(
                    irc.ERR_CHANOPRIVSNEEDED,
                    "#" + group.name,
                    ":You need to be a channel operator to do that.",
                )

            return group.setMetadata(newMeta).addErrback(ebSet)

        def ebGroup(err):
            err.trap(ewords.NoSuchGroup)
            self.sendMessage(
                irc.ERR_NOSUCHCHANNEL, "=", channel, ":That channel doesn't exist."
            )

        self.realm.lookupGroup(channel).addCallbacks(cbGroup, ebGroup)

    def list(self, channels):
        """
        Send a group of LIST response lines

        @type channels: C{list} of C{(str, int, str)}
        @param channels: Information about the channels being sent:
            their name, the number of participants, and their topic.
        """
        for (name, size, topic) in channels:
            self.sendMessage(irc.RPL_LIST, name, str(size), ":" + topic)
        self.sendMessage(irc.RPL_LISTEND, ":End of /LIST")

    def irc_LIST(self, prefix, params):
        """
        List query

        Return information about the indicated channels, or about all
        channels if none are specified.

        Parameters: [ <channel> *( "," <channel> ) [ <target> ] ]
        """
        # << list #python
        # >> :orwell.freenode.net 321 exarkun Channel :Users  Name
        # >> :orwell.freenode.net 322 exarkun #python 358 :The Python programming language
        # >> :orwell.freenode.net 323 exarkun :End of /LIST
        if params:
            # Return information about indicated channels
            try:
                allChannels = params[0]
                if isinstance(allChannels, bytes):
                    allChannels = allChannels.decode(self.encoding)
                channels = allChannels.split(",")
            except UnicodeDecodeError:
                self.sendMessage(
                    irc.ERR_NOSUCHCHANNEL,
                    params[0],
                    ":No such channel (could not decode your unicode!)",
                )
                return

            groups = []
            for ch in channels:
                if ch.startswith("#"):
                    ch = ch[1:]
                groups.append(self.realm.lookupGroup(ch))

            groups = defer.DeferredList(groups, consumeErrors=True)
            groups.addCallback(lambda gs: [r for (s, r) in gs if s])
        else:
            # Return information about all channels
            groups = self.realm.itergroups()

        def cbGroups(groups):
            def gotSize(size, group):
                return group.name, size, group.meta.get("topic")

            d = defer.DeferredList(
                [group.size().addCallback(gotSize, group) for group in groups]
            )
            d.addCallback(lambda results: self.list([r for (s, r) in results if s]))
            return d

        groups.addCallback(cbGroups)

    def _channelWho(self, group):
        self.who(
            self.name,
            "#" + group.name,
            [
                (m.name, self.hostname, self.realm.name, m.name, "H", 0, m.name)
                for m in group.iterusers()
            ],
        )

    def _userWho(self, user):
        self.sendMessage(irc.RPL_ENDOFWHO, ":User /WHO not implemented")

    def irc_WHO(self, prefix, params):
        """
        Who query

        Parameters: [ <mask> [ "o" ] ]
        """
        # << who #python
        # >> :x.opn 352 glyph #python aquarius pc-62-31-193-114-du.blueyonder.co.uk y.opn Aquarius H :3 Aquarius
        # ...
        # >> :x.opn 352 glyph #python foobar europa.tranquility.net z.opn skreech H :0 skreech
        # >> :x.opn 315 glyph #python :End of /WHO list.
        ### also
        # << who glyph
        # >> :x.opn 352 glyph #python glyph adsl-64-123-27-108.dsl.austtx.swbell.net x.opn glyph H :0 glyph
        # >> :x.opn 315 glyph glyph :End of /WHO list.
        if not params:
            self.sendMessage(irc.RPL_ENDOFWHO, ":/WHO not supported.")
            return

        try:
            channelOrUser = params[0]
            if isinstance(channelOrUser, bytes):
                channelOrUser = channelOrUser.decode(self.encoding)
        except UnicodeDecodeError:
            self.sendMessage(
                irc.RPL_ENDOFWHO,
                params[0],
                ":End of /WHO list (could not decode your unicode!)",
            )
            return

        if channelOrUser.startswith("#"):

            def ebGroup(err):
                err.trap(ewords.NoSuchGroup)
                self.sendMessage(irc.RPL_ENDOFWHO, channelOrUser, ":End of /WHO list.")

            d = self.realm.lookupGroup(channelOrUser[1:])
            d.addCallbacks(self._channelWho, ebGroup)
        else:

            def ebUser(err):
                err.trap(ewords.NoSuchUser)
                self.sendMessage(irc.RPL_ENDOFWHO, channelOrUser, ":End of /WHO list.")

            d = self.realm.lookupUser(channelOrUser)
            d.addCallbacks(self._userWho, ebUser)

    def irc_WHOIS(self, prefix, params):
        """
        Whois query

        Parameters: [ <target> ] <mask> *( "," <mask> )
        """

        def cbUser(user):
            self.whois(
                self.name,
                user.name,
                user.name,
                self.realm.name,
                user.name,
                self.realm.name,
                "Hi mom!",
                False,
                int(time() - user.lastMessage),
                user.signOn,
                ["#" + group.name for group in user.itergroups()],
            )

        def ebUser(err):
            err.trap(ewords.NoSuchUser)
            self.sendMessage(irc.ERR_NOSUCHNICK, params[0], ":No such nick/channel")

        try:
            user = params[0]
            if isinstance(user, bytes):
                user = user.decode(self.encoding)
        except UnicodeDecodeError:
            self.sendMessage(irc.ERR_NOSUCHNICK, params[0], ":No such nick/channel")
            return

        self.realm.lookupUser(user).addCallbacks(cbUser, ebUser)

    # Unsupported commands, here for legacy compatibility
    def irc_OPER(self, prefix, params):
        """
        Oper message

        Parameters: <name> <password>
        """
        self.sendMessage(irc.ERR_NOOPERHOST, ":O-lines not applicable")


class IRCFactory(protocol.ServerFactory):
    """
    IRC server that creates instances of the L{IRCUser} protocol.

    @ivar _serverInfo: A dictionary mapping:
        "serviceName" to the name of the server,
        "serviceVersion" to the copyright version,
        "creationDate" to the time that the server was started.
    """

    protocol = IRCUser

    def __init__(self, realm, portal):
        self.realm = realm
        self.portal = portal
        self._serverInfo = {
            "serviceName": self.realm.name,
            "serviceVersion": copyright.version,
            "creationDate": ctime(),
        }


class PBMind(pb.Referenceable):
    def __init__(self):
        pass

    def jellyFor(self, jellier):
        qual = reflect.qual(PBMind)
        if isinstance(qual, str):
            qual = qual.encode("utf-8")
        return qual, jellier.invoker.registerReference(self)

    def remote_userJoined(self, user, group):
        pass

    def remote_userLeft(self, user, group, reason):
        pass

    def remote_receive(self, sender, recipient, message):
        pass

    def remote_groupMetaUpdate(self, group, meta):
        pass


@implementer(iwords.IChatClient)
class PBMindReference(pb.RemoteReference):

    name = ""

    def receive(self, sender, recipient, message):
        if iwords.IGroup.providedBy(recipient):
            rec = PBGroup(self.realm, self.avatar, recipient)
        else:
            rec = PBUser(self.realm, self.avatar, recipient)
        return self.callRemote(
            "receive", PBUser(self.realm, self.avatar, sender), rec, message
        )

    def groupMetaUpdate(self, group, meta):
        return self.callRemote(
            "groupMetaUpdate", PBGroup(self.realm, self.avatar, group), meta
        )

    def userJoined(self, group, user):
        return self.callRemote(
            "userJoined",
            PBGroup(self.realm, self.avatar, group),
            PBUser(self.realm, self.avatar, user),
        )

    def userLeft(self, group, user, reason=None):
        return self.callRemote(
            "userLeft",
            PBGroup(self.realm, self.avatar, group),
            PBUser(self.realm, self.avatar, user),
            reason,
        )


pb.setUnjellyableForClass(PBMind, PBMindReference)


class PBGroup(pb.Referenceable):
    def __init__(self, realm, avatar, group):
        self.realm = realm
        self.avatar = avatar
        self.group = group

    def processUniqueID(self):
        return hash((self.realm.name, self.avatar.name, self.group.name))

    def jellyFor(self, jellier):
        qual = reflect.qual(self.__class__)
        if isinstance(qual, str):
            qual = qual.encode("utf-8")
        group = self.group.name
        if isinstance(group, str):
            group = group.encode("utf-8")
        return qual, group, jellier.invoker.registerReference(self)

    def remote_leave(self, reason=None):
        return self.avatar.leave(self.group, reason)

    def remote_send(self, message):
        return self.avatar.send(self.group, message)


@implementer(iwords.IGroup)
class PBGroupReference(pb.RemoteReference):
    def unjellyFor(self, unjellier, unjellyList):
        clsName, name, ref = unjellyList
        self.name = name
        if bytes != str and isinstance(self.name, bytes):
            self.name = self.name.decode("utf-8")
        return pb.RemoteReference.unjellyFor(self, unjellier, [clsName, ref])

    def leave(self, reason=None):
        return self.callRemote("leave", reason)

    def send(self, message):
        return self.callRemote("send", message)

    def add(self, user):
        # IGroup.add
        pass

    def iterusers(self):
        # IGroup.iterusers
        pass

    def receive(self, sender, recipient, message):
        # IGroup.receive
        pass

    def remove(self, user, reason=None):
        # IGroup.remove
        pass

    def setMetadata(self, meta):
        # IGroup.setMetadata
        pass

    def size(self):
        # IGroup.size
        pass


pb.setUnjellyableForClass(PBGroup, PBGroupReference)


class PBUser(pb.Referenceable):
    def __init__(self, realm, avatar, user):
        self.realm = realm
        self.avatar = avatar
        self.user = user

    def processUniqueID(self):
        return hash((self.realm.name, self.avatar.name, self.user.name))


@implementer(iwords.IChatClient)
class ChatAvatar(pb.Referenceable):
    def __init__(self, avatar):
        self.avatar = avatar

    def jellyFor(self, jellier):
        qual = reflect.qual(self.__class__)
        if isinstance(qual, str):
            qual = qual.encode("utf-8")
        return qual, jellier.invoker.registerReference(self)

    def remote_join(self, groupName):
        def cbGroup(group):
            def cbJoin(ignored):
                return PBGroup(self.avatar.realm, self.avatar, group)

            d = self.avatar.join(group)
            d.addCallback(cbJoin)
            return d

        d = self.avatar.realm.getGroup(groupName)
        d.addCallback(cbGroup)
        return d

    @property
    def name(self):
        # IChatClient.name
        pass

    @name.setter
    def name(self, value):
        # IChatClient.name
        pass

    def groupMetaUpdate(self, group, meta):
        # IChatClient.groupMetaUpdate
        pass

    def receive(self, sender, recipient, message):
        # IChatClient.receive
        pass

    def userJoined(self, group, user):
        # IChatClient.userJoined
        pass

    def userLeft(self, group, user, reason=None):
        # IChatClient.userLeft
        pass


registerAdapter(ChatAvatar, iwords.IUser, pb.IPerspective)


class AvatarReference(pb.RemoteReference):
    def join(self, groupName):
        return self.callRemote("join", groupName)

    def quit(self):
        d = defer.Deferred()
        self.broker.notifyOnDisconnect(lambda: d.callback(None))
        self.broker.transport.loseConnection()
        return d


pb.setUnjellyableForClass(ChatAvatar, AvatarReference)


@implementer(portal.IRealm, iwords.IChatService)
class WordsRealm:
    _encoding = "utf-8"

    def __init__(self, name):
        self.name = name

    def userFactory(self, name):
        return User(name)

    def groupFactory(self, name):
        return Group(name)

    def logoutFactory(self, avatar, facet):
        def logout():
            # XXX Deferred support here
            getattr(facet, "logout", lambda: None)()
            avatar.realm = avatar.mind = None

        return logout

    def requestAvatar(self, avatarId, mind, *interfaces):
        if isinstance(avatarId, bytes):
            avatarId = avatarId.decode(self._encoding)

        def gotAvatar(avatar):
            if avatar.realm is not None:
                raise ewords.AlreadyLoggedIn()
            for iface in interfaces:
                facet = iface(avatar, None)
                if facet is not None:
                    avatar.loggedIn(self, mind)
                    mind.name = avatarId
                    mind.realm = self
                    mind.avatar = avatar
                    return iface, facet, self.logoutFactory(avatar, facet)
            raise NotImplementedError(self, interfaces)

        return self.getUser(avatarId).addCallback(gotAvatar)

    def itergroups(self):
        # IChatServer.itergroups
        pass

    # IChatService, mostly.
    createGroupOnRequest = False
    createUserOnRequest = True

    def lookupUser(self, name):
        raise NotImplementedError

    def lookupGroup(self, group):
        raise NotImplementedError

    def addUser(self, user):
        """
        Add the given user to this service.

        This is an internal method intended to be overridden by
        L{WordsRealm} subclasses, not called by external code.

        @type user: L{IUser}

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires with L{None} when the user is
        added, or which fails with
        L{twisted.words.ewords.DuplicateUser} if a user with the
        same name exists already.
        """
        raise NotImplementedError

    def addGroup(self, group):
        """
        Add the given group to this service.

        @type group: L{IGroup}

        @rtype: L{twisted.internet.defer.Deferred}
        @return: A Deferred which fires with L{None} when the group is
        added, or which fails with
        L{twisted.words.ewords.DuplicateGroup} if a group with the
        same name exists already.
        """
        raise NotImplementedError

    def getGroup(self, name):
        if self.createGroupOnRequest:

            def ebGroup(err):
                err.trap(ewords.DuplicateGroup)
                return self.lookupGroup(name)

            return self.createGroup(name).addErrback(ebGroup)
        return self.lookupGroup(name)

    def getUser(self, name):
        if self.createUserOnRequest:

            def ebUser(err):
                err.trap(ewords.DuplicateUser)
                return self.lookupUser(name)

            return self.createUser(name).addErrback(ebUser)
        return self.lookupUser(name)

    def createUser(self, name):
        def cbLookup(user):
            return failure.Failure(ewords.DuplicateUser(name))

        def ebLookup(err):
            err.trap(ewords.NoSuchUser)
            return self.userFactory(name)

        name = name.lower()
        d = self.lookupUser(name)
        d.addCallbacks(cbLookup, ebLookup)
        d.addCallback(self.addUser)
        return d

    def createGroup(self, name):
        def cbLookup(group):
            return failure.Failure(ewords.DuplicateGroup(name))

        def ebLookup(err):
            err.trap(ewords.NoSuchGroup)
            return self.groupFactory(name)

        name = name.lower()
        d = self.lookupGroup(name)
        d.addCallbacks(cbLookup, ebLookup)
        d.addCallback(self.addGroup)
        return d


class InMemoryWordsRealm(WordsRealm):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.users = {}
        self.groups = {}

    def itergroups(self):
        return defer.succeed(self.groups.values())

    def addUser(self, user):
        if user.name in self.users:
            return defer.fail(failure.Failure(ewords.DuplicateUser()))
        self.users[user.name] = user
        return defer.succeed(user)

    def addGroup(self, group):
        if group.name in self.groups:
            return defer.fail(failure.Failure(ewords.DuplicateGroup()))
        self.groups[group.name] = group
        return defer.succeed(group)

    def lookupUser(self, name):
        name = name.lower()
        try:
            user = self.users[name]
        except KeyError:
            return defer.fail(failure.Failure(ewords.NoSuchUser(name)))
        else:
            return defer.succeed(user)

    def lookupGroup(self, name):
        name = name.lower()
        try:
            group = self.groups[name]
        except KeyError:
            return defer.fail(failure.Failure(ewords.NoSuchGroup(name)))
        else:
            return defer.succeed(group)


__all__ = [
    "Group",
    "User",
    "WordsRealm",
    "InMemoryWordsRealm",
]
