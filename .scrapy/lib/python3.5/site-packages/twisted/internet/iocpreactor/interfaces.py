# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Interfaces for iocpreactor
"""


from zope.interface import Interface



class IReadHandle(Interface):
    def readFromHandle(bufflist, evt):
        """
        Read into the given buffers from this handle.

        @param buff: the buffers to read into
        @type buff: list of objects implementing the read/write buffer protocol

        @param evt: an IOCP Event object

        @return: tuple (return code, number of bytes read)
        """



class IWriteHandle(Interface):
    def writeToHandle(buff, evt):
        """
        Write the given buffer to this handle.

        @param buff: the buffer to write
        @type buff: any object implementing the buffer protocol

        @param evt: an IOCP Event object

        @return: tuple (return code, number of bytes written)
        """



class IReadWriteHandle(IReadHandle, IWriteHandle):
    pass


