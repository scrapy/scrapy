# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


import contextlib
import errno
import os
import stat
import time
from unittest import skipIf

from twisted.python import logfile, runtime
from twisted.trial.unittest import TestCase


class LogFileTests(TestCase):
    """
    Test the rotating log file.
    """

    def setUp(self):
        self.dir = self.mktemp()
        os.makedirs(self.dir)
        self.name = "test.log"
        self.path = os.path.join(self.dir, self.name)

    def tearDown(self):
        """
        Restore back write rights on created paths: if tests modified the
        rights, that will allow the paths to be removed easily afterwards.
        """
        os.chmod(self.dir, 0o777)
        if os.path.exists(self.path):
            os.chmod(self.path, 0o777)

    def test_abstractShouldRotate(self):
        """
        L{BaseLogFile.shouldRotate} is abstract and must be implemented by
        subclass.
        """
        log = logfile.BaseLogFile(self.name, self.dir)
        self.addCleanup(log.close)
        self.assertRaises(NotImplementedError, log.shouldRotate)

    def test_writing(self):
        """
        Log files can be written to, flushed and closed. Closing a log file
        also flushes it.
        """
        with contextlib.closing(logfile.LogFile(self.name, self.dir)) as log:
            log.write("123")
            log.write("456")
            log.flush()
            log.write("7890")

        with open(self.path) as f:
            self.assertEqual(f.read(), "1234567890")

    def test_rotation(self):
        """
        Rotating log files autorotate after a period of time, and can also be
        manually rotated.
        """
        # this logfile should rotate every 10 bytes
        with contextlib.closing(
            logfile.LogFile(self.name, self.dir, rotateLength=10)
        ) as log:

            # test automatic rotation
            log.write("123")
            log.write("4567890")
            log.write("1" * 11)
            self.assertTrue(os.path.exists(f"{self.path}.1"))
            self.assertFalse(os.path.exists(f"{self.path}.2"))
            log.write("")
            self.assertTrue(os.path.exists(f"{self.path}.1"))
            self.assertTrue(os.path.exists(f"{self.path}.2"))
            self.assertFalse(os.path.exists(f"{self.path}.3"))
            log.write("3")
            self.assertFalse(os.path.exists(f"{self.path}.3"))

            # test manual rotation
            log.rotate()
            self.assertTrue(os.path.exists(f"{self.path}.3"))
            self.assertFalse(os.path.exists(f"{self.path}.4"))

        self.assertEqual(log.listLogs(), [1, 2, 3])

    def test_append(self):
        """
        Log files can be written to, closed. Their size is the number of
        bytes written to them. Everything that was written to them can
        be read, even if the writing happened on separate occasions,
        and even if the log file was closed in between.
        """
        with contextlib.closing(logfile.LogFile(self.name, self.dir)) as log:
            log.write("0123456789")

        log = logfile.LogFile(self.name, self.dir)
        self.addCleanup(log.close)
        self.assertEqual(log.size, 10)
        self.assertEqual(log._file.tell(), log.size)
        log.write("abc")
        self.assertEqual(log.size, 13)
        self.assertEqual(log._file.tell(), log.size)
        f = log._file
        f.seek(0, 0)
        self.assertEqual(f.read(), b"0123456789abc")

    def test_logReader(self):
        """
        Various tests for log readers.

        First of all, log readers can get logs by number and read what
        was written to those log files. Getting nonexistent log files
        raises C{ValueError}. Using anything other than an integer
        index raises C{TypeError}. As logs get older, their log
        numbers increase.
        """
        log = logfile.LogFile(self.name, self.dir)
        self.addCleanup(log.close)
        log.write("abc\n")
        log.write("def\n")
        log.rotate()
        log.write("ghi\n")
        log.flush()

        # check reading logs
        self.assertEqual(log.listLogs(), [1])
        with contextlib.closing(log.getCurrentLog()) as reader:
            reader._file.seek(0)
            self.assertEqual(reader.readLines(), ["ghi\n"])
            self.assertEqual(reader.readLines(), [])
        with contextlib.closing(log.getLog(1)) as reader:
            self.assertEqual(reader.readLines(), ["abc\n", "def\n"])
            self.assertEqual(reader.readLines(), [])

        # check getting illegal log readers
        self.assertRaises(ValueError, log.getLog, 2)
        self.assertRaises(TypeError, log.getLog, "1")

        # check that log numbers are higher for older logs
        log.rotate()
        self.assertEqual(log.listLogs(), [1, 2])
        with contextlib.closing(log.getLog(1)) as reader:
            reader._file.seek(0)
            self.assertEqual(reader.readLines(), ["ghi\n"])
            self.assertEqual(reader.readLines(), [])
        with contextlib.closing(log.getLog(2)) as reader:
            self.assertEqual(reader.readLines(), ["abc\n", "def\n"])
            self.assertEqual(reader.readLines(), [])

    def test_LogReaderReadsZeroLine(self):
        """
        L{LogReader.readLines} supports reading no line.
        """
        # We don't need any content, just a file path that can be opened.
        with open(self.path, "w"):
            pass

        reader = logfile.LogReader(self.path)
        self.addCleanup(reader.close)
        self.assertEqual([], reader.readLines(0))

    def test_modePreservation(self):
        """
        Check rotated files have same permissions as original.
        """
        open(self.path, "w").close()
        os.chmod(self.path, 0o707)
        mode = os.stat(self.path)[stat.ST_MODE]
        log = logfile.LogFile(self.name, self.dir)
        self.addCleanup(log.close)
        log.write("abc")
        log.rotate()
        self.assertEqual(mode, os.stat(self.path)[stat.ST_MODE])

    def test_noPermission(self):
        """
        Check it keeps working when permission on dir changes.
        """
        log = logfile.LogFile(self.name, self.dir)
        self.addCleanup(log.close)
        log.write("abc")

        # change permissions so rotation would fail
        os.chmod(self.dir, 0o555)

        # if this succeeds, chmod doesn't restrict us, so we can't
        # do the test
        try:
            f = open(os.path.join(self.dir, "xxx"), "w")
        except OSError:
            pass
        else:
            f.close()
            return

        log.rotate()  # this should not fail

        log.write("def")
        log.flush()

        f = log._file
        self.assertEqual(f.tell(), 6)
        f.seek(0, 0)
        self.assertEqual(f.read(), b"abcdef")

    def test_maxNumberOfLog(self):
        """
        Test it respect the limit on the number of files when maxRotatedFiles
        is not None.
        """
        log = logfile.LogFile(self.name, self.dir, rotateLength=10, maxRotatedFiles=3)
        self.addCleanup(log.close)
        log.write("1" * 11)
        log.write("2" * 11)
        self.assertTrue(os.path.exists(f"{self.path}.1"))

        log.write("3" * 11)
        self.assertTrue(os.path.exists(f"{self.path}.2"))

        log.write("4" * 11)
        self.assertTrue(os.path.exists(f"{self.path}.3"))
        with open(f"{self.path}.3") as fp:
            self.assertEqual(fp.read(), "1" * 11)

        log.write("5" * 11)
        with open(f"{self.path}.3") as fp:
            self.assertEqual(fp.read(), "2" * 11)
        self.assertFalse(os.path.exists(f"{self.path}.4"))

    def test_fromFullPath(self):
        """
        Test the fromFullPath method.
        """
        log1 = logfile.LogFile(self.name, self.dir, 10, defaultMode=0o777)
        self.addCleanup(log1.close)
        log2 = logfile.LogFile.fromFullPath(self.path, 10, defaultMode=0o777)
        self.addCleanup(log2.close)
        self.assertEqual(log1.name, log2.name)
        self.assertEqual(os.path.abspath(log1.path), log2.path)
        self.assertEqual(log1.rotateLength, log2.rotateLength)
        self.assertEqual(log1.defaultMode, log2.defaultMode)

    def test_defaultPermissions(self):
        """
        Test the default permission of the log file: if the file exist, it
        should keep the permission.
        """
        with open(self.path, "wb"):
            os.chmod(self.path, 0o707)
            currentMode = stat.S_IMODE(os.stat(self.path)[stat.ST_MODE])
        log1 = logfile.LogFile(self.name, self.dir)
        self.assertEqual(stat.S_IMODE(os.stat(self.path)[stat.ST_MODE]), currentMode)
        self.addCleanup(log1.close)

    def test_specifiedPermissions(self):
        """
        Test specifying the permissions used on the log file.
        """
        log1 = logfile.LogFile(self.name, self.dir, defaultMode=0o066)
        self.addCleanup(log1.close)
        mode = stat.S_IMODE(os.stat(self.path)[stat.ST_MODE])
        if runtime.platform.isWindows():
            # The only thing we can get here is global read-only
            self.assertEqual(mode, 0o444)
        else:
            self.assertEqual(mode, 0o066)

    @skipIf(runtime.platform.isWindows(), "Can't test reopen on Windows")
    def test_reopen(self):
        """
        L{logfile.LogFile.reopen} allows to rename the currently used file and
        make L{logfile.LogFile} create a new file.
        """
        with contextlib.closing(logfile.LogFile(self.name, self.dir)) as log1:
            log1.write("hello1")
            savePath = os.path.join(self.dir, "save.log")
            os.rename(self.path, savePath)
            log1.reopen()
            log1.write("hello2")

        with open(self.path) as f:
            self.assertEqual(f.read(), "hello2")
        with open(savePath) as f:
            self.assertEqual(f.read(), "hello1")

    def test_nonExistentDir(self):
        """
        Specifying an invalid directory to L{LogFile} raises C{IOError}.
        """
        e = self.assertRaises(
            IOError, logfile.LogFile, self.name, "this_dir_does_not_exist"
        )
        self.assertEqual(e.errno, errno.ENOENT)

    def test_cantChangeFileMode(self):
        """
        Opening a L{LogFile} which can be read and write but whose mode can't
        be changed doesn't trigger an error.
        """
        if runtime.platform.isWindows():
            name, directory = "NUL", ""
            expectedPath = "NUL"
        else:
            name, directory = "null", "/dev"
            expectedPath = "/dev/null"

        log = logfile.LogFile(name, directory, defaultMode=0o555)
        self.addCleanup(log.close)

        self.assertEqual(log.path, expectedPath)
        self.assertEqual(log.defaultMode, 0o555)

    def test_listLogsWithBadlyNamedFiles(self):
        """
        L{LogFile.listLogs} doesn't choke if it encounters a file with an
        unexpected name.
        """
        log = logfile.LogFile(self.name, self.dir)
        self.addCleanup(log.close)

        with open(f"{log.path}.1", "w") as fp:
            fp.write("123")
        with open(f"{log.path}.bad-file", "w") as fp:
            fp.write("123")

        self.assertEqual([1], log.listLogs())

    def test_listLogsIgnoresZeroSuffixedFiles(self):
        """
        L{LogFile.listLogs} ignores log files which rotated suffix is 0.
        """
        log = logfile.LogFile(self.name, self.dir)
        self.addCleanup(log.close)

        for i in range(0, 3):
            with open(f"{log.path}.{i}", "w") as fp:
                fp.write("123")

        self.assertEqual([1, 2], log.listLogs())


