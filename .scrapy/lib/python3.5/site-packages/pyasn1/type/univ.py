# ASN.1 "universal" data types
import operator, sys, math
from pyasn1.type import base, tag, constraint, namedtype, namedval, tagmap
from pyasn1.codec.ber import eoo
from pyasn1.compat import octets
from pyasn1 import error

# "Simple" ASN.1 types (yet incomplete)

class Integer(base.AbstractSimpleAsn1Item):
    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatSimple, 0x02)
        )
    namedValues = namedval.NamedValues()
    def __init__(self, value=None, tagSet=None, subtypeSpec=None,
                 namedValues=None):
        if namedValues is None:
            self.__namedValues = self.namedValues
        else:
            self.__namedValues = namedValues
        base.AbstractSimpleAsn1Item.__init__(
            self, value, tagSet, subtypeSpec
            )

    def __repr__(self):
        if self.__namedValues is not self.namedValues:
            return '%s, %r)' % (base.AbstractSimpleAsn1Item.__repr__(self)[:-1], self.__namedValues)
        else:
            return base.AbstractSimpleAsn1Item.__repr__(self)

    def __and__(self, value): return self.clone(self._value & value)
    def __rand__(self, value): return self.clone(value & self._value)
    def __or__(self, value): return self.clone(self._value | value)
    def __ror__(self, value): return self.clone(value | self._value)
    def __xor__(self, value): return self.clone(self._value ^ value)
    def __rxor__(self, value): return self.clone(value ^ self._value)
    def __lshift__(self, value): return self.clone(self._value << value)
    def __rshift__(self, value): return self.clone(self._value >> value)

    def __add__(self, value): return self.clone(self._value + value)
    def __radd__(self, value): return self.clone(value + self._value)
    def __sub__(self, value): return self.clone(self._value - value)
    def __rsub__(self, value): return self.clone(value - self._value)
    def __mul__(self, value): return self.clone(self._value * value)
    def __rmul__(self, value): return self.clone(value * self._value)
    def __mod__(self, value): return self.clone(self._value % value)
    def __rmod__(self, value): return self.clone(value % self._value)
    def __pow__(self, value, modulo=None): return self.clone(pow(self._value, value, modulo))
    def __rpow__(self, value): return self.clone(pow(value, self._value))

    if sys.version_info[0] <= 2:
        def __div__(self, value):  return self.clone(self._value // value)
        def __rdiv__(self, value):  return self.clone(value // self._value)
    else:
        def __truediv__(self, value):  return self.clone(self._value / value)
        def __rtruediv__(self, value):  return self.clone(value / self._value)
        def __divmod__(self, value):  return self.clone(self._value // value)
        def __rdivmod__(self, value):  return self.clone(value // self._value)

        __hash__ = base.AbstractSimpleAsn1Item.__hash__

    def __int__(self): return int(self._value)
    if sys.version_info[0] <= 2:
        def __long__(self): return long(self._value)
    def __float__(self): return float(self._value)    
    def __abs__(self): return self.clone(abs(self._value))
    def __index__(self): return int(self._value)
    def __pos__(self): return self.clone(+self._value)
    def __neg__(self): return self.clone(-self._value)
    def __invert__(self): return self.clone(~self._value)
    def __round__(self, n=0):
        r = round(self._value, n)
        if n:
            return self.clone(r)
        else:
            return r
    def __floor__(self): return math.floor(self._value)
    def __ceil__(self): return math.ceil(self._value)
    if sys.version_info[0:2] > (2, 5):
        def __trunc__(self): return self.clone(math.trunc(self._value))

    def __lt__(self, value): return self._value < value
    def __le__(self, value): return self._value <= value
    def __eq__(self, value): return self._value == value
    def __ne__(self, value): return self._value != value
    def __gt__(self, value): return self._value > value
    def __ge__(self, value): return self._value >= value

    def prettyIn(self, value):
        if not isinstance(value, str):
            try:
                return int(value)
            except:
                raise error.PyAsn1Error(
                    'Can\'t coerce %r into integer: %s' % (value, sys.exc_info()[1])
                    )
        r = self.__namedValues.getValue(value)
        if r is not None:
            return r
        try:
            return int(value)
        except:
            raise error.PyAsn1Error(
                'Can\'t coerce %r into integer: %s' % (value, sys.exc_info()[1])
                )

    def prettyOut(self, value):
        r = self.__namedValues.getName(value)
        return r is None and str(value) or repr(r)

    def getNamedValues(self): return self.__namedValues

    def clone(self, value=None, tagSet=None, subtypeSpec=None,
              namedValues=None):
        if value is None and tagSet is None and subtypeSpec is None \
               and namedValues is None:
            return self
        if value is None:
            value = self._value
        if tagSet is None:
            tagSet = self._tagSet
        if subtypeSpec is None:
            subtypeSpec = self._subtypeSpec
        if namedValues is None:
            namedValues = self.__namedValues
        return self.__class__(value, tagSet, subtypeSpec, namedValues)

    def subtype(self, value=None, implicitTag=None, explicitTag=None,
                subtypeSpec=None, namedValues=None):
        if value is None:
            value = self._value
        if implicitTag is not None:
            tagSet = self._tagSet.tagImplicitly(implicitTag)
        elif explicitTag is not None:
            tagSet = self._tagSet.tagExplicitly(explicitTag)
        else:
            tagSet = self._tagSet
        if subtypeSpec is None:
            subtypeSpec = self._subtypeSpec
        else:
            subtypeSpec = subtypeSpec + self._subtypeSpec
        if namedValues is None:
            namedValues = self.__namedValues
        else:
            namedValues = namedValues + self.__namedValues
        return self.__class__(value, tagSet, subtypeSpec, namedValues)

class Boolean(Integer):
    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatSimple, 0x01),
        )
    subtypeSpec = Integer.subtypeSpec+constraint.SingleValueConstraint(0,1)
    namedValues = Integer.namedValues.clone(('False', 0), ('True', 1))

class BitString(base.AbstractSimpleAsn1Item):
    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatSimple, 0x03)
        )
    namedValues = namedval.NamedValues()
    def __init__(self, value=None, tagSet=None, subtypeSpec=None,
                 namedValues=None):
        if namedValues is None:
            self.__namedValues = self.namedValues
        else:
            self.__namedValues = namedValues
        base.AbstractSimpleAsn1Item.__init__(
            self, value, tagSet, subtypeSpec
            )

    def clone(self, value=None, tagSet=None, subtypeSpec=None,
              namedValues=None):
        if value is None and tagSet is None and subtypeSpec is None \
               and namedValues is None:
            return self
        if value is None:
            value = self._value
        if tagSet is None:
            tagSet = self._tagSet
        if subtypeSpec is None:
            subtypeSpec = self._subtypeSpec
        if namedValues is None:
            namedValues = self.__namedValues
        return self.__class__(value, tagSet, subtypeSpec, namedValues)

    def subtype(self, value=None, implicitTag=None, explicitTag=None,
                subtypeSpec=None, namedValues=None):
        if value is None:
            value = self._value
        if implicitTag is not None:
            tagSet = self._tagSet.tagImplicitly(implicitTag)
        elif explicitTag is not None:
            tagSet = self._tagSet.tagExplicitly(explicitTag)
        else:
            tagSet = self._tagSet
        if subtypeSpec is None:
            subtypeSpec = self._subtypeSpec
        else:
            subtypeSpec = subtypeSpec + self._subtypeSpec
        if namedValues is None:
            namedValues = self.__namedValues
        else:
            namedValues = namedValues + self.__namedValues
        return self.__class__(value, tagSet, subtypeSpec, namedValues)

    def __str__(self): return str(tuple(self))

    # Immutable sequence object protocol

    def __len__(self):
        if self._len is None:
            self._len = len(self._value)
        return self._len
    def __getitem__(self, i):
        if isinstance(i, slice):
            return self.clone(operator.getitem(self._value, i))
        else:
            return self._value[i]

    def __add__(self, value): return self.clone(self._value + value)
    def __radd__(self, value): return self.clone(value + self._value)
    def __mul__(self, value): return self.clone(self._value * value)
    def __rmul__(self, value): return self * value

    def prettyIn(self, value):
        r = []
        if not value:
            return ()
        elif isinstance(value, str):
            if value[0] == '\'':
                if value[-2:] == '\'B':
                    for v in value[1:-2]:
                        if v == '0':
                            r.append(0)
                        elif v == '1':
                            r.append(1)
                        else:
                            raise error.PyAsn1Error(
                                'Non-binary BIT STRING initializer %s' % (v,)
                                )
                    return tuple(r)
                elif value[-2:] == '\'H':
                    for v in value[1:-2]:
                        i = 4
                        v = int(v, 16)
                        while i:
                            i = i - 1
                            r.append((v>>i)&0x01)
                    return tuple(r)
                else:
                    raise error.PyAsn1Error(
                        'Bad BIT STRING value notation %s' % (value,)
                        )                
            else:
                for i in value.split(','):
                    j = self.__namedValues.getValue(i)
                    if j is None:
                        raise error.PyAsn1Error(
                            'Unknown bit identifier \'%s\'' % (i,)
                            )
                    if j >= len(r):
                        r.extend([0]*(j-len(r)+1))
                    r[j] = 1
                return tuple(r)
        elif isinstance(value, (tuple, list)):
            r = tuple(value)
            for b in r:
                if b and b != 1:
                    raise error.PyAsn1Error(
                        'Non-binary BitString initializer \'%s\'' % (r,)
                        )
            return r
        elif isinstance(value, BitString):
            return tuple(value)
        else:
            raise error.PyAsn1Error(
                'Bad BitString initializer type \'%s\'' % (value,)
                )

    def prettyOut(self, value):
        return '\"\'%s\'B\"' % ''.join([str(x) for x in value])

