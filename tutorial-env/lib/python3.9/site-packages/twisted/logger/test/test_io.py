# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._io}.
"""

import sys
from typing import List, Optional

from zope.interface import implementer

from constantly import NamedConstant  # type: ignore[import]

from twisted.trial import unittest
from .._interfaces import ILogObserver, LogEvent
from .._io import LoggingFile
from .._levels import LogLevel
from .._logger import Logger
from .._observer import LogPublisher


@implementer(ILogObserver)
class TestLoggingFile(LoggingFile):
    """
    L{LoggingFile} that is also an observer which captures events and messages.
    """

    def __init__(
        self,
        logger: Logger,
        level: NamedConstant = LogLevel.info,
        encoding: Optional[str] = None,
    ) -> None:
        super().__init__(logger=logger, level=level, encoding=encoding)
        self.events: List[LogEvent] = []
        self.messages: List[str] = []

    def __call__(self, event: LogEvent) -> None:
        self.events.append(event)
        if "log_io" in event:
            self.messages.append(event["log_io"])


class LoggingFileTests(unittest.TestCase):
    """
    Tests for L{LoggingFile}.
    """

    def setUp(self) -> None:
        """
        Create a logger for test L{LoggingFile} instances to use.
        """
        self.publisher = LogPublisher()
        self.logger = Logger(observer=self.publisher)

    def test_softspace(self) -> None:
        """
        L{LoggingFile.softspace} is 0.
        """
        self.assertEqual(LoggingFile(self.logger).softspace, 0)

        warningsShown = self.flushWarnings([self.test_softspace])
        self.assertEqual(len(warningsShown), 1)
        self.assertEqual(warningsShown[0]["category"], DeprecationWarning)
        deprecatedClass = "twisted.logger._io.LoggingFile.softspace"
        self.assertEqual(
            warningsShown[0]["message"],
            "%s was deprecated in Twisted 21.2.0" % (deprecatedClass),
        )

    def test_readOnlyAttributes(self) -> None:
        """
        Some L{LoggingFile} attributes are read-only.
        """
        f = LoggingFile(self.logger)

        self.assertRaises(AttributeError, setattr, f, "closed", True)
        self.assertRaises(AttributeError, setattr, f, "encoding", "utf-8")
        self.assertRaises(AttributeError, setattr, f, "mode", "r")
        self.assertRaises(AttributeError, setattr, f, "newlines", ["\n"])
        self.assertRaises(AttributeError, setattr, f, "name", "foo")

    def test_unsupportedMethods(self) -> None:
        """
        Some L{LoggingFile} methods are unsupported.
        """
        f = LoggingFile(self.logger)

        self.assertRaises(IOError, f.read)
        self.assertRaises(IOError, f.next)
        self.assertRaises(IOError, f.readline)
        self.assertRaises(IOError, f.readlines)
        self.assertRaises(IOError, f.xreadlines)
        self.assertRaises(IOError, f.seek)
        self.assertRaises(IOError, f.tell)
        self.assertRaises(IOError, f.truncate)

    def test_level(self) -> None:
        """
        Default level is L{LogLevel.info} if not set.
        """
        f = LoggingFile(self.logger)
        self.assertEqual(f.level, LogLevel.info)

        f = LoggingFile(self.logger, level=LogLevel.error)
        self.assertEqual(f.level, LogLevel.error)

    def test_encoding(self) -> None:
        """
        Default encoding is C{sys.getdefaultencoding()} if not set.
        """
        f = LoggingFile(self.logger)
        self.assertEqual(f.encoding, sys.getdefaultencoding())

        f = LoggingFile(self.logger, encoding="utf-8")
        self.assertEqual(f.encoding, "utf-8")

    def test_mode(self) -> None:
        """
        Reported mode is C{"w"}.
        """
        f = LoggingFile(self.logger)
        self.assertEqual(f.mode, "w")

    def test_newlines(self) -> None:
        """
        The C{newlines} attribute is L{None}.
        """
        f = LoggingFile(self.logger)
        self.assertIsNone(f.newlines)

    def test_name(self) -> None:
        """
        The C{name} attribute is fixed.
        """
        f = LoggingFile(self.logger)
        self.assertEqual(f.name, "<LoggingFile twisted.logger.test.test_io#info>")

    def test_close(self) -> None:
        """
        L{LoggingFile.close} closes the file.
        """
        f = LoggingFile(self.logger)
        f.close()

        self.assertTrue(f.closed)
        self.assertRaises(ValueError, f.write, "Hello")

    def test_flush(self) -> None:
        """
        L{LoggingFile.flush} does nothing.
        """
        f = LoggingFile(self.logger)
        f.flush()

    def test_fileno(self) -> None:
        """
        L{LoggingFile.fileno} returns C{-1}.
        """
        f = LoggingFile(self.logger)
        self.assertEqual(f.fileno(), -1)

    def test_isatty(self) -> None:
        """
        L{LoggingFile.isatty} returns C{False}.
        """
        f = LoggingFile(self.logger)
        self.assertFalse(f.isatty())

    def test_writeBuffering(self) -> None:
        """
        Writing buffers correctly.
        """
        f = self.observedFile()
        f.write("Hello")
        self.assertEqual(f.messages, [])
        f.write(", world!\n")
        self.assertEqual(f.messages, ["Hello, world!"])
        f.write("It's nice to meet you.\n\nIndeed.")
        self.assertEqual(
            f.messages,
            [
                "Hello, world!",
                "It's nice to meet you.",
                "",
            ],
        )

    def test_writeBytesDecoded(self) -> None:
        """
        Bytes are decoded to text.
        """
        f = self.observedFile(encoding="utf-8")
        f.write(b"Hello, Mr. S\xc3\xa1nchez\n")
        self.assertEqual(f.messages, ["Hello, Mr. S\xe1nchez"])

    def test_writeUnicode(self) -> None:
        """
        Unicode is unmodified.
        """
        f = self.observedFile(encoding="utf-8")
        f.write("Hello, Mr. S\xe1nchez\n")
        self.assertEqual(f.messages, ["Hello, Mr. S\xe1nchez"])

    def test_writeLevel(self) -> None:
        """
        Log level is emitted properly.
        """
        f = self.observedFile()
        f.write("Hello\n")
        self.assertEqual(len(f.events), 1)
        self.assertEqual(f.events[0]["log_level"], LogLevel.info)

        f = self.observedFile(level=LogLevel.error)
        f.write("Hello\n")
        self.assertEqual(len(f.events), 1)
        self.assertEqual(f.events[0]["log_level"], LogLevel.error)

    def test_writeFormat(self) -> None:
        """
        Log format is C{"{message}"}.
        """
        f = self.observedFile()
        f.write("Hello\n")
        self.assertEqual(len(f.events), 1)
        self.assertEqual(f.events[0]["log_format"], "{log_io}")

    def test_writelinesBuffering(self) -> None:
        """
        C{writelines} does not add newlines.
        """
        # Note this is different behavior than t.p.log.StdioOnnaStick.
        f = self.observedFile()
        f.writelines(("Hello", ", ", ""))
        self.assertEqual(f.messages, [])
        f.writelines(("world!\n",))
        self.assertEqual(f.messages, ["Hello, world!"])
        f.writelines(("It's nice to meet you.\n\n", "Indeed."))
        self.assertEqual(
            f.messages,
            [
                "Hello, world!",
                "It's nice to meet you.",
                "",
            ],
        )

    def test_print(self) -> None:
        """
        L{LoggingFile} can replace L{sys.stdout}.
        """
        f = self.observedFile()
        self.patch(sys, "stdout", f)

        print("Hello,", end=" ")
        print("world.")

        self.assertEqual(f.messages, ["Hello, world."])

    def observedFile(
        self,
        level: NamedConstant = LogLevel.info,
        encoding: Optional[str] = None,
    ) -> TestLoggingFile:
        """
        Construct a L{LoggingFile} with a built-in observer.

        @param level: C{level} argument to L{LoggingFile}
        @param encoding: C{encoding} argument to L{LoggingFile}

        @return: a L{TestLoggingFile} with an observer that appends received
            events into the file's C{events} attribute (a L{list}) and
            event messages into the file's C{messages} attribute (a L{list}).
        """
        # Logger takes an observer argument, for which we want to use the
        # TestLoggingFile we will create, but that takes the Logger as an
        # argument, so we'll use an array to indirectly reference the
        # TestLoggingFile.
        loggingFiles: List[TestLoggingFile] = []

        @implementer(ILogObserver)
        def observer(event: LogEvent) -> None:
            loggingFiles[0](event)

        log = Logger(observer=observer)
        loggingFiles.append(TestLoggingFile(logger=log, level=level, encoding=encoding))

        return loggingFiles[0]