class RiggedDailyLogFile(logfile.DailyLogFile):
    _clock = 0.0

    def _openFile(self):
        logfile.DailyLogFile._openFile(self)
        # rig the date to match _clock, not mtime
        self.lastDate = self.toDate()

    def toDate(self, *args):
        if args:
            return time.gmtime(*args)[:3]
        return time.gmtime(self._clock)[:3]


class DailyLogFileTests(TestCase):
    """
    Test rotating log file.
    """

    def setUp(self):
        self.dir = self.mktemp()
        os.makedirs(self.dir)
        self.name = "testdaily.log"
        self.path = os.path.join(self.dir, self.name)

    def test_writing(self):
        """
        A daily log file can be written to like an ordinary log file.
        """
        with contextlib.closing(RiggedDailyLogFile(self.name, self.dir)) as log:
            log.write("123")
            log.write("456")
            log.flush()
            log.write("7890")

        with open(self.path) as f:
            self.assertEqual(f.read(), "1234567890")

    def test_rotation(self):
        """
        Daily log files rotate daily.
        """
        log = RiggedDailyLogFile(self.name, self.dir)
        self.addCleanup(log.close)
        days = [(self.path + "." + log.suffix(day * 86400)) for day in range(3)]

        # test automatic rotation
        log._clock = 0.0  # 1970/01/01 00:00.00
        log.write("123")
        log._clock = 43200  # 1970/01/01 12:00.00
        log.write("4567890")
        log._clock = 86400  # 1970/01/02 00:00.00
        log.write("1" * 11)
        self.assertTrue(os.path.exists(days[0]))
        self.assertFalse(os.path.exists(days[1]))
        log._clock = 172800  # 1970/01/03 00:00.00
        log.write("")
        self.assertTrue(os.path.exists(days[0]))
        self.assertTrue(os.path.exists(days[1]))
        self.assertFalse(os.path.exists(days[2]))
        log._clock = 259199  # 1970/01/03 23:59.59
        log.write("3")
        self.assertFalse(os.path.exists(days[2]))

    def test_getLog(self):
        """
        Test retrieving log files with L{DailyLogFile.getLog}.
        """
        data = ["1\n", "2\n", "3\n"]
        log = RiggedDailyLogFile(self.name, self.dir)
        self.addCleanup(log.close)
        for d in data:
            log.write(d)
        log.flush()

        # This returns the current log file.
        r = log.getLog(0.0)
        self.addCleanup(r.close)

        self.assertEqual(data, r.readLines())

        # We can't get this log, it doesn't exist yet.
        self.assertRaises(ValueError, log.getLog, 86400)

        log._clock = 86401  # New day
        r.close()
        log.rotate()
        r = log.getLog(0)  # We get the previous log
        self.addCleanup(r.close)
        self.assertEqual(data, r.readLines())

    def test_rotateAlreadyExists(self):
        """
        L{DailyLogFile.rotate} doesn't do anything if they new log file already
        exists on the disk.
        """
        log = RiggedDailyLogFile(self.name, self.dir)
        self.addCleanup(log.close)

        # Build a new file with the same name as the file which would be created
        # if the log file is to be rotated.
        newFilePath = f"{log.path}.{log.suffix(log.lastDate)}"
        with open(newFilePath, "w") as fp:
            fp.write("123")
        previousFile = log._file
        log.rotate()
        self.assertEqual(previousFile, log._file)

    @skipIf(
        runtime.platform.isWindows(),
        "Making read-only directories on Windows is too complex for this "
        "test to reasonably do.",
    )
    def test_rotatePermissionDirectoryNotOk(self):
        """
        L{DailyLogFile.rotate} doesn't do anything if the directory containing
        the log files can't be written to.
        """
        log = logfile.DailyLogFile(self.name, self.dir)
        self.addCleanup(log.close)

        os.chmod(log.directory, 0o444)
        # Restore permissions so tests can be cleaned up.
        self.addCleanup(os.chmod, log.directory, 0o755)
        previousFile = log._file
        log.rotate()
        self.assertEqual(previousFile, log._file)

    def test_rotatePermissionFileNotOk(self):
        """
        L{DailyLogFile.rotate} doesn't do anything if the log file can't be
        written to.
        """
        log = logfile.DailyLogFile(self.name, self.dir)
        self.addCleanup(log.close)

        os.chmod(log.path, 0o444)
        previousFile = log._file
        log.rotate()
        self.assertEqual(previousFile, log._file)

    def test_toDate(self):
        """
        Test that L{DailyLogFile.toDate} converts its timestamp argument to a
        time tuple (year, month, day).
        """
        log = logfile.DailyLogFile(self.name, self.dir)
        self.addCleanup(log.close)

        timestamp = time.mktime((2000, 1, 1, 0, 0, 0, 0, 0, 0))
        self.assertEqual((2000, 1, 1), log.toDate(timestamp))

    def test_toDateDefaultToday(self):
        """
        Test that L{DailyLogFile.toDate} returns today's date by default.

        By mocking L{time.localtime}, we ensure that L{DailyLogFile.toDate}
        returns the first 3 values of L{time.localtime} which is the current
        date.

        Note that we don't compare the *real* result of L{DailyLogFile.toDate}
        to the *real* current date, as there's a slight possibility that the
        date changes between the 2 function calls.
        """

        def mock_localtime(*args):
            self.assertEqual((), args)
            return list(range(0, 9))

        log = logfile.DailyLogFile(self.name, self.dir)
        self.addCleanup(log.close)

        self.patch(time, "localtime", mock_localtime)
        logDate = log.toDate()
        self.assertEqual([0, 1, 2], logDate)

    def test_toDateUsesArgumentsToMakeADate(self):
        """
        Test that L{DailyLogFile.toDate} uses its arguments to create a new
        date.
        """
        log = logfile.DailyLogFile(self.name, self.dir)
        self.addCleanup(log.close)

        date = (2014, 10, 22)
        seconds = time.mktime(date + (0,) * 6)

        logDate = log.toDate(seconds)
        self.assertEqual(date, logDate)