try:
    all
except NameError:  # Python 2.4
    def all(iterable):
        for element in iterable:
            if not element:
                return False
        return True

class OctetString(base.AbstractSimpleAsn1Item):
    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatSimple, 0x04)
        )
    defaultBinValue = defaultHexValue = base.noValue
    encoding = 'us-ascii'
    def __init__(self, value=None, tagSet=None, subtypeSpec=None,
                 encoding=None, binValue=None, hexValue=None):
        if encoding is None:
            self._encoding = self.encoding
        else:
            self._encoding = encoding
        if binValue is not None:
            value = self.fromBinaryString(binValue)
        if hexValue is not None:
            value = self.fromHexString(hexValue)
        if value is None or value is base.noValue:
            value = self.defaultHexValue
        if value is None or value is base.noValue:
            value = self.defaultBinValue
        self.__asNumbersCache = None
        base.AbstractSimpleAsn1Item.__init__(self, value, tagSet, subtypeSpec)

    def clone(self, value=None, tagSet=None, subtypeSpec=None,
              encoding=None, binValue=None, hexValue=None):
        if value is None and tagSet is None and subtypeSpec is None and \
               encoding is None and binValue is None and hexValue is None:
            return self
        if value is None and binValue is None and hexValue is None:
            value = self._value
        if tagSet is None:
            tagSet = self._tagSet
        if subtypeSpec is None:
            subtypeSpec = self._subtypeSpec
        if encoding is None:
            encoding = self._encoding
        return self.__class__(
            value, tagSet, subtypeSpec, encoding, binValue, hexValue
            )
   
    if sys.version_info[0] <= 2:
        def prettyIn(self, value):
            if isinstance(value, str):
                return value
            elif isinstance(value, unicode):
                try:
                    return value.encode(self._encoding)
                except (LookupError, UnicodeEncodeError):
                    raise error.PyAsn1Error(
                        'Can\'t encode string \'%s\' with \'%s\' codec' % (value, self._encoding)
                    )
            elif isinstance(value, (tuple, list)):
                try:
                    return ''.join([ chr(x) for x in value ])
                except ValueError:
                    raise error.PyAsn1Error(
                        'Bad OctetString initializer \'%s\'' % (value,)
                    )                
            else:
                return str(value)
    else:
        def prettyIn(self, value):
            if isinstance(value, bytes):
                return value
            elif isinstance(value, str):
                try:
                    return value.encode(self._encoding)
                except UnicodeEncodeError:
                    raise error.PyAsn1Error(
                        'Can\'t encode string \'%s\' with \'%s\' codec' % (value, self._encoding)
                    )
            elif isinstance(value, OctetString):
                return value.asOctets()
            elif isinstance(value, (tuple, list, map)):
                try:
                    return bytes(value)
                except ValueError:
                    raise error.PyAsn1Error(
                        'Bad OctetString initializer \'%s\'' % (value,)
                    )
            else:
                try:
                    return str(value).encode(self._encoding)
                except UnicodeEncodeError:
                    raise error.PyAsn1Error(
                        'Can\'t encode string \'%s\' with \'%s\' codec' % (value, self._encoding)
                    )
                        

    def fromBinaryString(self, value):
        bitNo = 8; byte = 0; r = ()
        for v in value:
            if bitNo:
                bitNo = bitNo - 1
            else:
                bitNo = 7
                r = r + (byte,)
                byte = 0
            if v == '0':
                v = 0
            elif v == '1':
                v = 1
            else:
                raise error.PyAsn1Error(
                    'Non-binary OCTET STRING initializer %s' % (v,)
                    )
            byte = byte | (v << bitNo)
        return octets.ints2octs(r + (byte,))
        
    def fromHexString(self, value):            
        r = p = ()
        for v in value:
            if p:
                r = r + (int(p+v, 16),)
                p = ()
            else:
                p = v
        if p:
            r = r + (int(p+'0', 16),)
        return octets.ints2octs(r)

    def prettyOut(self, value):
        if sys.version_info[0] <= 2:
            numbers = tuple(( ord(x) for x in value ))
        else:
            numbers = tuple(value)
        if all(x >= 32 and x <= 126 for x in numbers):
            return str(value)
        else:
            return '0x' + ''.join(( '%.2x' % x for x in numbers ))

    def __repr__(self):
        r = []
        doHex = False
        if self._value is not self.defaultValue:
            for x in self.asNumbers():
                if x < 32 or x > 126:
                    doHex = True
                    break
            if not doHex:
                r.append('%r' % (self._value,))
        if self._tagSet is not self.tagSet:
            r.append('tagSet=%r' % (self._tagSet,))
        if self._subtypeSpec is not self.subtypeSpec:
            r.append('subtypeSpec=%r' % (self._subtypeSpec,))
        if self.encoding is not self._encoding:
            r.append('encoding=%r' % (self._encoding,))
        if doHex:
            r.append('hexValue=%r' % ''.join([ '%.2x' % x for x in self.asNumbers() ]))
        return '%s(%s)' % (self.__class__.__name__, ', '.join(r))
                                
    if sys.version_info[0] <= 2:
        def __str__(self): return str(self._value)
        def __unicode__(self):
            return self._value.decode(self._encoding, 'ignore')
        def asOctets(self): return self._value
        def asNumbers(self):
            if self.__asNumbersCache is None:
                self.__asNumbersCache = tuple([ ord(x) for x in self._value ])
            return self.__asNumbersCache
    else:
        def __str__(self): return self._value.decode(self._encoding, 'ignore')
        def __bytes__(self): return self._value
        def asOctets(self): return self._value
        def asNumbers(self):
            if self.__asNumbersCache is None:
                self.__asNumbersCache = tuple(self._value)
            return self.__asNumbersCache
 
    # Immutable sequence object protocol
    
    def __len__(self):
        if self._len is None:
            self._len = len(self._value)
        return self._len
    def __getitem__(self, i):
        if isinstance(i, slice):
            return self.clone(operator.getitem(self._value, i))
        else:
            return self._value[i]

    def __add__(self, value): return self.clone(self._value + self.prettyIn(value))
    def __radd__(self, value): return self.clone(self.prettyIn(value) + self._value)
    def __mul__(self, value): return self.clone(self._value * value)
    def __rmul__(self, value): return self * value
    def __int__(self): return int(self._value)
    def __float__(self): return float(self._value)
    
