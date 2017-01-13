# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Serial port support for Windows.

Requires PySerial and pywin32.
"""

from __future__ import division, absolute_import

# system imports
from serial import PARITY_NONE
from serial import STOPBITS_ONE
from serial import EIGHTBITS
import win32file, win32event

# twisted imports
from twisted.internet import abstract

# sibling imports
from twisted.internet.serialport import BaseSerialPort


class SerialPort(BaseSerialPort, abstract.FileDescriptor):
    """A serial device, acting as a transport, that uses a win32 event."""

    connected = 1

    def __init__(self, protocol, deviceNameOrPortNumber, reactor, 
        baudrate = 9600, bytesize = EIGHTBITS, parity = PARITY_NONE,
        stopbits = STOPBITS_ONE, xonxoff = 0, rtscts = 0):
        self._serial = self._serialFactory(
            deviceNameOrPortNumber, baudrate=baudrate, bytesize=bytesize,
            parity=parity, stopbits=stopbits, timeout=None,
            xonxoff=xonxoff, rtscts=rtscts)
        self.flushInput()
        self.flushOutput()
        self.reactor = reactor
        self.protocol = protocol
        self.outQueue = []
        self.closed = 0
        self.closedNotifies = 0
        self.writeInProgress = 0

        self.protocol = protocol
        self._overlappedRead = win32file.OVERLAPPED()
        self._overlappedRead.hEvent = win32event.CreateEvent(None, 1, 0, None)
        self._overlappedWrite = win32file.OVERLAPPED()
        self._overlappedWrite.hEvent = win32event.CreateEvent(None, 0, 0, None)

        self.reactor.addEvent(self._overlappedRead.hEvent, self, 'serialReadEvent')
        self.reactor.addEvent(self._overlappedWrite.hEvent, self, 'serialWriteEvent')

        self.protocol.makeConnection(self)
        self._finishPortSetup()


    def _finishPortSetup(self):
        """
        Finish setting up the serial port.

        This is a separate method to facilitate testing.
        """
        flags, comstat = win32file.ClearCommError(self._serial.hComPort)
        rc, self.read_buf = win32file.ReadFile(self._serial.hComPort,
                                               win32file.AllocateReadBuffer(1),
                                               self._overlappedRead)


    def serialReadEvent(self):
        #get that character we set up
        n = win32file.GetOverlappedResult(self._serial.hComPort, self._overlappedRead, 0)
        if n:
            first = str(self.read_buf[:n])
            #now we should get everything that is already in the buffer
            flags, comstat = win32file.ClearCommError(self._serial.hComPort)
            if comstat.cbInQue:
                win32event.ResetEvent(self._overlappedRead.hEvent)
                rc, buf = win32file.ReadFile(self._serial.hComPort,
                                             win32file.AllocateReadBuffer(comstat.cbInQue),
                                             self._overlappedRead)
                n = win32file.GetOverlappedResult(self._serial.hComPort, self._overlappedRead, 1)
                #handle all the received data:
                self.protocol.dataReceived(first + str(buf[:n]))
            else:
                #handle all the received data:
                self.protocol.dataReceived(first)

        #set up next one
        win32event.ResetEvent(self._overlappedRead.hEvent)
        rc, self.read_buf = win32file.ReadFile(self._serial.hComPort,
                                               win32file.AllocateReadBuffer(1),
                                               self._overlappedRead)


    def write(self, data):
        if data:
            if self.writeInProgress:
                self.outQueue.append(data)
            else:
                self.writeInProgress = 1
                win32file.WriteFile(self._serial.hComPort, data, self._overlappedWrite)


    def serialWriteEvent(self):
        try:
            dataToWrite = self.outQueue.pop(0)
        except IndexError:
            self.writeInProgress = 0
            return
        else:
            win32file.WriteFile(self._serial.hComPort, dataToWrite, self._overlappedWrite)


    def connectionLost(self, reason):
        """
        Called when the serial port disconnects.

        Will call C{connectionLost} on the protocol that is handling the
        serial data.
        """
        self.reactor.removeEvent(self._overlappedRead.hEvent)
        self.reactor.removeEvent(self._overlappedWrite.hEvent)
        abstract.FileDescriptor.connectionLost(self, reason)
        self._serial.close()
        self.protocol.connectionLost(reason)
