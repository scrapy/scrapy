# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


import os

from twisted.spread import pb


class Maildir(pb.Referenceable):
    def __init__(self, directory, rootDirectory):
        self.virtualDirectory = directory
        self.rootDirectory = rootDirectory
        self.directory = os.path.join(rootDirectory, directory)

    def getFolderMessage(self, folder, name):
        if "/" in name:
            raise OSError("can only open files in '%s' directory'" % folder)
        with open(os.path.join(self.directory, "new", name)) as fp:
            return fp.read()

    def deleteFolderMessage(self, folder, name):
        if "/" in name:
            raise OSError("can only delete files in '%s' directory'" % folder)
        os.rename(
            os.path.join(self.directory, folder, name),
            os.path.join(self.rootDirectory, ".Trash", folder, name),
        )

    def deleteNewMessage(self, name):
        return self.deleteFolderMessage("new", name)

    remote_deleteNewMessage = deleteNewMessage

    def deleteCurMessage(self, name):
        return self.deleteFolderMessage("cur", name)

    remote_deleteCurMessage = deleteCurMessage

    def getNewMessages(self):
        return os.listdir(os.path.join(self.directory, "new"))

    remote_getNewMessages = getNewMessages

    def getCurMessages(self):
        return os.listdir(os.path.join(self.directory, "cur"))

    remote_getCurMessages = getCurMessages

    def getNewMessage(self, name):
        return self.getFolderMessage("new", name)

    remote_getNewMessage = getNewMessage

    def getCurMessage(self, name):
        return self.getFolderMessage("cur", name)

    remote_getCurMessage = getCurMessage

    def getSubFolder(self, name):
        if name[0] == ".":
            raise OSError("subfolder name cannot begin with a '.'")
        name = name.replace("/", ":")
        if self.virtualDirectoy == ".":
            name = "." + name
        else:
            name = self.virtualDirectory + ":" + name
        if not self._isSubFolder(name):
            raise OSError("not a subfolder")
        return Maildir(name, self.rootDirectory)

    remote_getSubFolder = getSubFolder

    def _isSubFolder(self, name):
        return not os.path.isdir(
            os.path.join(self.rootDirectory, name)
        ) or not os.path.isfile(os.path.join(self.rootDirectory, name, "maildirfolder"))


class MaildirCollection(pb.Referenceable):
    def __init__(self, root):
        self.root = root

    def getSubFolders(self):
        return os.listdir(self.getRoot())

    remote_getSubFolders = getSubFolders

    def getSubFolder(self, name):
        if "/" in name or name[0] == ".":
            raise OSError("invalid name")
        return Maildir(".", os.path.join(self.getRoot(), name))

    remote_getSubFolder = getSubFolder


class MaildirBroker(pb.Broker):
    def proto_getCollection(self, requestID, name, domain, password):
        collection = self._getCollection()
        if collection is None:
            self.sendError(requestID, "permission denied")
        else:
            self.sendAnswer(requestID, collection)

    def getCollection(self, name, domain, password):
        if domain not in self.domains:
            return
        domain = self.domains[domain]
        if name in domain.dbm and domain.dbm[name] == password:
            return MaildirCollection(domain.userDirectory(name))


class MaildirClient(pb.Broker):
    def getCollection(self, name, domain, password, callback, errback):
        requestID = self.newRequestID()
        self.waitingForAnswers[requestID] = callback, errback
        self.sendCall("getCollection", requestID, name, domain, password)