class Null(OctetString):
    defaultValue = ''.encode()  # This is tightly constrained
    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatSimple, 0x05)
        )
    subtypeSpec = OctetString.subtypeSpec+constraint.SingleValueConstraint(''.encode())
    
if sys.version_info[0] <= 2:
    intTypes = (int, long)
else:
    intTypes = (int,)

numericTypes = intTypes + (float,)

class ObjectIdentifier(base.AbstractSimpleAsn1Item):
    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatSimple, 0x06)
        )
    def __add__(self, other): return self.clone(self._value + other)
    def __radd__(self, other): return self.clone(other + self._value)

    def asTuple(self): return self._value
    
    # Sequence object protocol
    
    def __len__(self):
        if self._len is None:
            self._len = len(self._value)
        return self._len
    def __getitem__(self, i):
        if isinstance(i, slice):
            return self.clone(
                operator.getitem(self._value, i)
                )
        else:
            return self._value[i]

    def __str__(self): return self.prettyPrint()
    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.prettyPrint())

    def index(self, suboid): return self._value.index(suboid)

    def isPrefixOf(self, value):
        """Returns true if argument OID resides deeper in the OID tree"""
        l = len(self)
        if l <= len(value):
            if self._value[:l] == value[:l]:
                return 1
        return 0

    def prettyIn(self, value):
        """Dotted -> tuple of numerics OID converter"""
        if isinstance(value, tuple):
            pass
        elif isinstance(value, ObjectIdentifier):
            return tuple(value)        
        elif octets.isStringType(value):
            r = []
            for element in [ x for x in value.split('.') if x != '' ]:
                try:
                    r.append(int(element, 0))
                except ValueError:
                    raise error.PyAsn1Error(
                        'Malformed Object ID %s at %s: %s' %
                        (str(value), self.__class__.__name__, sys.exc_info()[1])
                        )
            value = tuple(r)
        else:
            try:
                value = tuple(value)
            except TypeError:
                raise error.PyAsn1Error(
                        'Malformed Object ID %s at %s: %s' %
                        (str(value), self.__class__.__name__,sys.exc_info()[1])
                        )

        for x in value:
            if not isinstance(x, intTypes) or x < 0:
                raise error.PyAsn1Error(
                    'Invalid sub-ID in %s at %s' % (value, self.__class__.__name__)
                    )
    
        return value

    def prettyOut(self, value): return '.'.join([ str(x) for x in value ])
    
