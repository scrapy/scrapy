# -*- test-case-name: twisted.logger.test.test_flatten -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Code related to "flattening" events; that is, extracting a description of all
relevant fields from the format string and persisting them for later
examination.
"""

from string import Formatter
from collections import defaultdict

from twisted.python.compat import unicode

aFormatter = Formatter()



class KeyFlattener(object):
    """
    A L{KeyFlattener} computes keys for the things within curly braces in
    PEP-3101-style format strings as parsed by L{string.Formatter.parse}.
    """

    def __init__(self):
        """
        Initialize a L{KeyFlattener}.
        """
        self.keys = defaultdict(lambda: 0)


    def flatKey(self, fieldName, formatSpec, conversion):
        """
        Compute a string key for a given field/format/conversion.

        @param fieldName: A format field name.
        @type fieldName: L{str}

        @param formatSpec: A format spec.
        @type formatSpec: L{str}

        @param conversion: A format field conversion type.
        @type conversion: L{str}

        @return: A key specific to the given field, format and conversion, as
            well as the occurrence of that combination within this
            L{KeyFlattener}'s lifetime.
        @rtype: L{str}
        """
        result = (
            "{fieldName}!{conversion}:{formatSpec}"
            .format(
                fieldName=fieldName,
                formatSpec=(formatSpec or ""),
                conversion=(conversion or ""),
            )
        )
        self.keys[result] += 1
        n = self.keys[result]
        if n != 1:
            result += "/" + str(self.keys[result])
        return result



def flattenEvent(event):
    """
    Flatten the given event by pre-associating format fields with specific
    objects and callable results in a L{dict} put into the C{"log_flattened"}
    key in the event.

    @param event: A logging event.
    @type event: L{dict}
    """
    if "log_format" not in event:
        return

    if "log_flattened" in event:
        fields = event["log_flattened"]
    else:
        fields = {}

    keyFlattener = KeyFlattener()

    for (literalText, fieldName, formatSpec, conversion) in (
        aFormatter.parse(event["log_format"])
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

        if fieldName.endswith(u"()"):
            fieldName = fieldName[:-2]
            callit = True
        else:
            callit = False

        field = aFormatter.get_field(fieldName, (), event)
        fieldValue = field[0]

        if conversion == "r":
            conversionFunction = repr
        else:  # Above: if conversion is not "r", it's "s"
            conversionFunction = unicode

        if callit:
            fieldValue = fieldValue()

        flattenedValue = conversionFunction(fieldValue)
        fields[flattenedKey] = flattenedValue
        fields[structuredKey] = fieldValue

    if fields:
        event["log_flattened"] = fields



def extractField(field, event):
    """
    Extract a given format field from the given event.

    @param field: A string describing a format field or log key.  This is the
        text that would normally fall between a pair of curly braces in a
        format string: for example, C{"key[2].attribute"}.  If a conversion is
        specified (the thing after the C{"!"} character in a format field) then
        the result will always be L{unicode}.
    @type field: L{str} (native string)

    @param event: A log event.
    @type event: L{dict}

    @return: A value extracted from the field.
    @rtype: L{object}

    @raise KeyError: if the field is not found in the given event.
    """
    keyFlattener = KeyFlattener()
    [[literalText, fieldName, formatSpec, conversion]] = aFormatter.parse(
        "{" + field + "}"
    )
    key = keyFlattener.flatKey(fieldName, formatSpec, conversion)
    if "log_flattened" not in event:
        flattenEvent(event)
    return event["log_flattened"][key]



def flatFormat(event):
    """
    Format an event which has been flattened with L{flattenEvent}.

    @param event: A logging event.
    @type event: L{dict}

    @return: A formatted string.
    @rtype: L{unicode}
    """
    fieldValues = event["log_flattened"]
    s = []
    keyFlattener = KeyFlattener()
    formatFields = aFormatter.parse(event["log_format"])
    for literalText, fieldName, formatSpec, conversion in formatFields:
        s.append(literalText)
        if fieldName is not None:
            key = keyFlattener.flatKey(
                    fieldName, formatSpec, conversion or "s")
            s.append(unicode(fieldValues[key]))
    return u"".join(s)
