# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This module contains interfaces defined for the L{twisted.conch} package.
"""

from zope.interface import Attribute, Interface


class IConchUser(Interface):
    """
    A user who has been authenticated to Cred through Conch.  This is
    the interface between the SSH connection and the user.
    """

    conn = Attribute("The SSHConnection object for this user.")

    def lookupChannel(channelType, windowSize, maxPacket, data):
        """
        The other side requested a channel of some sort.

        C{channelType} is the type of channel being requested,
        as an ssh connection protocol channel type.
        C{data} is any other packet data (often nothing).

        We return a subclass of L{SSHChannel<ssh.channel.SSHChannel>}.  If
        the channel type is unknown, we return C{None}.

        For other failures, we raise an exception. If a
        L{ConchError<error.ConchError>} is raised, the C{.value} will
        be the message, and the C{.data} will be the error code.

        @param channelType: The requested channel type
        @type channelType:  L{bytes}
        @param windowSize:  The initial size of the remote window
        @type windowSize:   L{int}
        @param maxPacket:   The largest packet we should send
        @type maxPacket:    L{int}
        @param data:        Additional request data
        @type data:         L{bytes}
        @rtype:             a subclass of L{SSHChannel} or L{None}
        """

    def lookupSubsystem(subsystem, data):
        """
        The other side requested a subsystem.

        We return a L{Protocol} implementing the requested subsystem.
        If the subsystem is not available, we return C{None}.

        @param subsystem: The name of the subsystem being requested
        @type subsystem: L{bytes}
        @param data:     Additional request data (often nothing)
        @type data:      L{bytes}
        @rtype:          L{Protocol} or L{None}
        """

    def gotGlobalRequest(requestType, data):
        """
        A global request was sent from the other side.

        We return a true value on success or a false value on failure.
        If we indicate success by returning a tuple, its second item
        will be sent to the other side as additional response data.

        @param requestType: The type of the request
        @type requestType:  L{bytes}
        @param data:        Additional request data
        @type data:         L{bytes}
        @rtype:             boolean or L{tuple}
        """


class ISession(Interface):
    def getPty(term, windowSize, modes):
        """
        Get a pseudo-terminal for use by a shell or command.

        If a pseudo-terminal is not available, or the request otherwise
        fails, raise an exception.
        """

    def openShell(proto):
        """
        Open a shell and connect it to proto.

        @param proto: a L{ProcessProtocol} instance.
        """

    def execCommand(proto, command):
        """
        Execute a command.

        @param proto: a L{ProcessProtocol} instance.
        """

    def windowChanged(newWindowSize):
        """
        Called when the size of the remote screen has changed.
        """

    def eofReceived():
        """
        Called when the other side has indicated no more data will be sent.
        """

    def closed():
        """
        Called when the session is closed.
        """


class EnvironmentVariableNotPermitted(ValueError):
    """Setting this environment variable in this session is not permitted."""


class ISessionSetEnv(Interface):
    """A session that can set environment variables."""

    def setEnv(name, value):
        """
        Set an environment variable for the shell or command to be started.

        From U{RFC 4254, section 6.4
        <https://tools.ietf.org/html/rfc4254#section-6.4>}: "Uncontrolled
        setting of environment variables in a privileged process can be a
        security hazard.  It is recommended that implementations either
        maintain a list of allowable variable names or only set environment
        variables after the server process has dropped sufficient
        privileges."

        (OpenSSH refuses all environment variables by default, but has an
        C{AcceptEnv} configuration option to select specific variables to
        accept.)

        @param name: The name of the environment variable to set.
        @type name: L{bytes}
        @param value: The value of the environment variable to set.
        @type value: L{bytes}
        @raise EnvironmentVariableNotPermitted: if setting this environment
            variable is not permitted.
        """


class ISFTPServer(Interface):
    """
    SFTP subsystem for server-side communication.

    Each method should check to verify that the user has permission for
    their actions.
    """

    avatar = Attribute(
        """
        The avatar returned by the Realm that we are authenticated with,
        and represents the logged-in user.
        """
    )

    def gotVersion(otherVersion, extData):
        """
        Called when the client sends their version info.

        otherVersion is an integer representing the version of the SFTP
        protocol they are claiming.
        extData is a dictionary of extended_name : extended_data items.
        These items are sent by the client to indicate additional features.

        This method should return a dictionary of extended_name : extended_data
        items.  These items are the additional features (if any) supported
        by the server.
        """
        return {}

    def openFile(filename, flags, attrs):
        """
        Called when the clients asks to open a file.

        @param filename: a string representing the file to open.

        @param flags: an integer of the flags to open the file with, ORed
        together.  The flags and their values are listed at the bottom of
        L{twisted.conch.ssh.filetransfer} as FXF_*.

        @param attrs: a list of attributes to open the file with.  It is a
        dictionary, consisting of 0 or more keys.  The possible keys are::

            size: the size of the file in bytes
            uid: the user ID of the file as an integer
            gid: the group ID of the file as an integer
            permissions: the permissions of the file with as an integer.
            the bit representation of this field is defined by POSIX.
            atime: the access time of the file as seconds since the epoch.
            mtime: the modification time of the file as seconds since the epoch.
            ext_*: extended attributes.  The server is not required to
            understand this, but it may.

        NOTE: there is no way to indicate text or binary files.  it is up
        to the SFTP client to deal with this.

        This method returns an object that meets the ISFTPFile interface.
        Alternatively, it can return a L{Deferred} that will be called back
        with the object.
        """

    def removeFile(filename):
        """
        Remove the given file.

        This method returns when the remove succeeds, or a Deferred that is
        called back when it succeeds.

        @param filename: the name of the file as a string.
        """

    def renameFile(oldpath, newpath):
        """
        Rename the given file.

        This method returns when the rename succeeds, or a L{Deferred} that is
        called back when it succeeds. If the rename fails, C{renameFile} will
        raise an implementation-dependent exception.

        @param oldpath: the current location of the file.
        @param newpath: the new file name.
        """

    def makeDirectory(path, attrs):
        """
        Make a directory.

        This method returns when the directory is created, or a Deferred that
        is called back when it is created.

        @param path: the name of the directory to create as a string.
        @param attrs: a dictionary of attributes to create the directory with.
        Its meaning is the same as the attrs in the L{openFile} method.
        """

    def removeDirectory(path):
        """
        Remove a directory (non-recursively)

        It is an error to remove a directory that has files or directories in
        it.

        This method returns when the directory is removed, or a Deferred that
        is called back when it is removed.

        @param path: the directory to remove.
        """

    def openDirectory(path):
        """
        Open a directory for scanning.

        This method returns an iterable object that has a close() method,
        or a Deferred that is called back with same.

        The close() method is called when the client is finished reading
        from the directory.  At this point, the iterable will no longer
        be used.

        The iterable should return triples of the form (filename,
        longname, attrs) or Deferreds that return the same.  The
        sequence must support __getitem__, but otherwise may be any
        'sequence-like' object.

        filename is the name of the file relative to the directory.
        logname is an expanded format of the filename.  The recommended format
        is:
        -rwxr-xr-x   1 mjos     staff      348911 Mar 25 14:29 t-filexfer
        1234567890 123 12345678 12345678 12345678 123456789012

        The first line is sample output, the second is the length of the field.
        The fields are: permissions, link count, user owner, group owner,
        size in bytes, modification time.

        attrs is a dictionary in the format of the attrs argument to openFile.

        @param path: the directory to open.
        """

    def getAttrs(path, followLinks):
        """
        Return the attributes for the given path.

        This method returns a dictionary in the same format as the attrs
        argument to openFile or a Deferred that is called back with same.

        @param path: the path to return attributes for as a string.
        @param followLinks: a boolean.  If it is True, follow symbolic links
        and return attributes for the real path at the base.  If it is False,
        return attributes for the specified path.
        """

    def setAttrs(path, attrs):
        """
        Set the attributes for the path.

        This method returns when the attributes are set or a Deferred that is
        called back when they are.

        @param path: the path to set attributes for as a string.
        @param attrs: a dictionary in the same format as the attrs argument to
        L{openFile}.
        """

    def readLink(path):
        """
        Find the root of a set of symbolic links.

        This method returns the target of the link, or a Deferred that
        returns the same.

        @param path: the path of the symlink to read.
        """

    def makeLink(linkPath, targetPath):
        """
        Create a symbolic link.

        This method returns when the link is made, or a Deferred that
        returns the same.

        @param linkPath: the pathname of the symlink as a string.
        @param targetPath: the path of the target of the link as a string.
        """

    def realPath(path):
        """
        Convert any path to an absolute path.

        This method returns the absolute path as a string, or a Deferred
        that returns the same.

        @param path: the path to convert as a string.
        """

    def extendedRequest(extendedName, extendedData):
        """
        This is the extension mechanism for SFTP.  The other side can send us
        arbitrary requests.

        If we don't implement the request given by extendedName, raise
        NotImplementedError.

        The return value is a string, or a Deferred that will be called
        back with a string.

        @param extendedName: the name of the request as a string.
        @param extendedData: the data the other side sent with the request,
        as a string.
        """


class IKnownHostEntry(Interface):
    """
    A L{IKnownHostEntry} is an entry in an OpenSSH-formatted C{known_hosts}
    file.

    @since: 8.2
    """

    def matchesKey(key):
        """
        Return True if this entry matches the given Key object, False
        otherwise.

        @param key: The key object to match against.
        @type key: L{twisted.conch.ssh.keys.Key}
        """

    def matchesHost(hostname):
        """
        Return True if this entry matches the given hostname, False otherwise.

        Note that this does no name resolution; if you want to match an IP
        address, you have to resolve it yourself, and pass it in as a dotted
        quad string.

        @param hostname: The hostname to match against.
        @type hostname: L{str}
        """

    def toString():
        """

        @return: a serialized string representation of this entry, suitable for
        inclusion in a known_hosts file.  (Newline not included.)

        @rtype: L{str}
        """


class ISFTPFile(Interface):
    """
    This represents an open file on the server.  An object adhering to this
    interface should be returned from L{openFile}().
    """

    def close():
        """
        Close the file.

        This method returns nothing if the close succeeds immediately, or a
        Deferred that is called back when the close succeeds.
        """

    def readChunk(offset, length):
        """
        Read from the file.

        If EOF is reached before any data is read, raise EOFError.

        This method returns the data as a string, or a Deferred that is
        called back with same.

        @param offset: an integer that is the index to start from in the file.
        @param length: the maximum length of data to return.  The actual amount
        returned may less than this.  For normal disk files, however,
        this should read the requested number (up to the end of the file).
        """

    def writeChunk(offset, data):
        """
        Write to the file.

        This method returns when the write completes, or a Deferred that is
        called when it completes.

        @param offset: an integer that is the index to start from in the file.
        @param data: a string that is the data to write.
        """

    def getAttrs():
        """
        Return the attributes for the file.

        This method returns a dictionary in the same format as the attrs
        argument to L{openFile} or a L{Deferred} that is called back with same.
        """

    def setAttrs(attrs):
        """
        Set the attributes for the file.

        This method returns when the attributes are set or a Deferred that is
        called back when they are.

        @param attrs: a dictionary in the same format as the attrs argument to
        L{openFile}.
        """