class Real(base.AbstractSimpleAsn1Item):
    binEncBase = None # binEncBase = 16 is recommended for large numbers
    try:
        _plusInf = float('inf')
        _minusInf = float('-inf')
        _inf = (_plusInf, _minusInf)
    except ValueError:
        # Infinity support is platform and Python dependent
        _plusInf = _minusInf = None
        _inf = ()

    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatSimple, 0x09)
        )

    def __normalizeBase10(self, value):
        m, b, e = value
        while m and m % 10 == 0:
            m = m / 10
            e = e + 1
        return m, b, e

    def prettyIn(self, value):
        if isinstance(value, tuple) and len(value) == 3:
            if not isinstance(value[0], numericTypes) or \
                    not isinstance(value[1], intTypes) or \
                    not isinstance(value[2], intTypes):
                raise error.PyAsn1Error('Lame Real value syntax: %s' % (value,))
            if isinstance(value[0], float) and \
                self._inf and value[0] in self._inf:
                return value[0]
            if value[1] not in (2, 10):
                raise error.PyAsn1Error(
                    'Prohibited base for Real value: %s' % (value[1],)
                    )
            if value[1] == 10:
                value = self.__normalizeBase10(value)
            return value
        elif isinstance(value, intTypes):
            return self.__normalizeBase10((value, 10, 0))
        elif isinstance(value, (str, float)):
            if isinstance(value, str):
                try:
                    value = float(value)
                except ValueError:
                    raise error.PyAsn1Error(
                        'Bad real value syntax: %s' % (value,)
                    )
            if self._inf and value in self._inf:
                return value
            else:
                e = 0
                while int(value) != value:
                    value = value * 10
                    e = e - 1
                return self.__normalizeBase10((int(value), 10, e))
        elif isinstance(value, Real):
            return tuple(value)
        raise error.PyAsn1Error(
            'Bad real value syntax: %s' % (value,)
            )
        
    def prettyOut(self, value):
        if value in self._inf:
            return '\'%s\'' % value
        else:
            return str(value)

    def prettyPrint(self, scope=0):
        if self.isInfinity():
            return self.prettyOut(self._value)
        else:
            return str(float(self))

    def isPlusInfinity(self): return self._value == self._plusInf
    def isMinusInfinity(self): return self._value == self._minusInf
    def isInfinity(self): return self._value in self._inf
    
    def __str__(self): return str(float(self))
    
    def __add__(self, value): return self.clone(float(self) + value)
    def __radd__(self, value): return self + value
    def __mul__(self, value): return self.clone(float(self) * value)
    def __rmul__(self, value): return self * value
    def __sub__(self, value): return self.clone(float(self) - value)
    def __rsub__(self, value): return self.clone(value - float(self))
    def __mod__(self, value): return self.clone(float(self) % value)
    def __rmod__(self, value): return self.clone(value % float(self))
    def __pow__(self, value, modulo=None): return self.clone(pow(float(self), value, modulo))
    def __rpow__(self, value): return self.clone(pow(value, float(self)))

    if sys.version_info[0] <= 2:
        def __div__(self, value): return self.clone(float(self) / value)
        def __rdiv__(self, value): return self.clone(value / float(self))
    else:
        def __truediv__(self, value): return self.clone(float(self) / value)
        def __rtruediv__(self, value): return self.clone(value / float(self))
        def __divmod__(self, value): return self.clone(float(self) // value)
        def __rdivmod__(self, value): return self.clone(value // float(self))

    def __int__(self): return int(float(self))
    if sys.version_info[0] <= 2:
        def __long__(self): return long(float(self))
    def __float__(self):
        if self._value in self._inf:
            return self._value
        else:
            return float(
                self._value[0] * pow(self._value[1], self._value[2])
            )
    def __abs__(self): return self.clone(abs(float(self)))
    def __pos__(self): return self.clone(+float(self))
    def __neg__(self): return self.clone(-float(self))
    def __round__(self, n=0):
        r = round(float(self), n)
        if n:
            return self.clone(r)
        else:
            return r
    def __floor__(self): return self.clone(math.floor(float(self)))
    def __ceil__(self): return self.clone(math.ceil(float(self)))
    if sys.version_info[0:2] > (2, 5):
        def __trunc__(self): return self.clone(math.trunc(float(self)))

    def __lt__(self, value): return float(self) < value
    def __le__(self, value): return float(self) <= value
    def __eq__(self, value): return float(self) == value
    def __ne__(self, value): return float(self) != value
    def __gt__(self, value): return float(self) > value
    def __ge__(self, value): return float(self) >= value

    if sys.version_info[0] <= 2:
        def __nonzero__(self): return bool(float(self))
    else:
        def __bool__(self): return bool(float(self))
        __hash__ = base.AbstractSimpleAsn1Item.__hash__

    def __getitem__(self, idx):
        if self._value in self._inf:
            raise error.PyAsn1Error('Invalid infinite value operation')
        else:
            return self._value[idx]
    
class Enumerated(Integer):
    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatSimple, 0x0A)
        )

