# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.


"""
pyftpdlib: RFC-959 asynchronous FTP server.

pyftpdlib implements a fully functioning asynchronous FTP server as
defined in RFC-959.  A hierarchy of classes outlined below implement
the backend functionality for the FTPd:

    [pyftpdlib.ftpservers.FTPServer]
      accepts connections and dispatches them to a handler

    [pyftpdlib.handlers.FTPHandler]
      a class representing the server-protocol-interpreter
      (server-PI, see RFC-959). Each time a new connection occurs
      FTPServer will create a new FTPHandler instance to handle the
      current PI session.

    [pyftpdlib.handlers.ActiveDTP]
    [pyftpdlib.handlers.PassiveDTP]
      base classes for active/passive-DTP backends.

    [pyftpdlib.handlers.DTPHandler]
      this class handles processing of data transfer operations (server-DTP,
      see RFC-959).

    [pyftpdlib.authorizers.DummyAuthorizer]
      an "authorizer" is a class handling FTPd authentications and
      permissions. It is used inside FTPHandler class to verify user
      passwords, to get user's home directory and to get permissions
      when a filesystem read/write occurs. "DummyAuthorizer" is the
      base authorizer class providing a platform independent interface
      for managing virtual users.

    [pyftpdlib.filesystems.AbstractedFS]
      class used to interact with the file system, providing a high level,
      cross-platform interface compatible with both Windows and UNIX style
      filesystems.

Usage example:

>>> from pyftpdlib.authorizers import DummyAuthorizer
>>> from pyftpdlib.handlers import FTPHandler
>>> from pyftpdlib.servers import FTPServer
>>>
>>> authorizer = DummyAuthorizer()
>>> authorizer.add_user("user", "12345", "/home/giampaolo", perm="elradfmwMT")
>>> authorizer.add_anonymous("/home/nobody")
>>>
>>> handler = FTPHandler
>>> handler.authorizer = authorizer
>>>
>>> server = FTPServer(("127.0.0.1", 21), handler)
>>> server.serve_forever()
[I 13-02-19 10:55:42] >>> starting FTP server on 127.0.0.1:21 <<<
[I 13-02-19 10:55:42] poller: <class 'pyftpdlib.ioloop.Epoll'>
[I 13-02-19 10:55:42] masquerade (NAT) address: None
[I 13-02-19 10:55:42] passive ports: None
[I 13-02-19 10:55:42] use sendfile(2): True
[I 13-02-19 10:55:45] 127.0.0.1:34178-[] FTP session opened (connect)
[I 13-02-19 10:55:48] 127.0.0.1:34178-[user] USER 'user' logged in.
[I 13-02-19 10:56:27] 127.0.0.1:34179-[user] RETR /home/giampaolo/.vimrc
                      completed=1 bytes=1700 seconds=0.001
[I 13-02-19 10:56:39] 127.0.0.1:34179-[user] FTP session closed (disconnect).
"""


__ver__ = '1.5.9'
__author__ = "Giampaolo Rodola' <g.rodola@gmail.com>"
__web__ = 'https://github.com/giampaolo/pyftpdlib/'
