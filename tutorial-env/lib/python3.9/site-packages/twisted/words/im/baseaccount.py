# -*- Python -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

#


class AccountManager:
    """I am responsible for managing a user's accounts.

    That is, remembering what accounts are available, their settings,
    adding and removal of accounts, etc.

    @ivar accounts: A collection of available accounts.
    @type accounts: mapping of strings to L{Account<interfaces.IAccount>}s.
    """

    def __init__(self):
        self.accounts = {}

    def getSnapShot(self):
        """A snapshot of all the accounts and their status.

        @returns: A list of tuples, each of the form
            (string:accountName, boolean:isOnline,
            boolean:autoLogin, string:gatewayType)
        """
        data = []
        for account in self.accounts.values():
            data.append(
                (
                    account.accountName,
                    account.isOnline(),
                    account.autoLogin,
                    account.gatewayType,
                )
            )
        return data

    def isEmpty(self):
        return len(self.accounts) == 0

    def getConnectionInfo(self):
        connectioninfo = []
        for account in self.accounts.values():
            connectioninfo.append(account.isOnline())
        return connectioninfo

    def addAccount(self, account):
        self.accounts[account.accountName] = account

    def delAccount(self, accountName):
        del self.accounts[accountName]

    def connect(self, accountName, chatui):
        """
        @returntype: Deferred L{interfaces.IClient}
        """
        return self.accounts[accountName].logOn(chatui)

    def disconnect(self, accountName):
        pass
        # self.accounts[accountName].logOff()  - not yet implemented

    def quit(self):
        pass
        # for account in self.accounts.values():
        #    account.logOff()  - not yet implemented