# "Structured" ASN.1 types

class SetOf(base.AbstractConstructedAsn1Item):
    componentType = None
    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatConstructed, 0x11)
        )
    typeId = 1
    strictConstraints = False

    def _cloneComponentValues(self, myClone, cloneValueFlag):
        idx = 0; l = len(self._componentValues)
        while idx < l:
            c = self._componentValues[idx]
            if c is not None:
                if isinstance(c, base.AbstractConstructedAsn1Item):
                    myClone.setComponentByPosition(
                        idx, c.clone(cloneValueFlag=cloneValueFlag)
                        )
                else:
                    myClone.setComponentByPosition(idx, c.clone())
            idx = idx + 1
        
    def _verifyComponent(self, idx, value):
        t = self._componentType
        if t is None:
            return
        if not t.isSameTypeWith(value,matchConstraints=self.strictConstraints):
            raise error.PyAsn1Error('Component value is tag-incompatible: %r vs %r' % (value, t))
        if self.strictConstraints and \
                not t.isSuperTypeOf(value, matchTags=False):
            raise error.PyAsn1Error('Component value is constraints-incompatible: %r vs %r' % (value, t))

    def getComponentByPosition(self, idx): return self._componentValues[idx]
    def setComponentByPosition(self, idx, value=None, verifyConstraints=True):
        l = len(self._componentValues)
        if idx >= l:
            self._componentValues = self._componentValues + (idx-l+1)*[None]
        if value is None:
            if self._componentValues[idx] is None:
                if self._componentType is None:
                    raise error.PyAsn1Error('Component type not defined')
                self._componentValues[idx] = self._componentType.clone()
                self._componentValuesSet = self._componentValuesSet + 1
            return self
        elif not isinstance(value, base.Asn1Item):
            if self._componentType is None:
                raise error.PyAsn1Error('Component type not defined')
            if isinstance(self._componentType, base.AbstractSimpleAsn1Item):
                value = self._componentType.clone(value=value)
            else:
                raise error.PyAsn1Error('Instance value required')
        if verifyConstraints:
            if self._componentType is not None:
                self._verifyComponent(idx, value)
            self._verifySubtypeSpec(value, idx)            
        if self._componentValues[idx] is None:
            self._componentValuesSet = self._componentValuesSet + 1
        self._componentValues[idx] = value
        return self

    def getComponentTagMap(self):
        if self._componentType is not None:
            return self._componentType.getTagMap()

    def prettyPrint(self, scope=0):
        scope = scope + 1
        r = self.__class__.__name__ + ':\n'        
        for idx in range(len(self._componentValues)):
            r = r + ' '*scope
            if self._componentValues[idx] is None:
                r = r + '<empty>'
            else:
                r = r + self._componentValues[idx].prettyPrint(scope)
        return r

    def prettyPrintType(self, scope=0):
        scope = scope + 1
        r = '%s -> %s {\n' % (self.getTagSet(), self.__class__.__name__)
        if self._componentType is not None:
            r = r + ' '*scope
            r = r + self._componentType.prettyPrintType(scope)
        return r + '\n' + ' '*(scope-1) + '}'

