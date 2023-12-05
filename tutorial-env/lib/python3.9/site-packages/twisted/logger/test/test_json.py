# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.logger._json}.
"""

from io import BytesIO, StringIO
from typing import IO, Any, List, Optional, Sequence, cast

from zope.interface import implementer
from zope.interface.exceptions import BrokenMethodImplementation
from zope.interface.verify import verifyObject

from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase
from .._flatten import extractField
from .._format import formatEvent
from .._global import globalLogPublisher
from .._interfaces import ILogObserver, LogEvent
from .._json import (
    eventAsJSON,
    eventFromJSON,
    eventsFromJSONLogFile,
    jsonFileLogObserver,
    log as jsonLog,
)
from .._levels import LogLevel
from .._logger import Logger
from .._observer import LogPublisher


def savedJSONInvariants(testCase: TestCase, savedJSON: str) -> str:
    """
    Assert a few things about the result of L{eventAsJSON}, then return it.

    @param testCase: The L{TestCase} with which to perform the assertions.
    @param savedJSON: The result of L{eventAsJSON}.

    @return: C{savedJSON}

    @raise AssertionError: If any of the preconditions fail.
    """
    testCase.assertIsInstance(savedJSON, str)
    testCase.assertEqual(savedJSON.count("\n"), 0)
    return savedJSON


class SaveLoadTests(TestCase):
    """
    Tests for loading and saving log events.
    """

    def savedEventJSON(self, event: LogEvent) -> str:
        """
        Serialize some an events, assert some things about it, and return the
        JSON.

        @param event: An event.

        @return: JSON.
        """
        return savedJSONInvariants(self, eventAsJSON(event))

    def test_simpleSaveLoad(self) -> None:
        """
        Saving and loading an empty dictionary results in an empty dictionary.
        """
        self.assertEqual(eventFromJSON(self.savedEventJSON({})), {})

    def test_saveLoad(self) -> None:
        """
        Saving and loading a dictionary with some simple values in it results
        in those same simple values in the output; according to JSON's rules,
        though, all dictionary keys must be L{str} and any non-L{str}
        keys will be converted.
        """
        self.assertEqual(
            eventFromJSON(self.savedEventJSON({1: 2, "3": "4"})),  # type: ignore[dict-item]
            {"1": 2, "3": "4"},
        )

    def test_saveUnPersistable(self) -> None:
        """
        Saving and loading an object which cannot be represented in JSON will
        result in a placeholder.
        """
        self.assertEqual(
            eventFromJSON(self.savedEventJSON({"1": 2, "3": object()})),
            {"1": 2, "3": {"unpersistable": True}},
        )

    def test_saveNonASCII(self) -> None:
        """
        Non-ASCII keys and values can be saved and loaded.
        """
        self.assertEqual(
            eventFromJSON(self.savedEventJSON({"\u1234": "\u4321", "3": object()})),
            {"\u1234": "\u4321", "3": {"unpersistable": True}},
        )

    def test_saveBytes(self) -> None:
        """
        Any L{bytes} objects will be saved as if they are latin-1 so they can
        be faithfully re-loaded.
        """
        inputEvent = {"hello": bytes(range(255))}
        # On Python 3, bytes keys will be skipped by the JSON encoder. Not
        # much we can do about that.  Let's make sure that we don't get an
        # error, though.
        inputEvent.update({b"skipped": "okay"})  # type: ignore[dict-item]
        self.assertEqual(
            eventFromJSON(self.savedEventJSON(inputEvent)),
            {"hello": bytes(range(255)).decode("charmap")},
        )

    def test_saveUnPersistableThenFormat(self) -> None:
        """
        Saving and loading an object which cannot be represented in JSON, but
        has a string representation which I{can} be saved as JSON, will result
        in the same string formatting; any extractable fields will retain their
        data types.
        """

        class Reprable:
            def __init__(self, value: object) -> None:
                self.value = value

            def __repr__(self) -> str:
                return "reprable"

        inputEvent = {"log_format": "{object} {object.value}", "object": Reprable(7)}
        outputEvent = eventFromJSON(self.savedEventJSON(inputEvent))
        self.assertEqual(formatEvent(outputEvent), "reprable 7")

    def test_extractingFieldsPostLoad(self) -> None:
        """
        L{extractField} can extract fields from an object that's been saved and
        loaded from JSON.
        """

        class Obj:
            def __init__(self) -> None:
                self.value = 345

        inputEvent = dict(log_format="{object.value}", object=Obj())
        loadedEvent = eventFromJSON(self.savedEventJSON(inputEvent))
        self.assertEqual(extractField("object.value", loadedEvent), 345)

        # The behavior of extractField is consistent between pre-persistence
        # and post-persistence events, although looking up the key directly
        # won't be:
        self.assertRaises(KeyError, extractField, "object", loadedEvent)
        self.assertRaises(KeyError, extractField, "object", inputEvent)

    def test_failureStructurePreserved(self) -> None:
        """
        Round-tripping a failure through L{eventAsJSON} preserves its class and
        structure.
        """
        events: List[LogEvent] = []
        log = Logger(observer=cast(ILogObserver, events.append))
        try:
            1 / 0
        except ZeroDivisionError:
            f = Failure()
            log.failure("a message about failure", f)
        self.assertEqual(len(events), 1)
        loaded = eventFromJSON(self.savedEventJSON(events[0]))["log_failure"]
        self.assertIsInstance(loaded, Failure)
        self.assertTrue(loaded.check(ZeroDivisionError))
        self.assertIsInstance(loaded.getTraceback(), str)

    def test_saveLoadLevel(self) -> None:
        """
        It's important that the C{log_level} key remain a
        L{constantly.NamedConstant} object.
        """
        inputEvent = dict(log_level=LogLevel.warn)
        loadedEvent = eventFromJSON(self.savedEventJSON(inputEvent))
        self.assertIs(loadedEvent["log_level"], LogLevel.warn)

    def test_saveLoadUnknownLevel(self) -> None:
        """
        If a saved bit of JSON (let's say, from a future version of Twisted)
        were to persist a different log_level, it will resolve as None.
        """
        loadedEvent = eventFromJSON(
            '{"log_level": {"name": "other", '
            '"__class_uuid__": "02E59486-F24D-46AD-8224-3ACDF2A5732A"}}'
        )
        self.assertEqual(loadedEvent, dict(log_level=None))


class FileLogObserverTests(TestCase):
    """
    Tests for L{jsonFileLogObserver}.
    """

    def test_interface(self) -> None:
        """
        A L{FileLogObserver} returned by L{jsonFileLogObserver} is an
        L{ILogObserver}.
        """
        with StringIO() as fileHandle:
            observer = jsonFileLogObserver(fileHandle)
            try:
                verifyObject(ILogObserver, observer)
            except BrokenMethodImplementation as e:
                self.fail(e)

    def assertObserverWritesJSON(self, recordSeparator: str = "\x1e") -> None:
        """
        Asserts that an observer created by L{jsonFileLogObserver} with the
        given arguments writes events serialized as JSON text, using the given
        record separator.

        @param recordSeparator: C{recordSeparator} argument to
            L{jsonFileLogObserver}
        """
        with StringIO() as fileHandle:
            observer = jsonFileLogObserver(fileHandle, recordSeparator)
            event = dict(x=1)
            observer(event)
            self.assertEqual(fileHandle.getvalue(), f'{recordSeparator}{{"x": 1}}\n')

    def test_observeWritesDefaultRecordSeparator(self) -> None:
        """
        A L{FileLogObserver} created by L{jsonFileLogObserver} writes events
        serialzed as JSON text to a file when it observes events.
        By default, the record separator is C{"\\x1e"}.
        """
        self.assertObserverWritesJSON()

    def test_observeWritesEmptyRecordSeparator(self) -> None:
        """
        A L{FileLogObserver} created by L{jsonFileLogObserver} writes events
        serialzed as JSON text to a file when it observes events.
        This test sets the record separator to C{""}.
        """
        self.assertObserverWritesJSON(recordSeparator="")

    def test_failureFormatting(self) -> None:
        """
        A L{FileLogObserver} created by L{jsonFileLogObserver} writes failures
        serialized as JSON text to a file when it observes events.
        """
        io = StringIO()
        publisher = LogPublisher()
        logged: List[LogEvent] = []
        publisher.addObserver(cast(ILogObserver, logged.append))
        publisher.addObserver(jsonFileLogObserver(io))
        logger = Logger(observer=publisher)
        try:
            1 / 0
        except BaseException:
            logger.failure("failed as expected")
        reader = StringIO(io.getvalue())
        deserialized = list(eventsFromJSONLogFile(reader))

        def checkEvents(logEvents: Sequence[LogEvent]) -> None:
            self.assertEqual(len(logEvents), 1)
            [failureEvent] = logEvents
            self.assertIn("log_failure", failureEvent)
            failureObject = failureEvent["log_failure"]
            self.assertIsInstance(failureObject, Failure)
            tracebackObject = failureObject.getTracebackObject()
            self.assertEqual(
                tracebackObject.tb_frame.f_code.co_filename.rstrip("co"),
                __file__.rstrip("co"),
            )

        checkEvents(logged)
        checkEvents(deserialized)


class LogFileReaderTests(TestCase):
    """
    Tests for L{eventsFromJSONLogFile}.
    """

    def setUp(self) -> None:
        self.errorEvents: List[LogEvent] = []

        @implementer(ILogObserver)
        def observer(event: LogEvent) -> None:
            if event["log_namespace"] == jsonLog.namespace and "record" in event:
                self.errorEvents.append(event)

        self.logObserver = observer

        globalLogPublisher.addObserver(observer)

    def tearDown(self) -> None:
        globalLogPublisher.removeObserver(self.logObserver)

    def _readEvents(
        self,
        inFile: IO[Any],
        recordSeparator: Optional[str] = None,
        bufferSize: int = 4096,
    ) -> None:
        """
        Test that L{eventsFromJSONLogFile} reads two pre-defined events from a
        file: C{{"x": 1}} and C{{"y": 2}}.

        @param inFile: C{inFile} argument to L{eventsFromJSONLogFile}
        @param recordSeparator: C{recordSeparator} argument to
            L{eventsFromJSONLogFile}
        @param bufferSize: C{bufferSize} argument to L{eventsFromJSONLogFile}
        """
        events = iter(eventsFromJSONLogFile(inFile, recordSeparator, bufferSize))

        self.assertEqual(next(events), {"x": 1})
        self.assertEqual(next(events), {"y": 2})
        self.assertRaises(StopIteration, next, events)  # No more events

    def test_readEventsAutoWithRecordSeparator(self) -> None:
        """
        L{eventsFromJSONLogFile} reads events from a file and automatically
        detects use of C{"\\x1e"} as the record separator.
        """
        with StringIO('\x1e{"x": 1}\n' '\x1e{"y": 2}\n') as fileHandle:
            self._readEvents(fileHandle)
            self.assertEqual(len(self.errorEvents), 0)

    def test_readEventsAutoEmptyRecordSeparator(self) -> None:
        """
        L{eventsFromJSONLogFile} reads events from a file and automatically
        detects use of C{""} as the record separator.
        """
        with StringIO('{"x": 1}\n' '{"y": 2}\n') as fileHandle:
            self._readEvents(fileHandle)
            self.assertEqual(len(self.errorEvents), 0)

    def test_readEventsExplicitRecordSeparator(self) -> None:
        """
        L{eventsFromJSONLogFile} reads events from a file and is told to use
        a specific record separator.
        """
        # Use "\x08" (backspace)... because that seems weird enough.
        with StringIO('\x08{"x": 1}\n' '\x08{"y": 2}\n') as fileHandle:
            self._readEvents(fileHandle, recordSeparator="\x08")
            self.assertEqual(len(self.errorEvents), 0)

    def test_readEventsPartialBuffer(self) -> None:
        """
        L{eventsFromJSONLogFile} handles buffering a partial event.
        """
        with StringIO('\x1e{"x": 1}\n' '\x1e{"y": 2}\n') as fileHandle:
            # Use a buffer size smaller than the event text.
            self._readEvents(fileHandle, bufferSize=1)
            self.assertEqual(len(self.errorEvents), 0)

    def test_readTruncated(self) -> None:
        """
        If the JSON text for a record is truncated, skip it.
        """
        with StringIO('\x1e{"x": 1' '\x1e{"y": 2}\n') as fileHandle:
            events = iter(eventsFromJSONLogFile(fileHandle))

            self.assertEqual(next(events), {"y": 2})
            self.assertRaises(StopIteration, next, events)  # No more events

            # We should have logged the lost record
            self.assertEqual(len(self.errorEvents), 1)
            self.assertEqual(
                self.errorEvents[0]["log_format"],
                "Unable to read truncated JSON record: {record!r}",
            )
            self.assertEqual(self.errorEvents[0]["record"], b'{"x": 1')

    def test_readUnicode(self) -> None:
        """
        If the file being read from vends L{str}, strings decode from JSON
        as-is.
        """
        # The Euro currency sign is "\u20ac"
        with StringIO('\x1e{"currency": "\u20ac"}\n') as fileHandle:
            events = iter(eventsFromJSONLogFile(fileHandle))

            self.assertEqual(next(events), {"currency": "\u20ac"})
            self.assertRaises(StopIteration, next, events)  # No more events
            self.assertEqual(len(self.errorEvents), 0)

    def test_readUTF8Bytes(self) -> None:
        """
        If the file being read from vends L{bytes}, strings decode from JSON as
        UTF-8.
        """
        # The Euro currency sign is b"\xe2\x82\xac" in UTF-8
        with BytesIO(b'\x1e{"currency": "\xe2\x82\xac"}\n') as fileHandle:
            events = iter(eventsFromJSONLogFile(fileHandle))

            # The Euro currency sign is "\u20ac"
            self.assertEqual(next(events), {"currency": "\u20ac"})
            self.assertRaises(StopIteration, next, events)  # No more events
            self.assertEqual(len(self.errorEvents), 0)

    def test_readTruncatedUTF8Bytes(self) -> None:
        """
        If the JSON text for a record is truncated in the middle of a two-byte
        Unicode codepoint, we don't want to see a codec exception and the
        stream is read properly when the additional data arrives.
        """
        # The Euro currency sign is "\u20ac" and encodes in UTF-8 as three
        # bytes: b"\xe2\x82\xac".
        with BytesIO(b'\x1e{"x": "\xe2\x82\xac"}\n') as fileHandle:
            events = iter(eventsFromJSONLogFile(fileHandle, bufferSize=8))

            self.assertEqual(next(events), {"x": "\u20ac"})  # Got text
            self.assertRaises(StopIteration, next, events)  # No more events
            self.assertEqual(len(self.errorEvents), 0)

    def test_readInvalidUTF8Bytes(self) -> None:
        """
        If the JSON text for a record contains invalid UTF-8 text, ignore that
        record.
        """
        # The string b"\xe2\xac" is bogus
        with BytesIO(b'\x1e{"x": "\xe2\xac"}\n' b'\x1e{"y": 2}\n') as fileHandle:
            events = iter(eventsFromJSONLogFile(fileHandle))

            self.assertEqual(next(events), {"y": 2})
            self.assertRaises(StopIteration, next, events)  # No more events

            # We should have logged the lost record
            self.assertEqual(len(self.errorEvents), 1)
            self.assertEqual(
                self.errorEvents[0]["log_format"],
                "Unable to decode UTF-8 for JSON record: {record!r}",
            )
            self.assertEqual(self.errorEvents[0]["record"], b'{"x": "\xe2\xac"}\n')

    def test_readInvalidJSON(self) -> None:
        """
        If the JSON text for a record is invalid, skip it.
        """
        with StringIO('\x1e{"x": }\n' '\x1e{"y": 2}\n') as fileHandle:
            events = iter(eventsFromJSONLogFile(fileHandle))

            self.assertEqual(next(events), {"y": 2})
            self.assertRaises(StopIteration, next, events)  # No more events

            # We should have logged the lost record
            self.assertEqual(len(self.errorEvents), 1)
            self.assertEqual(
                self.errorEvents[0]["log_format"],
                "Unable to read JSON record: {record!r}",
            )
            self.assertEqual(self.errorEvents[0]["record"], b'{"x": }\n')

    def test_readUnseparated(self) -> None:
        """
        Multiple events without a record separator are skipped.
        """
        with StringIO('\x1e{"x": 1}\n' '{"y": 2}\n') as fileHandle:
            events = eventsFromJSONLogFile(fileHandle)

            self.assertRaises(StopIteration, next, events)  # No more events

            # We should have logged the lost record
            self.assertEqual(len(self.errorEvents), 1)
            self.assertEqual(
                self.errorEvents[0]["log_format"],
                "Unable to read JSON record: {record!r}",
            )
            self.assertEqual(self.errorEvents[0]["record"], b'{"x": 1}\n{"y": 2}\n')

    def test_roundTrip(self) -> None:
        """
        Data written by a L{FileLogObserver} returned by L{jsonFileLogObserver}
        and read by L{eventsFromJSONLogFile} is reconstructed properly.
        """
        event = dict(x=1)

        with StringIO() as fileHandle:
            observer = jsonFileLogObserver(fileHandle)
            observer(event)

            fileHandle.seek(0)
            events = eventsFromJSONLogFile(fileHandle)

            self.assertEqual(tuple(events), (event,))
            self.assertEqual(len(self.errorEvents), 0)
