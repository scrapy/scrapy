# BER encoder
from pyasn1.type import base, tag, univ, char, useful
from pyasn1.codec.ber import eoo
from pyasn1.compat.octets import int2oct, oct2int, ints2octs, null, str2octs
from pyasn1 import debug, error

class Error(Exception): pass

class AbstractItemEncoder:
    supportIndefLenMode = 1
    def encodeTag(self, t, isConstructed):
        tagClass, tagFormat, tagId = t.asTuple()  # this is a hotspot
        v = tagClass | tagFormat
        if isConstructed:
            v = v|tag.tagFormatConstructed
        if tagId < 31:
            return int2oct(v|tagId)
        else:
            s = int2oct(tagId&0x7f)
            tagId = tagId >> 7
            while tagId:
                s = int2oct(0x80|(tagId&0x7f)) + s
                tagId = tagId >> 7
            return int2oct(v|0x1F) + s

    def encodeLength(self, length, defMode):
        if not defMode and self.supportIndefLenMode:
            return int2oct(0x80)
        if length < 0x80:
            return int2oct(length)
        else:
            substrate = null
            while length:
                substrate = int2oct(length&0xff) + substrate
                length = length >> 8
            substrateLen = len(substrate)
            if substrateLen > 126:
                raise Error('Length octets overflow (%d)' % substrateLen)
            return int2oct(0x80 | substrateLen) + substrate

    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        raise Error('Not implemented')

    def _encodeEndOfOctets(self, encodeFun, defMode):
        if defMode or not self.supportIndefLenMode:
            return null
        else:
            return encodeFun(eoo.endOfOctets, defMode)
        
    def encode(self, encodeFun, value, defMode, maxChunkSize):
        substrate, isConstructed = self.encodeValue(
            encodeFun, value, defMode, maxChunkSize
            )
        tagSet = value.getTagSet()
        if tagSet:
            if not isConstructed:  # primitive form implies definite mode
                defMode = 1
            return self.encodeTag(
                tagSet[-1], isConstructed
                ) + self.encodeLength(
                len(substrate), defMode
                ) + substrate + self._encodeEndOfOctets(encodeFun, defMode)
        else:
            return substrate  # untagged value