class SequenceOf(SetOf):
    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatConstructed, 0x10)
        )
    typeId = 2

class SequenceAndSetBase(base.AbstractConstructedAsn1Item):
    componentType = namedtype.NamedTypes()
    strictConstraints = False
    def __init__(self, componentType=None, tagSet=None,
                 subtypeSpec=None, sizeSpec=None):
        if componentType is None:
            componentType = self.componentType
        base.AbstractConstructedAsn1Item.__init__(
            self, componentType.clone(), tagSet, subtypeSpec, sizeSpec
        )
        self._componentTypeLen = len(self._componentType)

    def __getitem__(self, idx):
        if isinstance(idx, str):
            return self.getComponentByName(idx)
        else:
            return base.AbstractConstructedAsn1Item.__getitem__(self, idx)

    def __setitem__(self, idx, value):
        if isinstance(idx, str):
            self.setComponentByName(idx, value)
        else:
            base.AbstractConstructedAsn1Item.__setitem__(self, idx, value)
        
    def _cloneComponentValues(self, myClone, cloneValueFlag):
        idx = 0; l = len(self._componentValues)
        while idx < l:
            c = self._componentValues[idx]
            if c is not None:
                if isinstance(c, base.AbstractConstructedAsn1Item):
                    myClone.setComponentByPosition(
                        idx, c.clone(cloneValueFlag=cloneValueFlag)
                        )
                else:
                    myClone.setComponentByPosition(idx, c.clone())
            idx = idx + 1

    def _verifyComponent(self, idx, value):
        if idx >= self._componentTypeLen:
            raise error.PyAsn1Error(
                'Component type error out of range'
                )
        t = self._componentType[idx].getType()
        if not t.isSameTypeWith(value,matchConstraints=self.strictConstraints):
            raise error.PyAsn1Error('Component value is tag-incompatible: %r vs %r' % (value, t))
        if self.strictConstraints and \
                not t.isSuperTypeOf(value, matchTags=False):
            raise error.PyAsn1Error('Component value is constraints-incompatible: %r vs %r' % (value, t))

    def getComponentByName(self, name):
        return self.getComponentByPosition(
            self._componentType.getPositionByName(name)
            )
    def setComponentByName(self, name, value=None, verifyConstraints=True):
        return self.setComponentByPosition(
            self._componentType.getPositionByName(name),value,verifyConstraints
        )

    def getComponentByPosition(self, idx):
        try:
            return self._componentValues[idx]
        except IndexError:
            if idx < self._componentTypeLen:
                return
            raise
    def setComponentByPosition(self, idx, value=None,
                               verifyConstraints=True,
                               exactTypes=False,
                               matchTags=True,
                               matchConstraints=True):
        l = len(self._componentValues)
        if idx >= l:
            self._componentValues = self._componentValues + (idx-l+1)*[None]
        if value is None:
            if self._componentValues[idx] is None:
                self._componentValues[idx] = self._componentType.getTypeByPosition(idx).clone()
                self._componentValuesSet = self._componentValuesSet + 1
            return self
        elif not isinstance(value, base.Asn1Item):
            t = self._componentType.getTypeByPosition(idx)
            if isinstance(t, base.AbstractSimpleAsn1Item):
                value = t.clone(value=value)
            else:
                raise error.PyAsn1Error('Instance value required')
        if verifyConstraints:
            if self._componentTypeLen:
                self._verifyComponent(idx, value)
            self._verifySubtypeSpec(value, idx)            
        if self._componentValues[idx] is None:
            self._componentValuesSet = self._componentValuesSet + 1
        self._componentValues[idx] = value
        return self

    def getNameByPosition(self, idx):
        if self._componentTypeLen:
            return self._componentType.getNameByPosition(idx)

    def getDefaultComponentByPosition(self, idx):
        if self._componentTypeLen and self._componentType[idx].isDefaulted:
            return self._componentType[idx].getType()

    def getComponentType(self):
        if self._componentTypeLen:
            return self._componentType
    
    def setDefaultComponents(self):
        if self._componentTypeLen == self._componentValuesSet:
            return
        idx = self._componentTypeLen
        while idx:
            idx = idx - 1
            if self._componentType[idx].isDefaulted:
                if self.getComponentByPosition(idx) is None:
                    self.setComponentByPosition(idx)
            elif not self._componentType[idx].isOptional:
                if self.getComponentByPosition(idx) is None:
                    raise error.PyAsn1Error(
                        'Uninitialized component #%s at %r' % (idx, self)
                        )

    def prettyPrint(self, scope=0):
        scope = scope + 1
        r = self.__class__.__name__ + ':\n'
        for idx in range(len(self._componentValues)):
            if self._componentValues[idx] is not None:
                r = r + ' '*scope
                componentType = self.getComponentType()
                if componentType is None:
                    r = r + '<no-name>'
                else:
                    r = r + componentType.getNameByPosition(idx)
                r = '%s=%s\n' % (
                    r, self._componentValues[idx].prettyPrint(scope)
                    )
        return r

    def prettyPrintType(self, scope=0):
        scope = scope + 1
        r = '%s -> %s {\n' % (self.getTagSet(), self.__class__.__name__)
        for idx in range(len(self.componentType)):
            r = r + ' '*scope
            r = r + '"%s"' % self.componentType.getNameByPosition(idx)
            r = '%s = %s\n' % (
                r, self._componentType.getTypeByPosition(idx).prettyPrintType(scope)
            )
        return r + '\n' + ' '*(scope-1) + '}'

