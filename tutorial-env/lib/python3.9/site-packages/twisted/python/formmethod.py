# -*- test-case-name: twisted.test.test_formmethod -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Form-based method objects.

This module contains support for descriptive method signatures that can be used
to format methods.
"""

import calendar
from typing import Any, Optional, Tuple


class FormException(Exception):
    """An error occurred calling the form method."""

    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args)
        self.descriptions = kwargs


class InputError(FormException):
    """
    An error occurred with some input.
    """


class Argument:
    """Base class for form arguments."""

    # default value for argument, if no other default is given
    defaultDefault: Any = None

    def __init__(
        self, name, default=None, shortDesc=None, longDesc=None, hints=None, allowNone=1
    ):
        self.name = name
        self.allowNone = allowNone
        if default is None:
            default = self.defaultDefault
        self.default = default
        self.shortDesc = shortDesc
        self.longDesc = longDesc
        if not hints:
            hints = {}
        self.hints = hints

    def addHints(self, **kwargs):
        self.hints.update(kwargs)

    def getHint(self, name, default=None):
        return self.hints.get(name, default)

    def getShortDescription(self):
        return self.shortDesc or self.name.capitalize()

    def getLongDescription(self):
        return self.longDesc or ""  # self.shortDesc or "The %s." % self.name

    def coerce(self, val):
        """Convert the value to the correct format."""
        raise NotImplementedError("implement in subclass")


class String(Argument):
    """A single string."""

    defaultDefault: str = ""
    min = 0
    max = None

    def __init__(
        self,
        name,
        default=None,
        shortDesc=None,
        longDesc=None,
        hints=None,
        allowNone=1,
        min=0,
        max=None,
    ):
        Argument.__init__(
            self,
            name,
            default=default,
            shortDesc=shortDesc,
            longDesc=longDesc,
            hints=hints,
            allowNone=allowNone,
        )
        self.min = min
        self.max = max

    def coerce(self, val):
        s = str(val)
        if len(s) < self.min:
            raise InputError("Value must be at least %s characters long" % self.min)
        if self.max is not None and len(s) > self.max:
            raise InputError("Value must be at most %s characters long" % self.max)
        return str(val)


class Text(String):
    """A long string."""


class Password(String):
    """A string which should be obscured when input."""


class VerifiedPassword(String):
    """A string that should be obscured when input and needs verification."""

    def coerce(self, vals):
        if len(vals) != 2 or vals[0] != vals[1]:
            raise InputError("Please enter the same password twice.")
        s = str(vals[0])
        if len(s) < self.min:
            raise InputError("Value must be at least %s characters long" % self.min)
        if self.max is not None and len(s) > self.max:
            raise InputError("Value must be at most %s characters long" % self.max)
        return s


class Hidden(String):
    """A string which is not displayed.

    The passed default is used as the value.
    """


class Integer(Argument):
    """A single integer."""

    defaultDefault: Optional[int] = None

    def __init__(
        self, name, allowNone=1, default=None, shortDesc=None, longDesc=None, hints=None
    ):
        # although Argument now has allowNone, that was recently added, and
        # putting it at the end kept things which relied on argument order
        # from breaking.  However, allowNone originally was in here, so
        # I have to keep the same order, to prevent breaking code that
        # depends on argument order only
        Argument.__init__(self, name, default, shortDesc, longDesc, hints, allowNone)

    def coerce(self, val):
        if not val.strip() and self.allowNone:
            return None
        try:
            return int(val)
        except ValueError:
            raise InputError(
                "{} is not valid, please enter " "a whole number, e.g. 10".format(val)
            )


class IntegerRange(Integer):
    def __init__(
        self,
        name,
        min,
        max,
        allowNone=1,
        default=None,
        shortDesc=None,
        longDesc=None,
        hints=None,
    ):
        self.min = min
        self.max = max
        Integer.__init__(
            self,
            name,
            allowNone=allowNone,
            default=default,
            shortDesc=shortDesc,
            longDesc=longDesc,
            hints=hints,
        )

    def coerce(self, val):
        result = Integer.coerce(self, val)
        if self.allowNone and result == None:
            return result
        if result < self.min:
            raise InputError(
                "Value {} is too small, it should be at least {}".format(
                    result, self.min
                )
            )
        if result > self.max:
            raise InputError(
                "Value {} is too large, it should be at most {}".format(
                    result, self.max
                )
            )
        return result


class Float(Argument):

    defaultDefault: Optional[float] = None

    def __init__(
        self, name, allowNone=1, default=None, shortDesc=None, longDesc=None, hints=None
    ):
        # although Argument now has allowNone, that was recently added, and
        # putting it at the end kept things which relied on argument order
        # from breaking.  However, allowNone originally was in here, so
        # I have to keep the same order, to prevent breaking code that
        # depends on argument order only
        Argument.__init__(self, name, default, shortDesc, longDesc, hints, allowNone)

    def coerce(self, val):
        if not val.strip() and self.allowNone:
            return None
        try:
            return float(val)
        except ValueError:
            raise InputError("Invalid float: %s" % val)


class Choice(Argument):
    """
    The result of a choice between enumerated types.  The choices should
    be a list of tuples of tag, value, and description.  The tag will be
    the value returned if the user hits "Submit", and the description
    is the bale for the enumerated type.  default is a list of all the
    values (seconds element in choices).  If no defaults are specified,
    initially the first item will be selected.  Only one item can (should)
    be selected at once.
    """

    def __init__(
        self,
        name,
        choices=[],
        default=[],
        shortDesc=None,
        longDesc=None,
        hints=None,
        allowNone=1,
    ):
        self.choices = choices
        if choices and not default:
            default.append(choices[0][1])
        Argument.__init__(
            self, name, default, shortDesc, longDesc, hints, allowNone=allowNone
        )

    def coerce(self, inIdent):
        for ident, val, desc in self.choices:
            if ident == inIdent:
                return val
        else:
            raise InputError("Invalid Choice: %s" % inIdent)


class Flags(Argument):
    """
    The result of a checkbox group or multi-menu.  The flags should be a
    list of tuples of tag, value, and description. The tag will be
    the value returned if the user hits "Submit", and the description
    is the bale for the enumerated type.  default is a list of all the
    values (second elements in flags).  If no defaults are specified,
    initially nothing will be selected.  Several items may be selected at
    once.
    """

    def __init__(
        self,
        name,
        flags=(),
        default=(),
        shortDesc=None,
        longDesc=None,
        hints=None,
        allowNone=1,
    ):
        self.flags = flags
        Argument.__init__(
            self, name, default, shortDesc, longDesc, hints, allowNone=allowNone
        )

    def coerce(self, inFlagKeys):
        if not inFlagKeys:
            return []
        outFlags = []
        for inFlagKey in inFlagKeys:
            for flagKey, flagVal, flagDesc in self.flags:
                if inFlagKey == flagKey:
                    outFlags.append(flagVal)
                    break
            else:
                raise InputError("Invalid Flag: %s" % inFlagKey)
        return outFlags


class CheckGroup(Flags):
    pass


class RadioGroup(Choice):
    pass


class Boolean(Argument):
    def coerce(self, inVal):
        if not inVal:
            return 0
        lInVal = str(inVal).lower()
        if lInVal in ("no", "n", "f", "false", "0"):
            return 0
        return 1


class File(Argument):
    def __init__(self, name, allowNone=1, shortDesc=None, longDesc=None, hints=None):
        Argument.__init__(
            self, name, None, shortDesc, longDesc, hints, allowNone=allowNone
        )

    def coerce(self, file):
        if not file and self.allowNone:
            return None
        elif file:
            return file
        else:
            raise InputError("Invalid File")


def positiveInt(x):
    x = int(x)
    if x <= 0:
        raise ValueError
    return x


class Date(Argument):
    """A date -- (year, month, day) tuple."""

    defaultDefault: Optional[Tuple[int, int, int]] = None

    def __init__(
        self, name, allowNone=1, default=None, shortDesc=None, longDesc=None, hints=None
    ):
        Argument.__init__(self, name, default, shortDesc, longDesc, hints)
        self.allowNone = allowNone
        if not allowNone:
            self.defaultDefault = (1970, 1, 1)

    def coerce(self, args):
        """Return tuple of ints (year, month, day)."""
        if tuple(args) == ("", "", "") and self.allowNone:
            return None

        try:
            year, month, day = map(positiveInt, args)
        except ValueError:
            raise InputError("Invalid date")
        if (month, day) == (2, 29):
            if not calendar.isleap(year):
                raise InputError("%d was not a leap year" % year)
            else:
                return year, month, day
        try:
            mdays = calendar.mdays[month]
        except IndexError:
            raise InputError("Invalid date")
        if day > mdays:
            raise InputError("Invalid date")
        return year, month, day


class Submit(Choice):
    """Submit button or a reasonable facsimile thereof."""

    def __init__(
        self,
        name,
        choices=[("Submit", "submit", "Submit form")],
        reset=0,
        shortDesc=None,
        longDesc=None,
        allowNone=0,
        hints=None,
    ):
        Choice.__init__(
            self,
            name,
            choices=choices,
            shortDesc=shortDesc,
            longDesc=longDesc,
            hints=hints,
        )
        self.allowNone = allowNone
        self.reset = reset

    def coerce(self, value):
        if self.allowNone and not value:
            return None
        else:
            return Choice.coerce(self, value)


class PresentationHint:
    """
    A hint to a particular system.
    """


class MethodSignature:
    """
    A signature of a callable.
    """

    def __init__(self, *sigList):
        """"""
        self.methodSignature = sigList

    def getArgument(self, name):
        for a in self.methodSignature:
            if a.name == name:
                return a

    def method(self, callable, takesRequest=False):
        return FormMethod(self, callable, takesRequest)


class FormMethod:
    """A callable object with a signature."""

    def __init__(self, signature, callable, takesRequest=False):
        self.signature = signature
        self.callable = callable
        self.takesRequest = takesRequest

    def getArgs(self):
        return tuple(self.signature.methodSignature)

    def call(self, *args, **kw):
        return self.callable(*args, **kw)
