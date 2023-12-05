# -*- test-case-name: twisted.words.test.test_jabberxmppstringprep -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

import stringprep
from encodings import idna
from itertools import chain

# We require Unicode version 3.2.
from unicodedata import ucd_3_2_0 as unicodedata

from zope.interface import Interface, implementer

from incremental import Version

from twisted.python.deprecate import deprecatedModuleAttribute

crippled = False
deprecatedModuleAttribute(
    Version("Twisted", 13, 1, 0), "crippled is always False", __name__, "crippled"
)


class ILookupTable(Interface):
    """
    Interface for character lookup classes.
    """

    def lookup(c):
        """
        Return whether character is in this table.
        """


class IMappingTable(Interface):
    """
    Interface for character mapping classes.
    """

    def map(c):
        """
        Return mapping for character.
        """


@implementer(ILookupTable)
class LookupTableFromFunction:
    def __init__(self, in_table_function):
        self.lookup = in_table_function


@implementer(ILookupTable)
class LookupTable:
    def __init__(self, table):
        self._table = table

    def lookup(self, c):
        return c in self._table


@implementer(IMappingTable)
class MappingTableFromFunction:
    def __init__(self, map_table_function):
        self.map = map_table_function


@implementer(IMappingTable)
class EmptyMappingTable:
    def __init__(self, in_table_function):
        self._in_table_function = in_table_function

    def map(self, c):
        if self._in_table_function(c):
            return None
        else:
            return c


class Profile:
    def __init__(
        self,
        mappings=[],
        normalize=True,
        prohibiteds=[],
        check_unassigneds=True,
        check_bidi=True,
    ):
        self.mappings = mappings
        self.normalize = normalize
        self.prohibiteds = prohibiteds
        self.do_check_unassigneds = check_unassigneds
        self.do_check_bidi = check_bidi

    def prepare(self, string):
        result = self.map(string)
        if self.normalize:
            result = unicodedata.normalize("NFKC", result)
        self.check_prohibiteds(result)
        if self.do_check_unassigneds:
            self.check_unassigneds(result)
        if self.do_check_bidi:
            self.check_bidirectionals(result)
        return result

    def map(self, string):
        result = []

        for c in string:
            result_c = c

            for mapping in self.mappings:
                result_c = mapping.map(c)
                if result_c != c:
                    break

            if result_c is not None:
                result.append(result_c)

        return "".join(result)

    def check_prohibiteds(self, string):
        for c in string:
            for table in self.prohibiteds:
                if table.lookup(c):
                    raise UnicodeError("Invalid character %s" % repr(c))

    def check_unassigneds(self, string):
        for c in string:
            if stringprep.in_table_a1(c):
                raise UnicodeError("Unassigned code point %s" % repr(c))

    def check_bidirectionals(self, string):
        found_LCat = False
        found_RandALCat = False

        for c in string:
            if stringprep.in_table_d1(c):
                found_RandALCat = True
            if stringprep.in_table_d2(c):
                found_LCat = True

        if found_LCat and found_RandALCat:
            raise UnicodeError("Violation of BIDI Requirement 2")

        if found_RandALCat and not (
            stringprep.in_table_d1(string[0]) and stringprep.in_table_d1(string[-1])
        ):
            raise UnicodeError("Violation of BIDI Requirement 3")


class NamePrep:
    """Implements preparation of internationalized domain names.

    This class implements preparing internationalized domain names using the
    rules defined in RFC 3491, section 4 (Conversion operations).

    We do not perform step 4 since we deal with unicode representations of
    domain names and do not convert from or to ASCII representations using
    punycode encoding. When such a conversion is needed, the C{idna} standard
    library provides the C{ToUnicode()} and C{ToASCII()} functions. Note that
    C{idna} itself assumes UseSTD3ASCIIRules to be false.

    The following steps are performed by C{prepare()}:

      - Split the domain name in labels at the dots (RFC 3490, 3.1)
      - Apply nameprep proper on each label (RFC 3491)
      - Enforce the restrictions on ASCII characters in host names by
        assuming STD3ASCIIRules to be true. (STD 3)
      - Rejoin the labels using the label separator U+002E (full stop).

    """

    # Prohibited characters.
    prohibiteds = [
        chr(n)
        for n in chain(
            range(0x00, 0x2C + 1),
            range(0x2E, 0x2F + 1),
            range(0x3A, 0x40 + 1),
            range(0x5B, 0x60 + 1),
            range(0x7B, 0x7F + 1),
        )
    ]

    def prepare(self, string):
        result = []

        labels = idna.dots.split(string)

        if labels and len(labels[-1]) == 0:
            trailing_dot = "."
            del labels[-1]
        else:
            trailing_dot = ""

        for label in labels:
            result.append(self.nameprep(label))

        return ".".join(result) + trailing_dot

    def check_prohibiteds(self, string):
        for c in string:
            if c in self.prohibiteds:
                raise UnicodeError("Invalid character %s" % repr(c))

    def nameprep(self, label):
        label = idna.nameprep(label)
        self.check_prohibiteds(label)
        if label[0] == "-":
            raise UnicodeError("Invalid leading hyphen-minus")
        if label[-1] == "-":
            raise UnicodeError("Invalid trailing hyphen-minus")
        return label


C_11 = LookupTableFromFunction(stringprep.in_table_c11)
C_12 = LookupTableFromFunction(stringprep.in_table_c12)
C_21 = LookupTableFromFunction(stringprep.in_table_c21)
C_22 = LookupTableFromFunction(stringprep.in_table_c22)
C_3 = LookupTableFromFunction(stringprep.in_table_c3)
C_4 = LookupTableFromFunction(stringprep.in_table_c4)
C_5 = LookupTableFromFunction(stringprep.in_table_c5)
C_6 = LookupTableFromFunction(stringprep.in_table_c6)
C_7 = LookupTableFromFunction(stringprep.in_table_c7)
C_8 = LookupTableFromFunction(stringprep.in_table_c8)
C_9 = LookupTableFromFunction(stringprep.in_table_c9)

B_1 = EmptyMappingTable(stringprep.in_table_b1)
B_2 = MappingTableFromFunction(stringprep.map_table_b2)

nodeprep = Profile(
    mappings=[B_1, B_2],
    prohibiteds=[
        C_11,
        C_12,
        C_21,
        C_22,
        C_3,
        C_4,
        C_5,
        C_6,
        C_7,
        C_8,
        C_9,
        LookupTable(['"', "&", "'", "/", ":", "<", ">", "@"]),
    ],
)

resourceprep = Profile(
    mappings=[
        B_1,
    ],
    prohibiteds=[C_12, C_21, C_22, C_3, C_4, C_5, C_6, C_7, C_8, C_9],
)

nameprep = NamePrep()