class Sequence(SequenceAndSetBase):
    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatConstructed, 0x10)
        )
    typeId = 3

    def getComponentTagMapNearPosition(self, idx):
        if self._componentType:
            return self._componentType.getTagMapNearPosition(idx)
    
    def getComponentPositionNearType(self, tagSet, idx):
        if self._componentType:
            return self._componentType.getPositionNearType(tagSet, idx)
        else:
            return idx
    
class Set(SequenceAndSetBase):
    tagSet = baseTagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatConstructed, 0x11)
        )
    typeId = 4

    def getComponent(self, innerFlag=0): return self
    
    def getComponentByType(self, tagSet, innerFlag=0):
        c = self.getComponentByPosition(
            self._componentType.getPositionByType(tagSet)
            )
        if innerFlag and isinstance(c, Set):
            # get inner component by inner tagSet
            return c.getComponent(1)
        else:
            # get outer component by inner tagSet
            return c
        
    def setComponentByType(self, tagSet, value=None, innerFlag=0,
                           verifyConstraints=True):
        idx = self._componentType.getPositionByType(tagSet)
        t = self._componentType.getTypeByPosition(idx)
        if innerFlag:  # set inner component by inner tagSet
            if t.getTagSet():
                return self.setComponentByPosition(
                    idx, value, verifyConstraints
                )
            else:
                t = self.setComponentByPosition(idx).getComponentByPosition(idx)
                return t.setComponentByType(
                    tagSet, value, innerFlag, verifyConstraints
                )
        else:  # set outer component by inner tagSet
            return self.setComponentByPosition(
                idx, value, verifyConstraints
            )
            
    def getComponentTagMap(self):
        if self._componentType:
            return self._componentType.getTagMap(True)

    def getComponentPositionByType(self, tagSet):
        if self._componentType:
            return self._componentType.getPositionByType(tagSet)

