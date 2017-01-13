#
# SNMPv2c message syntax
#
# ASN.1 source from:
# http://www.ietf.org/rfc/rfc1901.txt
#
from pyasn1.type import univ, namedtype, namedval

class Message(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('version', univ.Integer(namedValues = namedval.NamedValues(('version-2c', 1)))),
        namedtype.NamedType('community', univ.OctetString()),
        namedtype.NamedType('data', univ.Any())
        )