class EndOfOctetsEncoder(AbstractItemEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        return null, 0

class ExplicitlyTaggedItemEncoder(AbstractItemEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        if isinstance(value, base.AbstractConstructedAsn1Item):
            value = value.clone(tagSet=value.getTagSet()[:-1],
                                cloneValueFlag=1)
        else:
            value = value.clone(tagSet=value.getTagSet()[:-1])
        return encodeFun(value, defMode, maxChunkSize), 1

explicitlyTaggedItemEncoder = ExplicitlyTaggedItemEncoder()

class BooleanEncoder(AbstractItemEncoder):
    supportIndefLenMode = 0
    _true = ints2octs((1,))
    _false = ints2octs((0,))
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        return value and self._true or self._false, 0

class IntegerEncoder(AbstractItemEncoder):
    supportIndefLenMode = 0
    supportCompactZero = False
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        if value == 0:  # shortcut for zero value
            if self.supportCompactZero:
                # this seems to be a correct way for encoding zeros
                return null, 0
            else:
                # this seems to be a widespread way for encoding zeros
                return ints2octs((0,)), 0
        octets = []
        value = int(value) # to save on ops on asn1 type
        while 1:
            octets.insert(0, value & 0xff)
            if value == 0 or value == -1:
                break
            value = value >> 8
        if value == 0 and octets[0] & 0x80:
            octets.insert(0, 0)
        while len(octets) > 1 and \
                  (octets[0] == 0 and octets[1] & 0x80 == 0 or \
                   octets[0] == 0xff and octets[1] & 0x80 != 0):
            del octets[0]
        return ints2octs(octets), 0

class BitStringEncoder(AbstractItemEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        if not maxChunkSize or len(value) <= maxChunkSize*8:
            out_len = (len(value) + 7) // 8
            out_list = out_len * [0]
            j = 7
            i = -1
            for val in value:
                j += 1
                if j == 8:
                    i += 1
                    j = 0
                out_list[i] = out_list[i] | val << (7-j)
            return int2oct(7-j) + ints2octs(out_list), 0
        else:
            pos = 0; substrate = null
            while 1:
                # count in octets
                v = value.clone(value[pos*8:pos*8+maxChunkSize*8])
                if not v:
                    break
                substrate = substrate + encodeFun(v, defMode, maxChunkSize)
                pos = pos + maxChunkSize
            return substrate, 1

class OctetStringEncoder(AbstractItemEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        if not maxChunkSize or len(value) <= maxChunkSize:
            return value.asOctets(), 0
        else:
            pos = 0; substrate = null
            while 1:
                v = value.clone(value[pos:pos+maxChunkSize])
                if not v:
                    break
                substrate = substrate + encodeFun(v, defMode, maxChunkSize)
                pos = pos + maxChunkSize
            return substrate, 1

class NullEncoder(AbstractItemEncoder):
    supportIndefLenMode = 0
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        return null, 0

class ObjectIdentifierEncoder(AbstractItemEncoder):
    supportIndefLenMode = 0
    precomputedValues = {
        (1, 3, 6, 1, 2): (43, 6, 1, 2),        
        (1, 3, 6, 1, 4): (43, 6, 1, 4)
    }
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):    
        oid = value.asTuple()
        if oid[:5] in self.precomputedValues:
            octets = self.precomputedValues[oid[:5]]
            oid = oid[5:]
        else:
            if len(oid) < 2:
                raise error.PyAsn1Error('Short OID %s' % (value,))

            octets = ()

            # Build the first twos
            if oid[0] == 0 and 0 <= oid[1] <= 39:
                oid = (oid[1],) + oid[2:]
            elif oid[0] == 1 and 0 <= oid[1] <= 39:
                oid = (oid[1] + 40,) + oid[2:]
            elif oid[0] == 2:
                oid = (oid[1] + 80,) + oid[2:]
            else:
                raise error.PyAsn1Error(
                    'Impossible initial arcs %s at %s' % (oid[:2], value)
                    )

        # Cycle through subIds
        for subId in oid:
            if subId > -1 and subId < 128:
                # Optimize for the common case
                octets = octets + (subId & 0x7f,)
            elif subId < 0:
                raise error.PyAsn1Error(
                    'Negative OID arc %s at %s' % (subId, value)
                )
            else:
                # Pack large Sub-Object IDs
                res = (subId & 0x7f,)
                subId = subId >> 7
                while subId > 0:
                    res = (0x80 | (subId & 0x7f),) + res
                    subId = subId >> 7 
                # Add packed Sub-Object ID to resulted Object ID
                octets += res

        return ints2octs(octets), 0

class RealEncoder(AbstractItemEncoder):
    supportIndefLenMode = 0
    binEncBase = 2 # set to None to choose encoding base automatically 
    def _dropFloatingPoint(self, m, encbase, e):
        ms, es = 1, 1
        if m < 0:
            ms = -1  # mantissa sign
        if e < 0:
            es = -1  # exponenta sign 
        m *= ms 
        if encbase == 8:
            m = m*2**(abs(e) % 3 * es)
            e = abs(e) // 3 * es
        elif encbase == 16:
            m = m*2**(abs(e) % 4 * es)
            e = abs(e) // 4 * es

        while 1:
            if int(m) != m:
                m *= encbase
                e -= 1
                continue
            break
        return ms, int(m), encbase, e

    def _chooseEncBase(self, value):
        m, b, e = value
        base = [2, 8, 16]
        if value.binEncBase in base:
            return self._dropFloatingPoint(m, value.binEncBase, e)
        elif self.binEncBase in base:
            return self._dropFloatingPoint(m, self.binEncBase, e)
        # auto choosing base 2/8/16 
        mantissa = [m, m, m]
        exponenta = [e, e, e]
        encbase = 2 
        e = float('inf')
        for i in range(3):
            sign, mantissa[i], base[i], exponenta[i] = \
                self._dropFloatingPoint(mantissa[i], base[i], exponenta[i])
            if abs(exponenta[i]) < abs(e) or \
               (abs(exponenta[i]) == abs(e) and mantissa[i] < m):
                e = exponenta[i]
                m = int(mantissa[i])
                encbase = base[i]
        return sign, m, encbase, e

    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        if value.isPlusInfinity():
            return int2oct(0x40), 0
        if value.isMinusInfinity():
            return int2oct(0x41), 0
        m, b, e = value
        if not m:
            return null, 0
        if b == 10:
            return str2octs('\x03%dE%s%d' % (m, e == 0 and '+' or '', e)), 0
        elif b == 2:
            fo = 0x80 # binary encoding
            ms, m, encbase, e = self._chooseEncBase(value)
            if ms < 0: # mantissa sign
                fo = fo | 0x40 # sign bit
            # exponenta & mantissa normalization
            if encbase == 2:
                while m & 0x1 == 0:
                    m >>= 1
                    e += 1
            elif encbase == 8:
                while m & 0x7 == 0:
                    m >>= 3
                    e += 1
                fo |= 0x10
            else: # encbase = 16
                while m & 0xf == 0:
                    m >>= 4
                    e += 1
                fo |= 0x20
            sf = 0 # scale factor
            while m & 0x1 == 0:
                m >>= 1
                sf += 1
            if sf > 3:
                raise error.PyAsn1Error('Scale factor overflow') # bug if raised
            fo |= sf << 2
            eo = null
            if e == 0 or e == -1:
                eo = int2oct(e&0xff)
            else: 
                while e not in (0, -1):
                    eo = int2oct(e&0xff) + eo
                    e >>= 8
                if e == 0 and eo and oct2int(eo[0]) & 0x80:
                    eo = int2oct(0) + eo
                if e == -1 and eo and not (oct2int(eo[0]) & 0x80):
                    eo = int2oct(0xff) + eo
            n = len(eo)
            if n > 0xff:
                raise error.PyAsn1Error('Real exponent overflow')
            if n == 1:
                pass
            elif n == 2:
                fo |= 1
            elif n == 3:
                fo |= 2
            else:
                fo |= 3
                eo = int2oct(n&0xff) + eo
            po = null
            while m:
                po = int2oct(m&0xff) + po
                m >>= 8
            substrate = int2oct(fo) + eo + po
            return substrate, 0
        else:
            raise error.PyAsn1Error('Prohibited Real base %s' % b)

class SequenceEncoder(AbstractItemEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        value.setDefaultComponents()
        value.verifySizeSpec()
        substrate = null; idx = len(value)
        while idx > 0:
            idx = idx - 1
            if value[idx] is None:  # Optional component
                continue
            component = value.getDefaultComponentByPosition(idx)
            if component is not None and component == value[idx]:
                continue
            substrate = encodeFun(
                value[idx], defMode, maxChunkSize
                ) + substrate
        return substrate, 1

class SequenceOfEncoder(AbstractItemEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        value.verifySizeSpec()
        substrate = null; idx = len(value)
        while idx > 0:
            idx = idx - 1
            substrate = encodeFun(
                value[idx], defMode, maxChunkSize
                ) + substrate
        return substrate, 1

class ChoiceEncoder(AbstractItemEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        return encodeFun(value.getComponent(), defMode, maxChunkSize), 1

class AnyEncoder(OctetStringEncoder):
    def encodeValue(self, encodeFun, value, defMode, maxChunkSize):
        return value.asOctets(), defMode == 0

tagMap = {
    eoo.endOfOctets.tagSet: EndOfOctetsEncoder(),
    univ.Boolean.tagSet: BooleanEncoder(),
    univ.Integer.tagSet: IntegerEncoder(),
    univ.BitString.tagSet: BitStringEncoder(),
    univ.OctetString.tagSet: OctetStringEncoder(),
    univ.Null.tagSet: NullEncoder(),
    univ.ObjectIdentifier.tagSet: ObjectIdentifierEncoder(),
    univ.Enumerated.tagSet: IntegerEncoder(),
    univ.Real.tagSet: RealEncoder(),
    # Sequence & Set have same tags as SequenceOf & SetOf
    univ.SequenceOf.tagSet: SequenceOfEncoder(),
    univ.SetOf.tagSet: SequenceOfEncoder(),
    univ.Choice.tagSet: ChoiceEncoder(),
    # character string types
    char.UTF8String.tagSet: OctetStringEncoder(),
    char.NumericString.tagSet: OctetStringEncoder(),
    char.PrintableString.tagSet: OctetStringEncoder(),
    char.TeletexString.tagSet: OctetStringEncoder(),
    char.VideotexString.tagSet: OctetStringEncoder(),
    char.IA5String.tagSet: OctetStringEncoder(),
    char.GraphicString.tagSet: OctetStringEncoder(),
    char.VisibleString.tagSet: OctetStringEncoder(),
    char.GeneralString.tagSet: OctetStringEncoder(),
    char.UniversalString.tagSet: OctetStringEncoder(),
    char.BMPString.tagSet: OctetStringEncoder(),
    # useful types
    useful.ObjectDescriptor.tagSet: OctetStringEncoder(),
    useful.GeneralizedTime.tagSet: OctetStringEncoder(),
    useful.UTCTime.tagSet: OctetStringEncoder()        
    }

# Type-to-codec map for ambiguous ASN.1 types
typeMap = {
    univ.Set.typeId: SequenceEncoder(),
    univ.SetOf.typeId: SequenceOfEncoder(),
    univ.Sequence.typeId: SequenceEncoder(),
    univ.SequenceOf.typeId: SequenceOfEncoder(),
    univ.Choice.typeId: ChoiceEncoder(),
    univ.Any.typeId: AnyEncoder()
    }

class Encoder:
    supportIndefLength = True
    def __init__(self, tagMap, typeMap={}):
        self.__tagMap = tagMap
        self.__typeMap = typeMap

    def __call__(self, value, defMode=True, maxChunkSize=0):
        if not defMode and not self.supportIndefLength:
            raise error.PyAsn1Error('Indefinite length encoding not supported by this codec')
        debug.logger & debug.flagEncoder and debug.logger('encoder called in %sdef mode, chunk size %s for type %s, value:\n%s' % (not defMode and 'in' or '', maxChunkSize, value.prettyPrintType(), value.prettyPrint()))
        tagSet = value.getTagSet()
        if len(tagSet) > 1:
            concreteEncoder = explicitlyTaggedItemEncoder
        else:
            if value.typeId is not None and value.typeId in self.__typeMap:
                concreteEncoder = self.__typeMap[value.typeId]
            elif tagSet in self.__tagMap:
                concreteEncoder = self.__tagMap[tagSet]
            else:
                tagSet = value.baseTagSet
                if tagSet in self.__tagMap:
                    concreteEncoder = self.__tagMap[tagSet]
                else:
                    raise Error('No encoder for %s' % (value,))
        debug.logger & debug.flagEncoder and debug.logger('using value codec %s chosen by %s' % (concreteEncoder.__class__.__name__, tagSet))
        substrate = concreteEncoder.encode(
            self, value, defMode, maxChunkSize
            )
        debug.logger & debug.flagEncoder and debug.logger('built %s octets of substrate: %s\nencoder completed' % (len(substrate), debug.hexdump(substrate)))
        return substrate

encode = Encoder(tagMap, typeMap)