class Choice(Set):
    tagSet = baseTagSet = tag.TagSet()  # untagged
    sizeSpec = constraint.ConstraintsIntersection(
        constraint.ValueSizeConstraint(1, 1)
        )
    typeId = 5
    _currentIdx = None

    def __eq__(self, other):
        if self._componentValues:
            return self._componentValues[self._currentIdx] == other
        return NotImplemented
    def __ne__(self, other):
        if self._componentValues:
            return self._componentValues[self._currentIdx] != other
        return NotImplemented
    def __lt__(self, other):
        if self._componentValues:
            return self._componentValues[self._currentIdx] < other
        return NotImplemented
    def __le__(self, other):
        if self._componentValues:
            return self._componentValues[self._currentIdx] <= other
        return NotImplemented
    def __gt__(self, other):
        if self._componentValues:
            return self._componentValues[self._currentIdx] > other
        return NotImplemented
    def __ge__(self, other):
        if self._componentValues:
            return self._componentValues[self._currentIdx] >= other
        return NotImplemented
    if sys.version_info[0] <= 2:
        def __nonzero__(self): return bool(self._componentValues)
    else:
        def __bool__(self): return bool(self._componentValues)

    def __len__(self): return self._currentIdx is not None and 1 or 0
    
    def verifySizeSpec(self):
        if self._currentIdx is None:
            raise error.PyAsn1Error('Component not chosen')
        else:
            self._sizeSpec(' ')

    def _cloneComponentValues(self, myClone, cloneValueFlag):
        try:
            c = self.getComponent()
        except error.PyAsn1Error:
            pass
        else:
            if isinstance(c, Choice):
                tagSet = c.getEffectiveTagSet()
            else:
                tagSet = c.getTagSet()
            if isinstance(c, base.AbstractConstructedAsn1Item):
                myClone.setComponentByType(
                    tagSet, c.clone(cloneValueFlag=cloneValueFlag)
                    )
            else:
                myClone.setComponentByType(tagSet, c.clone())

    def setComponentByPosition(self, idx, value=None, verifyConstraints=True):
        l = len(self._componentValues)
        if idx >= l:
            self._componentValues = self._componentValues + (idx-l+1)*[None]
        if self._currentIdx is not None:
            self._componentValues[self._currentIdx] = None
        if value is None:
            if self._componentValues[idx] is None:
                self._componentValues[idx] = self._componentType.getTypeByPosition(idx).clone()
                self._componentValuesSet = 1
                self._currentIdx = idx
            return self
        elif not isinstance(value, base.Asn1Item):
            value = self._componentType.getTypeByPosition(idx).clone(
                value=value
                )
        if verifyConstraints:
            if self._componentTypeLen:
                self._verifyComponent(idx, value)
            self._verifySubtypeSpec(value, idx)            
        self._componentValues[idx] = value
        self._currentIdx = idx
        self._componentValuesSet = 1
        return self

    def getMinTagSet(self):
        if self._tagSet:
            return self._tagSet
        else:
            return self._componentType.genMinTagSet()

    def getEffectiveTagSet(self):
        if self._tagSet:
            return self._tagSet
        else:
            c = self.getComponent()
            if isinstance(c, Choice):
                return c.getEffectiveTagSet()
            else:
                return c.getTagSet()

    def getTagMap(self):
        if self._tagSet:
            return Set.getTagMap(self)
        else:
            return Set.getComponentTagMap(self)

    def getComponent(self, innerFlag=0):
        if self._currentIdx is None:
            raise error.PyAsn1Error('Component not chosen')
        else:
            c = self._componentValues[self._currentIdx]
            if innerFlag and isinstance(c, Choice):
                return c.getComponent(innerFlag)
            else:
                return c

    def getName(self, innerFlag=0):
        if self._currentIdx is None:
            raise error.PyAsn1Error('Component not chosen')
        else:
            if innerFlag:
                c = self._componentValues[self._currentIdx]
                if isinstance(c, Choice):
                    return c.getName(innerFlag)
            return self._componentType.getNameByPosition(self._currentIdx)

    def setDefaultComponents(self): pass

class Any(OctetString):
    tagSet = baseTagSet = tag.TagSet()  # untagged
    typeId = 6

    def getTagMap(self):
        return tagmap.TagMap(
            { self.getTagSet(): self },
            { eoo.endOfOctets.getTagSet(): eoo.endOfOctets },
            self
            )

# XXX
# coercion rules?
