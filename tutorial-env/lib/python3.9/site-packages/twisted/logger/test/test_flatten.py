# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for L{twisted.logger._format}.
"""

import json
from itertools import count
from typing import Any, Callable, Optional

try:
    from time import tzset
except ImportError:
    tzset = None  # type: ignore[assignment]

from twisted.trial import unittest
from .._flatten import KeyFlattener, aFormatter, extractField, flattenEvent
from .._format import formatEvent
from .._interfaces import LogEvent


class FlatFormattingTests(unittest.TestCase):
    """
    Tests for flattened event formatting functions.
    """

    def test_formatFlatEvent(self) -> None:
        """
        L{flattenEvent} will "flatten" an event so that, if scrubbed of all but
        serializable objects, it will preserve all necessary data to be
        formatted once serialized.  When presented with an event thusly
        flattened, L{formatEvent} will produce the same output.
        """
        counter = count()

        class Ephemeral:
            attribute = "value"

        event1 = dict(
            log_format=(
                "callable: {callme()} "
                "attribute: {object.attribute} "
                "numrepr: {number!r} "
                "numstr: {number!s} "
                "strrepr: {string!r} "
                "unistr: {unistr!s}"
            ),
            callme=lambda: next(counter),
            object=Ephemeral(),
            number=7,
            string="hello",
            unistr="ö",
        )

        flattenEvent(event1)

        event2 = dict(event1)
        del event2["callme"]
        del event2["object"]
        event3 = json.loads(json.dumps(event2))
        self.assertEqual(
            formatEvent(event3),
            (
                "callable: 0 "
                "attribute: value "
                "numrepr: 7 "
                "numstr: 7 "
                "strrepr: 'hello' "
                "unistr: ö"
            ),
        )

    def test_formatFlatEventBadFormat(self) -> None:
        """
        If the format string is invalid, an error is produced.
        """
        event1 = dict(
            log_format=("strrepr: {string!X}"),
            string="hello",
        )

        flattenEvent(event1)
        event2 = json.loads(json.dumps(event1))

        self.assertTrue(formatEvent(event2).startswith("Unable to format event"))

    def test_formatFlatEventWithMutatedFields(self) -> None:
        """
        L{formatEvent} will prefer the stored C{str()} or C{repr()} value for
        an object, in case the other version.
        """

        class Unpersistable:
            """
            Unpersitable object.
            """

            destructed = False

            def selfDestruct(self) -> None:
                """
                Self destruct.
                """
                self.destructed = True

            def __repr__(self) -> str:
                if self.destructed:
                    return "post-serialization garbage"
                else:
                    return "un-persistable"

        up = Unpersistable()
        event1 = dict(log_format="unpersistable: {unpersistable}", unpersistable=up)

        flattenEvent(event1)
        up.selfDestruct()

        self.assertEqual(formatEvent(event1), "unpersistable: un-persistable")

    def test_keyFlattening(self) -> None:
        """
        Test that L{KeyFlattener.flatKey} returns the expected keys for format
        fields.
        """

        def keyFromFormat(format: str) -> str:
            for (
                literalText,
                fieldName,
                formatSpec,
                conversion,
            ) in aFormatter.parse(format):
                assert fieldName is not None
                return KeyFlattener().flatKey(fieldName, formatSpec, conversion)
            assert False, "Unable to derive key from format: {format}"

        # No name
        try:
            self.assertEqual(keyFromFormat("{}"), "!:")
        except ValueError:
            # In python 2.6, an empty field name causes Formatter.parse to
            # raise ValueError.
            # In Python 2.7, it's allowed, so this exception is unexpected.
            raise

        # Just a name
        self.assertEqual(keyFromFormat("{foo}"), "foo!:")

        # Add conversion
        self.assertEqual(keyFromFormat("{foo!s}"), "foo!s:")
        self.assertEqual(keyFromFormat("{foo!r}"), "foo!r:")

        # Add format spec
        self.assertEqual(keyFromFormat("{foo:%s}"), "foo!:%s")
        self.assertEqual(keyFromFormat("{foo:!}"), "foo!:!")
        self.assertEqual(keyFromFormat("{foo::}"), "foo!::")

        # Both
        self.assertEqual(keyFromFormat("{foo!s:%s}"), "foo!s:%s")
        self.assertEqual(keyFromFormat("{foo!s:!}"), "foo!s:!")
        self.assertEqual(keyFromFormat("{foo!s::}"), "foo!s::")

        sameFlattener = KeyFlattener()
        (
            (
                literalText,
                fieldName,
                formatSpec,
                conversion,
            ),
        ) = aFormatter.parse("{x}")
        assert fieldName is not None

        self.assertEqual(
            sameFlattener.flatKey(fieldName, formatSpec, conversion), "x!:"
        )
        self.assertEqual(
            sameFlattener.flatKey(fieldName, formatSpec, conversion), "x!:/2"
        )

    def _test_formatFlatEvent_fieldNamesSame(
        self, event: Optional[LogEvent] = None
    ) -> LogEvent:
        """
        The same format field used twice in one event is rendered twice.

        @param event: An event to flatten.  If L{None}, create a new event.
        @return: C{event} or the event created.
        """
        if event is None:
            counter = count()

            class CountStr:
                """
                Hack
                """

                def __str__(self) -> str:
                    return str(next(counter))

            event = dict(
                log_format="{x} {x}",
                x=CountStr(),
            )

        flattenEvent(event)
        self.assertEqual(formatEvent(event), "0 1")

        return event

    def test_formatFlatEventFieldNamesSame(self) -> None:
        """
        The same format field used twice in one event is rendered twice.
        """
        self._test_formatFlatEvent_fieldNamesSame()

    def test_formatFlatEventFieldNamesSameAgain(self) -> None:
        """
        The same event flattened twice gives the same (already rendered)
        result.
        """
        event = self._test_formatFlatEvent_fieldNamesSame()
        self._test_formatFlatEvent_fieldNamesSame(event)

    def test_formatEventFlatTrailingText(self) -> None:
        """
        L{formatEvent} will handle a flattened event with tailing text after
        a replacement field.
        """
        event = dict(
            log_format="test {x} trailing",
            x="value",
        )
        flattenEvent(event)

        result = formatEvent(event)

        self.assertEqual(result, "test value trailing")

    def test_extractField(
        self, flattenFirst: Callable[[LogEvent], LogEvent] = lambda x: x
    ) -> None:
        """
        L{extractField} will extract a field used in the format string.

        @param flattenFirst: callable to flatten an event
        """

        class ObjectWithRepr:
            def __repr__(self) -> str:
                return "repr"

        class Something:
            def __init__(self) -> None:
                self.number = 7
                self.object = ObjectWithRepr()

            def __getstate__(self) -> None:
                raise NotImplementedError("Just in case.")

        event = dict(
            log_format="{something.number} {something.object}",
            something=Something(),
        )

        flattened = flattenFirst(event)

        def extract(field: str) -> Any:
            return extractField(field, flattened)

        self.assertEqual(extract("something.number"), 7)
        self.assertEqual(extract("something.number!s"), "7")
        self.assertEqual(extract("something.object!s"), "repr")

    def test_extractFieldFlattenFirst(self) -> None:
        """
        L{extractField} behaves identically if the event is explicitly
        flattened first.
        """

        def flattened(event: LogEvent) -> LogEvent:
            flattenEvent(event)
            return event

        self.test_extractField(flattened)

    def test_flattenEventWithoutFormat(self) -> None:
        """
        L{flattenEvent} will do nothing to an event with no format string.
        """
        inputEvent = {"a": "b", "c": 1}
        flattenEvent(inputEvent)
        self.assertEqual(inputEvent, {"a": "b", "c": 1})

    def test_flattenEventWithInertFormat(self) -> None:
        """
        L{flattenEvent} will do nothing to an event with a format string that
        contains no format fields.
        """
        inputEvent = {"a": "b", "c": 1, "log_format": "simple message"}
        flattenEvent(inputEvent)
        self.assertEqual(
            inputEvent,
            {
                "a": "b",
                "c": 1,
                "log_format": "simple message",
            },
        )

    def test_flattenEventWithNoneFormat(self) -> None:
        """
        L{flattenEvent} will do nothing to an event with log_format set to
        None.
        """
        inputEvent = {"a": "b", "c": 1, "log_format": None}
        flattenEvent(inputEvent)
        self.assertEqual(
            inputEvent,
            {
                "a": "b",
                "c": 1,
                "log_format": None,
            },
        )
