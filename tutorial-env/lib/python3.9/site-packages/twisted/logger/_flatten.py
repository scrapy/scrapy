# -*- test-case-name: twisted.logger.test.test_flatten -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Code related to "flattening" events; that is, extracting a description of all
relevant fields from the format string and persisting them for later
examination.
"""

from collections import defaultdict
from string import Formatter
from typing import Any, Dict, Optional

from ._interfaces import LogEvent

aFormatter = Formatter()


class KeyFlattener:
    """
    A L{KeyFlattener} computes keys for the things within curly braces in
    PEP-3101-style format strings as parsed by L{string.Formatter.parse}.
    """

    def __init__(self) -> None:
        """
        Initialize a L{KeyFlattener}.
        """
        self.keys: Dict[str, int] = defaultdict(lambda: 0)

    def flatKey(
        self, fieldName: str, formatSpec: Optional[str], conversion: Optional[str]
    ) -> str:
        """
        Compute a string key for a given field/format/conversion.

        @param fieldName: A format field name.
        @param formatSpec: A format spec.
        @param conversion: A format field conversion type.

        @return: A key specific to the given field, format and conversion, as
            well as the occurrence of that combination within this
            L{KeyFlattener}'s lifetime.
        """
        if formatSpec is None:
            formatSpec = ""

        if conversion is None:
            conversion = ""

        result = "{fieldName}!{conversion}:{formatSpec}".format(
            fieldName=fieldName,
            formatSpec=formatSpec,
            conversion=conversion,
        )
        self.keys[result] += 1
        n = self.keys[result]
        if n != 1:
            result += "/" + str(self.keys[result])
        return result


def flattenEvent(event: LogEvent) -> None:
    """
    Flatten the given event by pre-associating format fields with specific
    objects and callable results in a L{dict} put into the C{"log_flattened"}
    key in the event.

    @param event: A logging event.
    """
    if event.get("log_format", None) is None:
        return

    if "log_flattened" in event:
        fields = event["log_flattened"]
    else:
        fields = {}

    keyFlattener = KeyFlattener()

    for (literalText, fieldName, formatSpec, conversion) in aFormatter.parse(
        event["log_format"]
    ):
        if fieldName is None:
            continue

        if conversion != "r":
            conversion = "s"

        flattenedKey = keyFlattener.flatKey(fieldName, formatSpec, conversion)
        structuredKey = keyFlattener.flatKey(fieldName, formatSpec, "")

        if flattenedKey in fields:
            # We've already seen and handled this key
            continue

        if fieldName.endswith("()"):
            fieldName = fieldName[:-2]
            callit = True
        else:
            callit = False

        field = aFormatter.get_field(fieldName, (), event)
        fieldValue = field[0]

        if conversion == "r":
            conversionFunction = repr
        else:  # Above: if conversion is not "r", it's "s"
            conversionFunction = str

        if callit:
            fieldValue = fieldValue()

        flattenedValue = conversionFunction(fieldValue)
        fields[flattenedKey] = flattenedValue
        fields[structuredKey] = fieldValue

    if fields:
        event["log_flattened"] = fields


def extractField(field: str, event: LogEvent) -> Any:
    """
    Extract a given format field from the given event.

    @param field: A string describing a format field or log key.  This is the
        text that would normally fall between a pair of curly braces in a
        format string: for example, C{"key[2].attribute"}.  If a conversion is
        specified (the thing after the C{"!"} character in a format field) then
        the result will always be str.
    @param event: A log event.

    @return: A value extracted from the field.

    @raise KeyError: if the field is not found in the given event.
    """
    keyFlattener = KeyFlattener()

    [[literalText, fieldName, formatSpec, conversion]] = aFormatter.parse(
        "{" + field + "}"
    )

    assert fieldName is not None

    key = keyFlattener.flatKey(fieldName, formatSpec, conversion)

    if "log_flattened" not in event:
        flattenEvent(event)

    return event["log_flattened"][key]


def flatFormat(event: LogEvent) -> str:
    """
    Format an event which has been flattened with L{flattenEvent}.

    @param event: A logging event.

    @return: A formatted string.
    """
    fieldValues = event["log_flattened"]
    keyFlattener = KeyFlattener()
    s = []

    for literalText, fieldName, formatSpec, conversion in aFormatter.parse(
        event["log_format"]
    ):
        s.append(literalText)

        if fieldName is not None:
            key = keyFlattener.flatKey(fieldName, formatSpec, conversion or "s")
            s.append(str(fieldValues[key]))

    return "".join(s)
