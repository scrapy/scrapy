# -*- test-case-name: twisted.logger.test.test_json -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tools for saving and loading log events in a structured format.
"""

from json import dumps, loads
from typing import IO, Any, AnyStr, Dict, Iterable, Optional, Union, cast
from uuid import UUID

from constantly import NamedConstant  # type: ignore[import]

from twisted.python.failure import Failure
from ._file import FileLogObserver
from ._flatten import flattenEvent
from ._interfaces import LogEvent
from ._levels import LogLevel
from ._logger import Logger

log = Logger()


JSONDict = Dict[str, Any]


def failureAsJSON(failure: Failure) -> JSONDict:
    """
    Convert a failure to a JSON-serializable data structure.

    @param failure: A failure to serialize.

    @return: a mapping of strings to ... stuff, mostly reminiscent of
        L{Failure.__getstate__}
    """
    return dict(
        failure.__getstate__(),
        type=dict(
            __module__=failure.type.__module__,
            __name__=failure.type.__name__,
        ),
    )


def failureFromJSON(failureDict: JSONDict) -> Failure:
    """
    Load a L{Failure} from a dictionary deserialized from JSON.

    @param failureDict: a JSON-deserialized object like one previously returned
        by L{failureAsJSON}.

    @return: L{Failure}
    """
    f = Failure.__new__(Failure)
    typeInfo = failureDict["type"]
    failureDict["type"] = type(typeInfo["__name__"], (), typeInfo)
    f.__dict__ = failureDict
    return f


classInfo = [
    (
        lambda level: (
            isinstance(level, NamedConstant)
            and getattr(LogLevel, level.name, None) is level
        ),
        UUID("02E59486-F24D-46AD-8224-3ACDF2A5732A"),
        lambda level: dict(name=level.name),
        lambda level: getattr(LogLevel, level["name"], None),
    ),
    (
        lambda o: isinstance(o, Failure),
        UUID("E76887E2-20ED-49BF-A8F8-BA25CC586F2D"),
        failureAsJSON,
        failureFromJSON,
    ),
]


uuidToLoader = {uuid: loader for (predicate, uuid, saver, loader) in classInfo}


def objectLoadHook(aDict: JSONDict) -> object:
    """
    Dictionary-to-object-translation hook for certain value types used within
    the logging system.

    @see: the C{object_hook} parameter to L{json.load}

    @param aDict: A dictionary loaded from a JSON object.

    @return: C{aDict} itself, or the object represented by C{aDict}
    """
    if "__class_uuid__" in aDict:
        return uuidToLoader[UUID(aDict["__class_uuid__"])](aDict)
    return aDict


def objectSaveHook(pythonObject: object) -> JSONDict:
    """
    Object-to-serializable hook for certain value types used within the logging
    system.

    @see: the C{default} parameter to L{json.dump}

    @param pythonObject: Any object.

    @return: If the object is one of the special types the logging system
        supports, a specially-formatted dictionary; otherwise, a marker
        dictionary indicating that it could not be serialized.
    """
    for (predicate, uuid, saver, loader) in classInfo:
        if predicate(pythonObject):
            result = saver(pythonObject)
            result["__class_uuid__"] = str(uuid)
            return result
    return {"unpersistable": True}


def eventAsJSON(event: LogEvent) -> str:
    """
    Encode an event as JSON, flattening it if necessary to preserve as much
    structure as possible.

    Not all structure from the log event will be preserved when it is
    serialized.

    @param event: A log event dictionary.

    @return: A string of the serialized JSON; note that this will contain no
        newline characters, and may thus safely be stored in a line-delimited
        file.
    """

    def default(unencodable: object) -> Union[JSONDict, str]:
        """
        Serialize an object not otherwise serializable by L{dumps}.

        @param unencodable: An unencodable object.

        @return: C{unencodable}, serialized
        """
        if isinstance(unencodable, bytes):
            return unencodable.decode("charmap")
        return objectSaveHook(unencodable)

    flattenEvent(event)
    return dumps(event, default=default, skipkeys=True)


def eventFromJSON(eventText: str) -> JSONDict:
    """
    Decode a log event from JSON.

    @param eventText: The output of a previous call to L{eventAsJSON}

    @return: A reconstructed version of the log event.
    """
    return cast(JSONDict, loads(eventText, object_hook=objectLoadHook))


def jsonFileLogObserver(
    outFile: IO[Any], recordSeparator: str = "\x1e"
) -> FileLogObserver:
    """
    Create a L{FileLogObserver} that emits JSON-serialized events to a
    specified (writable) file-like object.

    Events are written in the following form::

        RS + JSON + NL

    C{JSON} is the serialized event, which is JSON text.  C{NL} is a newline
    (C{"\\n"}).  C{RS} is a record separator.  By default, this is a single
    RS character (C{"\\x1e"}), which makes the default output conform to the
    IETF draft document "draft-ietf-json-text-sequence-13".

    @param outFile: A file-like object.  Ideally one should be passed which
        accepts L{str} data.  Otherwise, UTF-8 L{bytes} will be used.
    @param recordSeparator: The record separator to use.

    @return: A file log observer.
    """
    return FileLogObserver(
        outFile, lambda event: f"{recordSeparator}{eventAsJSON(event)}\n"
    )


def eventsFromJSONLogFile(
    inFile: IO[Any],
    recordSeparator: Optional[str] = None,
    bufferSize: int = 4096,
) -> Iterable[LogEvent]:
    """
    Load events from a file previously saved with L{jsonFileLogObserver}.
    Event records that are truncated or otherwise unreadable are ignored.

    @param inFile: A (readable) file-like object.  Data read from C{inFile}
        should be L{str} or UTF-8 L{bytes}.
    @param recordSeparator: The expected record separator.
        If L{None}, attempt to automatically detect the record separator from
        one of C{"\\x1e"} or C{""}.
    @param bufferSize: The size of the read buffer used while reading from
        C{inFile}.

    @return: Log events as read from C{inFile}.
    """

    def asBytes(s: AnyStr) -> bytes:
        if isinstance(s, bytes):
            return s
        else:
            return s.encode("utf-8")

    def eventFromBytearray(record: bytearray) -> Optional[LogEvent]:
        try:
            text = bytes(record).decode("utf-8")
        except UnicodeDecodeError:
            log.error(
                "Unable to decode UTF-8 for JSON record: {record!r}",
                record=bytes(record),
            )
            return None

        try:
            return eventFromJSON(text)
        except ValueError:
            log.error("Unable to read JSON record: {record!r}", record=bytes(record))
            return None

    if recordSeparator is None:
        first = asBytes(inFile.read(1))

        if first == b"\x1e":
            # This looks json-text-sequence compliant.
            recordSeparatorBytes = first
        else:
            # Default to simpler newline-separated stream, which does not use
            # a record separator.
            recordSeparatorBytes = b""

    else:
        recordSeparatorBytes = asBytes(recordSeparator)
        first = b""

    if recordSeparatorBytes == b"":
        recordSeparatorBytes = b"\n"  # Split on newlines below

        eventFromRecord = eventFromBytearray

    else:

        def eventFromRecord(record: bytearray) -> Optional[LogEvent]:
            if record[-1] == ord("\n"):
                return eventFromBytearray(record)
            else:
                log.error(
                    "Unable to read truncated JSON record: {record!r}",
                    record=bytes(record),
                )
            return None

    buffer = bytearray(first)

    while True:
        newData = inFile.read(bufferSize)

        if not newData:
            if len(buffer) > 0:
                event = eventFromRecord(buffer)
                if event is not None:
                    yield event
            break

        buffer += asBytes(newData)
        records = buffer.split(recordSeparatorBytes)

        for record in records[:-1]:
            if len(record) > 0:
                event = eventFromRecord(record)
                if event is not None:
                    yield event

        buffer = records[-1]
