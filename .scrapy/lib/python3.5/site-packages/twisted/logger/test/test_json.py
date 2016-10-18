# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.logger._json}.
"""

from io import StringIO, BytesIO

from zope.interface.verify import verifyObject, BrokenMethodImplementation

from twisted.python.compat import unicode

from twisted.trial.unittest import TestCase

from twisted.python.failure import Failure

from .._observer import ILogObserver
from .._format import formatEvent
from .._levels import LogLevel
from .._flatten import extractField
from .._global import globalLogPublisher
from .._json import (
    eventAsJSON, eventFromJSON, jsonFileLogObserver, eventsFromJSONLogFile,
    log as jsonLog
)
from .._logger import Logger


def savedJSONInvariants(testCase, savedJSON):
    """
    Assert a few things about the result of L{eventAsJSON}, then return it.

    @param testCase: The L{TestCase} with which to perform the assertions.
    @type testCase: L{TestCase}

    @param savedJSON: The result of L{eventAsJSON}.
    @type savedJSON: L{unicode} (we hope)

    @return: C{savedJSON}
    @rtype: L{unicode}

    @raise AssertionError: If any of the preconditions fail.
    """
    testCase.assertIsInstance(savedJSON, unicode)
    testCase.assertEqual(savedJSON.count("\n"), 0)
    return savedJSON



class SaveLoadTests(TestCase):
    """
    Tests for loading and saving log events.
    """

    def savedEventJSON(self, event):
        """
        Serialize some an events, assert some things about it, and return the
        JSON.

        @param event: An event.
        @type event: L{dict}

        @return: JSON.
        """
        return savedJSONInvariants(self, eventAsJSON(event))


    def test_simpleSaveLoad(self):
        """
        Saving and loading an empty dictionary results in an empty dictionary.
        """
        self.assertEqual(eventFromJSON(self.savedEventJSON({})), {})


    def test_saveLoad(self):
        """
        Saving and loading a dictionary with some simple values in it results
        in those same simple values in the output; according to JSON's rules,
        though, all dictionary keys must be L{unicode} and any non-L{unicode}
        keys will be converted.
        """
        self.assertEqual(
            eventFromJSON(self.savedEventJSON({1: 2, u"3": u"4"})),
            {u"1": 2, u"3": u"4"}
        )


    def test_saveUnPersistable(self):
        """
        Saving and loading an object which cannot be represented in JSON will
        result in a placeholder.
        """
        self.assertEqual(
            eventFromJSON(self.savedEventJSON({u"1": 2, u"3": object()})),
            {u"1": 2, u"3": {u"unpersistable": True}}
        )


    def test_saveNonASCII(self):
        """
        Non-ASCII keys and values can be saved and loaded.
        """
        self.assertEqual(
            eventFromJSON(self.savedEventJSON(
                {u"\u1234": u"\u4321", u"3": object()}
            )),
            {u"\u1234": u"\u4321", u"3": {u"unpersistable": True}}
        )


    def test_saveBytes(self):
        """
        Any L{bytes} objects will be saved as if they are latin-1 so they can
        be faithfully re-loaded.
        """
        def asbytes(x):
            if bytes is str:
                return b"".join(map(chr, x))
            else:
                return bytes(x)

        inputEvent = {"hello": asbytes(range(255))}
        if bytes is not str:
            # On Python 3, bytes keys will be skipped by the JSON encoder. Not
            # much we can do about that.  Let's make sure that we don't get an
            # error, though.
            inputEvent.update({b"skipped": "okay"})
        self.assertEqual(
            eventFromJSON(self.savedEventJSON(inputEvent)),
            {u"hello": asbytes(range(255)).decode("charmap")}
        )


    def test_saveUnPersistableThenFormat(self):
        """
        Saving and loading an object which cannot be represented in JSON, but
        has a string representation which I{can} be saved as JSON, will result
        in the same string formatting; any extractable fields will retain their
        data types.
        """
        class Reprable(object):
            def __init__(self, value):
                self.value = value

            def __repr__(self):
                return("reprable")

        inputEvent = {
            "log_format": "{object} {object.value}",
            "object": Reprable(7)
        }
        outputEvent = eventFromJSON(self.savedEventJSON(inputEvent))
        self.assertEqual(formatEvent(outputEvent), "reprable 7")


    def test_extractingFieldsPostLoad(self):
        """
        L{extractField} can extract fields from an object that's been saved and
        loaded from JSON.
        """
        class Obj(object):
            def __init__(self):
                self.value = 345

        inputEvent = dict(log_format="{object.value}", object=Obj())
        loadedEvent = eventFromJSON(self.savedEventJSON(inputEvent))
        self.assertEqual(extractField("object.value", loadedEvent), 345)

        # The behavior of extractField is consistent between pre-persistence
        # and post-persistence events, although looking up the key directly
        # won't be:
        self.assertRaises(KeyError, extractField, "object", loadedEvent)
        self.assertRaises(KeyError, extractField, "object", inputEvent)


    def test_failureStructurePreserved(self):
        """
        Round-tripping a failure through L{eventAsJSON} preserves its class and
        structure.
        """
        events = []
        log = Logger(observer=events.append)
        try:
            1 / 0
        except ZeroDivisionError:
            f = Failure()
            log.failure("a message about failure", f)
        import sys
        if sys.exc_info()[0] is not None:
            # Make sure we don't get the same Failure by accident.
            sys.exc_clear()
        self.assertEqual(len(events), 1)
        loaded = eventFromJSON(self.savedEventJSON(events[0]))['log_failure']
        self.assertIsInstance(loaded, Failure)
        self.assertTrue(loaded.check(ZeroDivisionError))
        self.assertIsInstance(loaded.getTraceback(), str)


    def test_saveLoadLevel(self):
        """
        It's important that the C{log_level} key remain a
        L{twisted.python.constants.NamedConstant} object.
        """
        inputEvent = dict(log_level=LogLevel.warn)
        loadedEvent = eventFromJSON(self.savedEventJSON(inputEvent))
        self.assertIs(loadedEvent["log_level"], LogLevel.warn)


    def test_saveLoadUnknownLevel(self):
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

    def test_interface(self):
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


    def assertObserverWritesJSON(self, **kwargs):
        """
        Asserts that an observer created by L{jsonFileLogObserver} with the
        given arguments writes events serialized as JSON text, using the given
        record separator.

        @param recordSeparator: A record separator.
        @type recordSeparator: L{unicode}

        @param kwargs: Keyword arguments to pass to L{jsonFileLogObserver}.
        @type kwargs: L{dict}
        """
        recordSeparator = kwargs.get("recordSeparator", u"\x1e")

        with StringIO() as fileHandle:
            observer = jsonFileLogObserver(fileHandle, **kwargs)
            event = dict(x=1)
            observer(event)
            self.assertEqual(
                fileHandle.getvalue(),
                u'{0}{{"x": 1}}\n'.format(recordSeparator)
            )


    def test_observeWritesDefaultRecordSeparator(self):
        """
        A L{FileLogObserver} created by L{jsonFileLogObserver} writes events
        serialzed as JSON text to a file when it observes events.
        By default, the record separator is C{u"\\x1e"}.
        """
        self.assertObserverWritesJSON()


    def test_observeWritesEmptyRecordSeparator(self):
        """
        A L{FileLogObserver} created by L{jsonFileLogObserver} writes events
        serialzed as JSON text to a file when it observes events.
        This test sets the record separator to C{u""}.
        """
        self.assertObserverWritesJSON(recordSeparator=u"")



class LogFileReaderTests(TestCase):
    """
    Tests for L{eventsFromJSONLogFile}.
    """

    def setUp(self):
        self.errorEvents = []

        def observer(event):
            if (
                event["log_namespace"] == jsonLog.namespace and
                "record" in event
            ):
                self.errorEvents.append(event)

        self.logObserver = observer

        globalLogPublisher.addObserver(observer)


    def tearDown(self):
        globalLogPublisher.removeObserver(self.logObserver)


    def _readEvents(self, fileHandle, **kwargs):
        """
        Test that L{eventsFromJSONLogFile} reads two pre-defined events from a
        file: C{{u"x": 1}} and C{{u"y": 2}}.

        @param fileHandle: The file to read from.

        @param kwargs: Keyword arguments to pass to L{eventsFromJSONLogFile}.
        """
        events = eventsFromJSONLogFile(fileHandle, **kwargs)

        self.assertEqual(next(events), {u"x": 1})
        self.assertEqual(next(events), {u"y": 2})
        self.assertRaises(StopIteration, next, events)  # No more events


    def test_readEventsAutoWithRecordSeparator(self):
        """
        L{eventsFromJSONLogFile} reads events from a file and automatically
        detects use of C{u"\\x1e"} as the record separator.
        """
        with StringIO(
            u'\x1e{"x": 1}\n'
            u'\x1e{"y": 2}\n'
        ) as fileHandle:
            self._readEvents(fileHandle)
            self.assertEqual(len(self.errorEvents), 0)


    def test_readEventsAutoEmptyRecordSeparator(self):
        """
        L{eventsFromJSONLogFile} reads events from a file and automatically
        detects use of C{u""} as the record separator.
        """
        with StringIO(
            u'{"x": 1}\n'
            u'{"y": 2}\n'
        ) as fileHandle:
            self._readEvents(fileHandle)
            self.assertEqual(len(self.errorEvents), 0)


    def test_readEventsExplicitRecordSeparator(self):
        """
        L{eventsFromJSONLogFile} reads events from a file and is told to use
        a specific record separator.
        """
        # Use u"\x08" (backspace)... because that seems weird enough.
        with StringIO(
            u'\x08{"x": 1}\n'
            u'\x08{"y": 2}\n'
        ) as fileHandle:
            self._readEvents(fileHandle, recordSeparator=u"\x08")
            self.assertEqual(len(self.errorEvents), 0)


    def test_readEventsPartialBuffer(self):
        """
        L{eventsFromJSONLogFile} handles buffering a partial event.
        """
        with StringIO(
            u'\x1e{"x": 1}\n'
            u'\x1e{"y": 2}\n'
        ) as fileHandle:
            # Use a buffer size smaller than the event text.
            self._readEvents(fileHandle, bufferSize=1)
            self.assertEqual(len(self.errorEvents), 0)


    def test_readTruncated(self):
        """
        If the JSON text for a record is truncated, skip it.
        """
        with StringIO(
            u'\x1e{"x": 1'
            u'\x1e{"y": 2}\n'
        ) as fileHandle:
            events = eventsFromJSONLogFile(fileHandle)

            self.assertEqual(next(events), {u"y": 2})
            self.assertRaises(StopIteration, next, events)  # No more events

            # We should have logged the lost record
            self.assertEqual(len(self.errorEvents), 1)
            self.assertEqual(
                self.errorEvents[0]["log_format"],
                u"Unable to read truncated JSON record: {record!r}"
            )
            self.assertEqual(self.errorEvents[0]["record"], b'{"x": 1')


    def test_readUnicode(self):
        """
        If the file being read from vends L{unicode}, strings decode from JSON
        as-is.
        """
        # The Euro currency sign is u"\u20ac"
        with StringIO(u'\x1e{"currency": "\u20ac"}\n') as fileHandle:
            events = eventsFromJSONLogFile(fileHandle)

            self.assertEqual(next(events), {u"currency": u"\u20ac"})
            self.assertRaises(StopIteration, next, events)  # No more events
            self.assertEqual(len(self.errorEvents), 0)


    def test_readUTF8Bytes(self):
        """
        If the file being read from vends L{bytes}, strings decode from JSON as
        UTF-8.
        """
        # The Euro currency sign is b"\xe2\x82\xac" in UTF-8
        with BytesIO(b'\x1e{"currency": "\xe2\x82\xac"}\n') as fileHandle:
            events = eventsFromJSONLogFile(fileHandle)

            # The Euro currency sign is u"\u20ac"
            self.assertEqual(next(events), {u"currency": u"\u20ac"})
            self.assertRaises(StopIteration, next, events)  # No more events
            self.assertEqual(len(self.errorEvents), 0)


    def test_readTruncatedUTF8Bytes(self):
        """
        If the JSON text for a record is truncated in the middle of a two-byte
        Unicode codepoint, we don't want to see a codec exception and the
        stream is read properly when the additional data arrives.
        """
        # The Euro currency sign is u"\u20ac" and encodes in UTF-8 as three
        # bytes: b"\xe2\x82\xac".
        with BytesIO(b'\x1e{"x": "\xe2\x82\xac"}\n') as fileHandle:
            events = eventsFromJSONLogFile(fileHandle, bufferSize=8)

            self.assertEqual(next(events), {u"x": u"\u20ac"})  # Got unicode
            self.assertRaises(StopIteration, next, events)  # No more events
            self.assertEqual(len(self.errorEvents), 0)


    def test_readInvalidUTF8Bytes(self):
        """
        If the JSON text for a record contains invalid UTF-8 text, ignore that
        record.
        """
        # The string b"\xe2\xac" is bogus
        with BytesIO(
            b'\x1e{"x": "\xe2\xac"}\n'
            b'\x1e{"y": 2}\n'
        ) as fileHandle:
            events = eventsFromJSONLogFile(fileHandle)

            self.assertEqual(next(events), {u"y": 2})
            self.assertRaises(StopIteration, next, events)  # No more events

            # We should have logged the lost record
            self.assertEqual(len(self.errorEvents), 1)
            self.assertEqual(
                self.errorEvents[0]["log_format"],
                u"Unable to decode UTF-8 for JSON record: {record!r}"
            )
            self.assertEqual(
                self.errorEvents[0]["record"],
                b'{"x": "\xe2\xac"}\n'
            )


    def test_readInvalidJSON(self):
        """
        If the JSON text for a record is invalid, skip it.
        """
        with StringIO(
            u'\x1e{"x": }\n'
            u'\x1e{"y": 2}\n'
        ) as fileHandle:
            events = eventsFromJSONLogFile(fileHandle)

            self.assertEqual(next(events), {u"y": 2})
            self.assertRaises(StopIteration, next, events)  # No more events

            # We should have logged the lost record
            self.assertEqual(len(self.errorEvents), 1)
            self.assertEqual(
                self.errorEvents[0]["log_format"],
                u"Unable to read JSON record: {record!r}"
            )
            self.assertEqual(self.errorEvents[0]["record"], b'{"x": }\n')


    def test_readUnseparated(self):
        """
        Multiple events without a record separator are skipped.
        """
        with StringIO(
            u'\x1e{"x": 1}\n'
            u'{"y": 2}\n'
        ) as fileHandle:
            events = eventsFromJSONLogFile(fileHandle)

            self.assertRaises(StopIteration, next, events)  # No more events

            # We should have logged the lost record
            self.assertEqual(len(self.errorEvents), 1)
            self.assertEqual(
                self.errorEvents[0]["log_format"],
                u"Unable to read JSON record: {record!r}"
            )
            self.assertEqual(
                self.errorEvents[0]["record"],
                b'{"x": 1}\n{"y": 2}\n'
            )


    def test_roundTrip(self):
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
