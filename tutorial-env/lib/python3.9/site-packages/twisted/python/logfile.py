# -*- test-case-name: twisted.test.test_logfile -*-

# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
A rotating, browsable log file.
"""


# System Imports
import glob
import os
import stat
import time
from typing import BinaryIO, Optional, cast

from twisted.python import threadable


class BaseLogFile:
    """
    The base class for a log file that can be rotated.
    """

    synchronized = ["write", "rotate"]

    def __init__(
        self, name: str, directory: str, defaultMode: Optional[int] = None
    ) -> None:
        """
        Create a log file.

        @param name: name of the file
        @param directory: directory holding the file
        @param defaultMode: permissions used to create the file. Default to
        current permissions of the file if the file exists.
        """
        self.directory = directory
        self.name = name
        self.path = os.path.join(directory, name)
        if defaultMode is None and os.path.exists(self.path):
            self.defaultMode: Optional[int] = stat.S_IMODE(
                os.stat(self.path)[stat.ST_MODE]
            )
        else:
            self.defaultMode = defaultMode
        self._openFile()

    @classmethod
    def fromFullPath(cls, filename, *args, **kwargs):
        """
        Construct a log file from a full file path.
        """
        logPath = os.path.abspath(filename)
        return cls(os.path.basename(logPath), os.path.dirname(logPath), *args, **kwargs)

    def shouldRotate(self):
        """
        Override with a method to that returns true if the log
        should be rotated.
        """
        raise NotImplementedError

    def _openFile(self):
        """
        Open the log file.

        The log file is always opened in binary mode.
        """
        self.closed = False
        if os.path.exists(self.path):
            self._file = cast(BinaryIO, open(self.path, "rb+", 0))
            self._file.seek(0, 2)
        else:
            if self.defaultMode is not None:
                # Set the lowest permissions
                oldUmask = os.umask(0o777)
                try:
                    self._file = cast(BinaryIO, open(self.path, "wb+", 0))
                finally:
                    os.umask(oldUmask)
            else:
                self._file = cast(BinaryIO, open(self.path, "wb+", 0))
        if self.defaultMode is not None:
            try:
                os.chmod(self.path, self.defaultMode)
            except OSError:
                # Probably /dev/null or something?
                pass

    def write(self, data):
        """
        Write some data to the file.

        @param data: The data to write.  Text will be encoded as UTF-8.
        @type data: L{bytes} or L{unicode}
        """
        if self.shouldRotate():
            self.flush()
            self.rotate()
        if isinstance(data, str):
            data = data.encode("utf8")
        self._file.write(data)

    def flush(self):
        """
        Flush the file.
        """
        self._file.flush()

    def close(self):
        """
        Close the file.

        The file cannot be used once it has been closed.
        """
        self.closed = True
        self._file.close()
        del self._file

    def reopen(self):
        """
        Reopen the log file. This is mainly useful if you use an external log
        rotation tool, which moves under your feet.

        Note that on Windows you probably need a specific API to rename the
        file, as it's not supported to simply use os.rename, for example.
        """
        self.close()
        self._openFile()

    def getCurrentLog(self):
        """
        Return a LogReader for the current log file.
        """
        return LogReader(self.path)


class LogFile(BaseLogFile):
    """
    A log file that can be rotated.

    A rotateLength of None disables automatic log rotation.
    """

    def __init__(
        self,
        name,
        directory,
        rotateLength=1000000,
        defaultMode=None,
        maxRotatedFiles=None,
    ):
        """
        Create a log file rotating on length.

        @param name: file name.
        @type name: C{str}
        @param directory: path of the log file.
        @type directory: C{str}
        @param rotateLength: size of the log file where it rotates. Default to
            1M.
        @type rotateLength: C{int}
        @param defaultMode: mode used to create the file.
        @type defaultMode: C{int}
        @param maxRotatedFiles: if not None, max number of log files the class
            creates. Warning: it removes all log files above this number.
        @type maxRotatedFiles: C{int}
        """
        BaseLogFile.__init__(self, name, directory, defaultMode)
        self.rotateLength = rotateLength
        self.maxRotatedFiles = maxRotatedFiles

    def _openFile(self):
        BaseLogFile._openFile(self)
        self.size = self._file.tell()

    def shouldRotate(self):
        """
        Rotate when the log file size is larger than rotateLength.
        """
        return self.rotateLength and self.size >= self.rotateLength

    def getLog(self, identifier):
        """
        Given an integer, return a LogReader for an old log file.
        """
        filename = "%s.%d" % (self.path, identifier)
        if not os.path.exists(filename):
            raise ValueError("no such logfile exists")
        return LogReader(filename)

    def write(self, data):
        """
        Write some data to the file.
        """
        BaseLogFile.write(self, data)
        self.size += len(data)

    def rotate(self):
        """
        Rotate the file and create a new one.

        If it's not possible to open new logfile, this will fail silently,
        and continue logging to old logfile.
        """
        if not (os.access(self.directory, os.W_OK) and os.access(self.path, os.W_OK)):
            return
        logs = self.listLogs()
        logs.reverse()
        for i in logs:
            if self.maxRotatedFiles is not None and i >= self.maxRotatedFiles:
                os.remove("%s.%d" % (self.path, i))
            else:
                os.rename("%s.%d" % (self.path, i), "%s.%d" % (self.path, i + 1))
        self._file.close()
        os.rename(self.path, "%s.1" % self.path)
        self._openFile()

    def listLogs(self):
        """
        Return sorted list of integers - the old logs' identifiers.
        """
        result = []
        for name in glob.glob("%s.*" % self.path):
            try:
                counter = int(name.split(".")[-1])
                if counter:
                    result.append(counter)
            except ValueError:
                pass
        result.sort()
        return result

    def __getstate__(self):
        state = BaseLogFile.__getstate__(self)
        del state["size"]
        return state


threadable.synchronize(LogFile)


class DailyLogFile(BaseLogFile):
    """A log file that is rotated daily (at or after midnight localtime)"""

    def _openFile(self):
        BaseLogFile._openFile(self)
        self.lastDate = self.toDate(os.stat(self.path)[8])

    def shouldRotate(self):
        """Rotate when the date has changed since last write"""
        return self.toDate() > self.lastDate

    def toDate(self, *args):
        """Convert a unixtime to (year, month, day) localtime tuple,
        or return the current (year, month, day) localtime tuple.

        This function primarily exists so you may overload it with
        gmtime, or some cruft to make unit testing possible.
        """
        # primarily so this can be unit tested easily
        return time.localtime(*args)[:3]

    def suffix(self, tupledate):
        """Return the suffix given a (year, month, day) tuple or unixtime"""
        try:
            return "_".join(map(str, tupledate))
        except BaseException:
            # try taking a float unixtime
            return "_".join(map(str, self.toDate(tupledate)))

    def getLog(self, identifier):
        """Given a unix time, return a LogReader for an old log file."""
        if self.toDate(identifier) == self.lastDate:
            return self.getCurrentLog()
        filename = f"{self.path}.{self.suffix(identifier)}"
        if not os.path.exists(filename):
            raise ValueError("no such logfile exists")
        return LogReader(filename)

    def write(self, data):
        """Write some data to the log file"""
        BaseLogFile.write(self, data)
        # Guard against a corner case where time.time()
        # could potentially run backwards to yesterday.
        # Primarily due to network time.
        self.lastDate = max(self.lastDate, self.toDate())

    def rotate(self):
        """Rotate the file and create a new one.

        If it's not possible to open new logfile, this will fail silently,
        and continue logging to old logfile.
        """
        if not (os.access(self.directory, os.W_OK) and os.access(self.path, os.W_OK)):
            return
        newpath = f"{self.path}.{self.suffix(self.lastDate)}"
        if os.path.exists(newpath):
            return
        self._file.close()
        os.rename(self.path, newpath)
        self._openFile()

    def __getstate__(self):
        state = BaseLogFile.__getstate__(self)
        del state["lastDate"]
        return state


threadable.synchronize(DailyLogFile)


class LogReader:
    """Read from a log file."""

    def __init__(self, name):
        """
        Open the log file for reading.

        The comments about binary-mode for L{BaseLogFile._openFile} also apply
        here.
        """
        self._file = open(name)  # Optional[BinaryIO]

    def readLines(self, lines=10):
        """Read a list of lines from the log file.

        This doesn't returns all of the files lines - call it multiple times.
        """
        result = []
        for i in range(lines):
            line = self._file.readline()
            if not line:
                break
            result.append(line)
        return result

    def close(self):
        self._file.close()
