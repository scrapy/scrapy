# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Serial Port Protocol
"""

from __future__ import division, absolute_import

# http://twistedmatrix.com/trac/ticket/3725#comment:24
# Apparently applications use these names even though they should
# be imported from pyserial
__all__ = ["serial", "PARITY_ODD", "PARITY_EVEN", "PARITY_NONE",
           "STOPBITS_TWO", "STOPBITS_ONE", "FIVEBITS",
           "EIGHTBITS", "SEVENBITS", "SIXBITS",
# Name this module is actually trying to export
           "SerialPort"]

# all of them require pyserial at the moment, so check that first
import serial
from serial import PARITY_NONE, PARITY_EVEN, PARITY_ODD
from serial import STOPBITS_ONE, STOPBITS_TWO
from serial import FIVEBITS, SIXBITS, SEVENBITS, EIGHTBITS

from twisted.python.runtime import platform



class BaseSerialPort:
    """
    Base class for Windows and POSIX serial ports.

    @ivar _serialFactory: a pyserial C{serial.Serial} factory, used to create
        the instance stored in C{self._serial}. Overrideable to enable easier
        testing.

    @ivar _serial: a pyserial C{serial.Serial} instance used to manage the
        options on the serial port.
    """

    _serialFactory = serial.Serial


    def setBaudRate(self, baudrate):
        if hasattr(self._serial, "setBaudrate"):
            self._serial.setBaudrate(baudrate)
        else:
            self._serial.setBaudRate(baudrate)

    def inWaiting(self):
        return self._serial.inWaiting()

    def flushInput(self):
        self._serial.flushInput()

    def flushOutput(self):
        self._serial.flushOutput()

    def sendBreak(self):
        self._serial.sendBreak()

    def getDSR(self):
        return self._serial.getDSR()

    def getCD(self):
        return self._serial.getCD()

    def getRI(self):
        return self._serial.getRI()

    def getCTS(self):
        return self._serial.getCTS()

    def setDTR(self, on = 1):
        self._serial.setDTR(on)

    def setRTS(self, on = 1):
        self._serial.setRTS(on)



# Expert appropriate implementation of SerialPort.
if platform.isWindows():
    from twisted.internet._win32serialport import SerialPort
else:
    from twisted.internet._posixserialport import SerialPort
