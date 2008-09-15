# this is a ctypes-based python wrapper for mozilla spidermonkey

# ************************************************************************
# This is an alpha release.  It has many known faults, and interfaces will
# change.

# Note that code listed with JavaScript error messages can be the WRONG
# CODE!  Don't take it seriously.
# ************************************************************************

# spidermonkey 0.0.2a: Python / JavaScript bridge.
# Copyright (C) 2003  John J. Lee <jjl@pobox.com>
# Copyright (C) 2006  Leonard Ritter <paniq@paniq.org>

# Partly derived from Spidermonkey.xs, Copyright (C) 2001, Claes
#  Jacobsson, All Rights Reserved (Perl Artistic License).
# Partly derived from PerlConnect (part of spidermonkey) Copyright (C)
#  1998 Netscape Communications Corporation (GPL).
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA


# Security constraints:
#  Can't add attributes to Python objects.
#  *Can* add JS properties to JS proxies of Python objects, as long as it
#   won't hide a Python attribute of the same name.
#  Can't assign to Python methods.
#  Can't access any Python attribute starting with "_".
#  Also, bound Python objects can of course implement their own
#   protection, as the Window class does.

# XXX
# Does JS expect some exceptions on reading a non-existent property?
#  Currently, this code has the effect of returning undef in that case,
#  which seems odd.  Look in O'Reilly book / spidermonkey code.
# Exception propagation.  IIRC, I'm waiting for except * to be fixed in
#  Pyrex.
# Code listings on JS errors are wrong.
# Review code
#  Replace Object with Py_INCREF and just keeping python object in JS
#   object (need to think first, though, to check this will work).
#  API call return values and bad function arguments!
#  Memory management.
#   Check strcpy's, malloc's / free's / Destroy*'s.
#   Look for and fix any memory leaks.
#  To prevent people crashing module, would be nice to make some things
#   private.  Ask on Pyrex list.
#  Make use of JS API security model?
#  GC issues (see spidermonkey GC tips page).
#  Threading issues (see GC tips again).

from ctypes import *

# predefines
size_t = c_ulong
_IO_FILE = c_ulong
__ssize_t = c_int
ssize_t = c_uint

JSWord = c_long
jsword = JSWord
jsval = jsword

class JSObject(Structure):
	_fields_ = [
	]
class ObjectJSVALUnion(Union):
	_fields_ = [
		('jsval', jsval),
		('obj', POINTER(JSObject)),
	]

def OBJECT_TO_JSVAL(obj):
	objectJSVALUnion = ObjectJSVALUnion()
	objectJSVALUnion.obj = obj
	return objectJSVALUnion.jsval

# defines
EOF = (-1)
FILENAME_MAX = 4096
FOPEN_MAX = 16
def JS_BIT(n):
	return 1 << n
def JS_BITMASK(n):
	return JS_BIT(n) - 1
def JSVAL_SETTAG(v,t):
	if type(v) == c_long:
		v = v.value
	return v | t
def BOOLEAN_TO_JSVAL(b):
	return JSVAL_SETTAG(b << JSVAL_TAGBITS, JSVAL_BOOLEAN)
def JSVAL_INT_POW2(n):
	return 1 << n
def INT_TO_JSVAL(i):
	return (i << 1) | JSVAL_INT
def JSVAL_IS_PRIMITIVE(v):
	return ((not JSVAL_IS_OBJECT(v)) or JSVAL_IS_NULL(v))
def JSVAL_IS_OBJECT(v):
	return (JSVAL_TAG(v) == JSVAL_OBJECT)
def JSVAL_IS_INT(v):
	if type(v) == c_long:
		v = v.value
	return ((v & JSVAL_INT) and (v != JSVAL_VOID))
def JSVAL_TO_INT(v):
	if type(v) == c_long:
		v = v.value
	return v >> 1
def JSVAL_IS_DOUBLE(v):
	return (JSVAL_TAG(v) == JSVAL_DOUBLE)
def JSVAL_TO_DOUBLE(v):
	return cast(JSVAL_TO_GCTHING(v),POINTER(jsdouble))
def JSVAL_IS_BOOLEAN(v):
	return (JSVAL_TAG(v) == JSVAL_BOOLEAN)
def JSVAL_TO_BOOLEAN(v):
	if type(v) == c_long:
		v = v.value
	return v >> JSVAL_TAGBITS
def JSVAL_IS_STRING(v):
	return JSVAL_TAG(v) == JSVAL_STRING
def JSVAL_TO_STRING(v):
	return cast(JSVAL_TO_GCTHING(v),POINTER(JSString))
def STRING_TO_JSVAL(str):
	return JSVAL_SETTAG(cast(addressof(str),POINTER(jsval)).contents, JSVAL_STRING)
def DOUBLE_TO_JSVAL(dp):
	return JSVAL_SETTAG(cast(addressof(dp),POINTER(jsval)).contents, JSVAL_DOUBLE)
def JSVAL_TO_GCTHING(v):
	return cast(JSVAL_CLRTAG(v),c_void_p)
def JSVAL_CLRTAG(v):
	if type(v) == c_long:
		v = v.value
	return v & (~JSVAL_TAGMASK)
def JSVAL_TAG(v):
	if type(v) == c_long:
		v = v.value
	return v & JSVAL_TAGMASK
def JSVAL_IS_NULL(v):
	if type(v) == c_long:
		v = v.value
	return v == JSVAL_NULL
def JSVAL_IS_VOID(v):
	if type(v) == c_long:
		v = v.value
	return v == JSVAL_VOID
def JSVAL_TO_OBJECT(v):
	return cast(JSVAL_TO_GCTHING(v), POINTER(JSObject))
JSCLASS_HAS_PRIVATE = (1<<0)
JSCLASS_NEW_ENUMERATE = (1<<1)
JSCLASS_NEW_RESOLVE = (1<<2)
JSCLASS_NEW_RESOLVE_GETS_START = (1<<5)
JSCLASS_NO_OPTIONAL_MEMBERS = 0,0,0,0,0,0,0,0
JSCLASS_PRIVATE_IS_NSISUPPORTS = (1<<3)
JSCLASS_RESERVED_SLOTS_WIDTH = 8
JSCLASS_RESERVED_SLOTS_MASK = JS_BITMASK(JSCLASS_RESERVED_SLOTS_WIDTH)
JSCLASS_RESERVED_SLOTS_SHIFT = 8
JSCLASS_SHARE_ALL_PROPERTIES = (1<<4)
JSFUN_BOUND_METHOD = 0x40
JSFUN_FLAGS_MASK = 0xf8
JSFUN_HEAVYWEIGHT = 0x80
JSFUN_LAMBDA = 0x08
JSOPTION_COMPILE_N_GO = JS_BIT(4)
JSOPTION_PRIVATE_IS_NSISUPPORTS = JS_BIT(3)
JSOPTION_STRICT = JS_BIT(0)
JSOPTION_VAROBJFIX = JS_BIT(2)
JSOPTION_WERROR = JS_BIT(1)
JSPROP_ENUMERATE = 0x01
JSPROP_EXPORTED = 0x08
JSPROP_GETTER = 0x10
JSPROP_INDEX = 0x80
JSPROP_PERMANENT = 0x04
JSPROP_READONLY = 0x02
JSPROP_SETTER = 0x20
JSPROP_SHARED = 0x40
JSREG_FOLD = 0x01
JSREG_GLOB = 0x02
JSREG_MULTILINE = 0x04
JSREPORT_ERROR = 0x0
JSREPORT_EXCEPTION = 0x2
JSREPORT_STRICT = 0x4
JSREPORT_WARNING = 0x1
JSRESOLVE_ASSIGNING = 0x02
JSRESOLVE_QUALIFIED = 0x01
JSVAL_TAGBITS = 3
JSVAL_ALIGN = JS_BIT(JSVAL_TAGBITS)
JSVAL_BOOLEAN = 0x6
JSVAL_DOUBLE = 0x2
JS_FALSE = 0
JSVAL_FALSE = BOOLEAN_TO_JSVAL(JS_FALSE)
JSVAL_INT = 0x1
JSVAL_INT_BITS = 31
JSVAL_INT_MAX = (JSVAL_INT_POW2(30) - 1)
JSVAL_INT_MIN = (1 - JSVAL_INT_POW2(30))
JSVAL_NULL = 0
JSVAL_OBJECT = 0x0
JSVAL_ONE = INT_TO_JSVAL(1)
JSVAL_STRING = 0x4
JSVAL_TAGMASK = JS_BITMASK(JSVAL_TAGBITS)
JS_TRUE = 1
JSVAL_TRUE = BOOLEAN_TO_JSVAL(JS_TRUE)
JSVAL_VOID = INT_TO_JSVAL(0 - JSVAL_INT_POW2(30))
JSVAL_ZERO = INT_TO_JSVAL(0)
JS_DONT_PRETTY_PRINT = (0x8000)
JS_MAP_GCROOT_NEXT = 0
JS_MAP_GCROOT_REMOVE = 2
JS_MAP_GCROOT_STOP = 1
SEEK_CUR = 1
SEEK_END = 2
SEEK_SET = 0
TMP_MAX = 238328

# using file "/usr/include/smjs/jslong.h"
# using file "/usr/include/smjs/jscompat.h"
# using file "/usr/include/smjs/jspubtd.h"
# using file "/usr/include/smjs/jsapi.h"
JSUintn = c_uint

uintN = JSUintn

class JSErrorFormatString(Structure):
	_fields_ = [
		('format', c_char_p),
		('argCount', uintN),
	]

JSErrorFormatString = JSErrorFormatString

class JSContext(Structure):
	_fields_ = [
	]

JSContext = JSContext

JSIntn = c_int

JSBool = JSIntn

JSInt32 = c_int

int32 = JSInt32

jsrefcount = int32

class JSPrincipals(Structure):
	_fields_ = [
		('codebase', c_char_p),
		('getPrincipalArray', CFUNCTYPE(c_void_p,POINTER(JSContext),POINTER('JSPrincipals'))),
		('globalPrivilegesEnabled', CFUNCTYPE(JSBool,POINTER(JSContext),POINTER('JSPrincipals'))),
		('refcount', jsrefcount),
		('destroy', CFUNCTYPE(None,POINTER(JSContext),POINTER('JSPrincipals'))),
	]

JSPrincipals = JSPrincipals

jsid = jsword

class JSProperty(Structure):
	_fields_ = [
		('id', jsid),
	]

JSProperty = JSProperty

class JSObjectMap(Structure):
	_fields_ = [
	]

JSObjectMap = JSObjectMap

class JSXDRState(Structure):
	_fields_ = [
	]

JSXDRState = JSXDRState

class JSObjectOps(Structure):
	_fields_ = []

JSUint32 = c_uint

uint32 = JSUint32

JSObject = JSObject

JSPropertyOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval))

JSEnumerateOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject))

JSResolveOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long)

# enumeration JSType
JSTYPE_VOID = 0
JSTYPE_OBJECT = 1
JSTYPE_FUNCTION = 2
JSTYPE_STRING = 3
JSTYPE_NUMBER = 4
JSTYPE_BOOLEAN = 5
JSTYPE_LIMIT = 6

JSConvertOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_int,POINTER(jsval))

JSFinalizeOp = CFUNCTYPE(None,POINTER(JSContext),POINTER(JSObject))

class JSClass(Structure):
	_fields_ = []

JSGetObjectOps = CFUNCTYPE(POINTER(JSObjectOps),POINTER(JSContext),POINTER(JSClass))

# enumeration JSAccessMode
JSACC_PROTO = 0
JSACC_PARENT = 1
JSACC_IMPORT = 2
JSACC_WATCH = 3
JSACC_READ = 4
JSACC_WRITE = 8
JSACC_LIMIT = 9

JSCheckAccessOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,c_int,POINTER(jsval))

JSNative = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_uint,POINTER(jsval),POINTER(jsval))

JSXDRObjectOp = CFUNCTYPE(JSBool,POINTER(JSXDRState),POINTER(POINTER(JSObject)))

JSHasInstanceOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(JSBool))

JSMarkOp = CFUNCTYPE(uint32,POINTER(JSContext),POINTER(JSObject),c_void_p)

class JSClass(Structure):
	_fields_ = [
		('name', c_char_p),
		('flags', uint32),
		('addProperty', JSPropertyOp),
		('delProperty', JSPropertyOp),
		('getProperty', JSPropertyOp),
		('setProperty', JSPropertyOp),
		('enumerate', JSEnumerateOp),
		('resolve', JSResolveOp),
		('convert', JSConvertOp),
		('finalize', JSFinalizeOp),
		('getObjectOps', JSGetObjectOps),
		('checkAccess', JSCheckAccessOp),
		('call', JSNative),
		('construct', JSNative),
		('xdrObject', JSXDRObjectOp),
		('hasInstance', JSHasInstanceOp),
		('mark', JSMarkOp),
		('spare', jsword),
	]

JSClass = JSClass

JSNewObjectMapOp = CFUNCTYPE(POINTER(JSObjectMap),POINTER(JSContext),c_int,POINTER(JSObjectOps),POINTER(JSClass),POINTER(JSObject))

JSObjectMapOp = CFUNCTYPE(None,POINTER(JSContext),POINTER(JSObjectMap))

JSLookupPropOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(POINTER(JSObject)),POINTER(POINTER(JSProperty)))

JSDefinePropOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,c_long,CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval)),CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval)),c_uint,POINTER(POINTER(JSProperty)))

JSPropertyIdOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval))

JSAttributesOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(JSProperty),POINTER(uintN))

# enumeration JSIterateOp
JSENUMERATE_INIT = 0
JSENUMERATE_NEXT = 1
JSENUMERATE_DESTROY = 2

JSNewEnumerateOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_int,POINTER(jsval),POINTER(jsid))

JSCheckAccessIdOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,c_int,POINTER(jsval),POINTER(uintN))

JSObjectOp = CFUNCTYPE(POINTER(JSObject),POINTER(JSContext),POINTER(JSObject))

JSPropertyRefOp = CFUNCTYPE(None,POINTER(JSContext),POINTER(JSObject),POINTER(JSProperty))

JSSetObjectSlotOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_uint,POINTER(JSObject))

JSGetRequiredSlotOp = CFUNCTYPE(jsval,POINTER(JSContext),POINTER(JSObject),c_uint)

JSSetRequiredSlotOp = CFUNCTYPE(None,POINTER(JSContext),POINTER(JSObject),c_uint,c_long)

class JSObjectOps(Structure):
	_fields_ = [
		('newObjectMap', JSNewObjectMapOp),
		('destroyObjectMap', JSObjectMapOp),
		('lookupProperty', JSLookupPropOp),
		('defineProperty', JSDefinePropOp),
		('getProperty', JSPropertyIdOp),
		('setProperty', JSPropertyIdOp),
		('getAttributes', JSAttributesOp),
		('setAttributes', JSAttributesOp),
		('deleteProperty', JSPropertyIdOp),
		('defaultValue', JSConvertOp),
		('enumerate', JSNewEnumerateOp),
		('checkAccess', JSCheckAccessIdOp),
		('thisObject', JSObjectOp),
		('dropProperty', JSPropertyRefOp),
		('call', JSNative),
		('construct', JSNative),
		('xdrObject', JSXDRObjectOp),
		('hasInstance', JSHasInstanceOp),
		('setProto', JSSetObjectSlotOp),
		('setParent', JSSetObjectSlotOp),
		('mark', JSMarkOp),
		('clear', JSFinalizeOp),
		('getRequiredSlot', JSGetRequiredSlotOp),
		('setRequiredSlot', JSSetRequiredSlotOp),
	]

JSObjectOps = JSObjectOps

JSUint16 = c_ushort

uint16 = JSUint16

jschar = uint16

class JSErrorReport(Structure):
	_fields_ = [
		('filename', c_char_p),
		('lineno', uintN),
		('linebuf', c_char_p),
		('tokenptr', c_char_p),
		('uclinebuf', POINTER(jschar)),
		('uctokenptr', POINTER(jschar)),
		('flags', uintN),
		('errorNumber', uintN),
		('ucmessage', POINTER(jschar)),
		('messageArgs', POINTER(POINTER(jschar))),
	]

class JSString(Structure):
	_fields_ = [
	]

JSString = JSString

JSLocaleToUpperCase = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSString),POINTER(jsval))

JSLocaleToLowerCase = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSString),POINTER(jsval))

JSLocaleCompare = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSString),POINTER(JSString),POINTER(jsval))

class JSLocaleCallbacks(Structure):
	_fields_ = [
		('localeToUpperCase', JSLocaleToUpperCase),
		('localeToLowerCase', JSLocaleToLowerCase),
		('localeCompare', JSLocaleCompare),
	]

JSUint8 = c_ubyte

uint8 = JSUint8

class JSFunctionSpec(Structure):
	_fields_ = [
		('name', c_char_p),
		('call', JSNative),
		('nargs', uint8),
		('flags', uint8),
		('extra', uint16),
	]

JSInt8 = c_char

int8 = JSInt8

class JSPropertySpec(Structure):
	_fields_ = [
		('name', c_char_p),
		('tinyid', int8),
		('flags', uint8),
		('getter', JSPropertyOp),
		('setter', JSPropertyOp),
	]

JSFloat64 = c_double

float64 = JSFloat64

jsdouble = float64

class JSConstDoubleSpec(Structure):
	_fields_ = [
		('dval', jsdouble),
		('name', c_char_p),
		('flags', uint8),
		('spare', uint8*3),
	]

jsint = int32

class JSIdArray(Structure):
	_fields_ = [
		('length', jsint),
		('vector', jsid*1),
	]

intN = JSIntn

JSErrorReport = JSErrorReport

class JSScript(Structure):
	_fields_ = [
	]

JSScript = JSScript

# enumeration JSGCStatus
JSGC_BEGIN = 0
JSGC_END = 1
JSGC_MARK_END = 2
JSGC_FINALIZE_END = 3

JSConstDoubleSpec = JSConstDoubleSpec

JSPropertySpec = JSPropertySpec

jsuint = uint32

JSIdArray = JSIdArray

class JSRuntime(Structure):
	_fields_ = [
	]

JSRuntime = JSRuntime

JSFunctionSpec = JSFunctionSpec

class JSFunction(Structure):
	_fields_ = [
	]

JSFunction = JSFunction

JSLocaleCallbacks = JSLocaleCallbacks

class JSExceptionState(Structure):
	_fields_ = [
	]

JSExceptionState = JSExceptionState

JSInt64 = c_longlong

from sm_settings import try_libs
for lib in try_libs:
    try:
        libsmjs = CDLL(lib)
        break
    except OSError:
        if lib == try_libs[-1]:
            raise ImportError("The spidermonkey C library is not installed")

JSLL_MaxInt = libsmjs.JSLL_MaxInt
JSLL_MaxInt.restype = JSInt64
JSLL_MaxInt.argtypes = []

JSLL_MinInt = libsmjs.JSLL_MinInt
JSLL_MinInt.restype = JSInt64
JSLL_MinInt.argtypes = []

JSLL_Zero = libsmjs.JSLL_Zero
JSLL_Zero.restype = JSInt64
JSLL_Zero.argtypes = []

JSUword = c_ulong

jsuword = JSUword

float32 = c_float

# enumeration Js-1.7.0.tar.gzSVersion
JSVERSION_1_0 = 100
JSVERSION_1_1 = 110
JSVERSION_1_2 = 120
JSVERSION_1_3 = 130
JSVERSION_1_4 = 140
JSVERSION_ECMA_3 = 148
JSVERSION_1_5 = 150
JSVERSION_DEFAULT = 0
JSVERSION_UNKNOWN = -1

JSVersion = c_int

JSType = c_int

JSAccessMode = c_int

JSIterateOp = c_int

JSTaskState = JSRuntime

JSNewResolveOp = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,c_uint,POINTER(POINTER(JSObject)))

JSStringFinalizeOp = CFUNCTYPE(None,POINTER(JSContext),POINTER(JSString))

JSGCStatus = c_int

JSGCCallback = CFUNCTYPE(JSBool,POINTER(JSContext),c_int)

JSBranchCallback = CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSScript))

JSErrorReporter = CFUNCTYPE(None,POINTER(JSContext),c_char_p,POINTER(JSErrorReport))

JSErrorCallback = CFUNCTYPE(POINTER(JSErrorFormatString),c_void_p,c_char_p,c_uint)

JSPrincipalsTranscoder = CFUNCTYPE(JSBool,POINTER(JSXDRState),POINTER(POINTER(JSPrincipals)))

JSObjectPrincipalsFinder = CFUNCTYPE(POINTER(JSPrincipals),POINTER(JSContext),POINTER(JSObject))

int64 = JSInt64

JS_Now = libsmjs.JS_Now
JS_Now.restype = int64
JS_Now.argtypes = []

JS_GetNaNValue = libsmjs.JS_GetNaNValue
JS_GetNaNValue.restype = jsval
JS_GetNaNValue.argtypes = [POINTER(JSContext)]

JS_GetNegativeInfinityValue = libsmjs.JS_GetNegativeInfinityValue
JS_GetNegativeInfinityValue.restype = jsval
JS_GetNegativeInfinityValue.argtypes = [POINTER(JSContext)]

JS_GetPositiveInfinityValue = libsmjs.JS_GetPositiveInfinityValue
JS_GetPositiveInfinityValue.restype = jsval
JS_GetPositiveInfinityValue.argtypes = [POINTER(JSContext)]

JS_GetEmptyStringValue = libsmjs.JS_GetEmptyStringValue
JS_GetEmptyStringValue.restype = jsval
JS_GetEmptyStringValue.argtypes = [POINTER(JSContext)]

JS_ConvertArguments = libsmjs.JS_ConvertArguments
JS_ConvertArguments.restype = JSBool
JS_ConvertArguments.argtypes = [POINTER(JSContext),c_uint,POINTER(jsval),c_char_p]

JS_PushArguments = libsmjs.JS_PushArguments
JS_PushArguments.restype = POINTER(jsval)
JS_PushArguments.argtypes = [POINTER(JSContext),POINTER(c_void_p),c_char_p]

JS_PopArguments = libsmjs.JS_PopArguments
JS_PopArguments.restype = None
JS_PopArguments.argtypes = [POINTER(JSContext),c_void_p]

JS_ConvertValue = libsmjs.JS_ConvertValue
JS_ConvertValue.restype = JSBool
JS_ConvertValue.argtypes = [POINTER(JSContext),c_long,c_int,POINTER(jsval)]

JS_ValueToObject = libsmjs.JS_ValueToObject
JS_ValueToObject.restype = JSBool
JS_ValueToObject.argtypes = [POINTER(JSContext),c_long,POINTER(POINTER(JSObject))]

JS_ValueToFunction = libsmjs.JS_ValueToFunction
JS_ValueToFunction.restype = POINTER(JSFunction)
JS_ValueToFunction.argtypes = [POINTER(JSContext),c_long]

JS_ValueToConstructor = libsmjs.JS_ValueToConstructor
JS_ValueToConstructor.restype = POINTER(JSFunction)
JS_ValueToConstructor.argtypes = [POINTER(JSContext),c_long]

JS_ValueToString = libsmjs.JS_ValueToString
JS_ValueToString.restype = POINTER(JSString)
JS_ValueToString.argtypes = [POINTER(JSContext),c_long]

JS_ValueToNumber = libsmjs.JS_ValueToNumber
JS_ValueToNumber.restype = JSBool
JS_ValueToNumber.argtypes = [POINTER(JSContext),c_long,POINTER(jsdouble)]

JS_ValueToECMAInt32 = libsmjs.JS_ValueToECMAInt32
JS_ValueToECMAInt32.restype = JSBool
JS_ValueToECMAInt32.argtypes = [POINTER(JSContext),c_long,POINTER(int32)]

JS_ValueToECMAUint32 = libsmjs.JS_ValueToECMAUint32
JS_ValueToECMAUint32.restype = JSBool
JS_ValueToECMAUint32.argtypes = [POINTER(JSContext),c_long,POINTER(uint32)]

JS_ValueToInt32 = libsmjs.JS_ValueToInt32
JS_ValueToInt32.restype = JSBool
JS_ValueToInt32.argtypes = [POINTER(JSContext),c_long,POINTER(int32)]

JS_ValueToUint16 = libsmjs.JS_ValueToUint16
JS_ValueToUint16.restype = JSBool
JS_ValueToUint16.argtypes = [POINTER(JSContext),c_long,POINTER(uint16)]

JS_ValueToBoolean = libsmjs.JS_ValueToBoolean
JS_ValueToBoolean.restype = JSBool
JS_ValueToBoolean.argtypes = [POINTER(JSContext),c_long,POINTER(JSBool)]

JS_TypeOfValue = libsmjs.JS_TypeOfValue
JS_TypeOfValue.restype = JSType
JS_TypeOfValue.argtypes = [POINTER(JSContext),c_long]

JS_GetTypeName = libsmjs.JS_GetTypeName
JS_GetTypeName.restype = c_char_p
JS_GetTypeName.argtypes = [POINTER(JSContext),c_int]

JS_Init = libsmjs.JS_Init
JS_Init.restype = POINTER(JSRuntime)
JS_Init.argtypes = [c_uint]

JS_Finish = libsmjs.JS_Finish
JS_Finish.restype = None
JS_Finish.argtypes = [POINTER(JSRuntime)]

JS_ShutDown = libsmjs.JS_ShutDown
JS_ShutDown.restype = None
JS_ShutDown.argtypes = []

JS_GetRuntimePrivate = libsmjs.JS_GetRuntimePrivate
JS_GetRuntimePrivate.restype = c_void_p
JS_GetRuntimePrivate.argtypes = [POINTER(JSRuntime)]

JS_SetRuntimePrivate = libsmjs.JS_SetRuntimePrivate
JS_SetRuntimePrivate.restype = None
JS_SetRuntimePrivate.argtypes = [POINTER(JSRuntime),c_void_p]

JS_Lock = libsmjs.JS_Lock
JS_Lock.restype = None
JS_Lock.argtypes = [POINTER(JSRuntime)]

JS_Unlock = libsmjs.JS_Unlock
JS_Unlock.restype = None
JS_Unlock.argtypes = [POINTER(JSRuntime)]

JS_NewContext = libsmjs.JS_NewContext
JS_NewContext.restype = POINTER(JSContext)
JS_NewContext.argtypes = [POINTER(JSRuntime),c_uint]

JS_DestroyContext = libsmjs.JS_DestroyContext
JS_DestroyContext.restype = None
JS_DestroyContext.argtypes = [POINTER(JSContext)]

JS_DestroyContextNoGC = libsmjs.JS_DestroyContextNoGC
JS_DestroyContextNoGC.restype = None
JS_DestroyContextNoGC.argtypes = [POINTER(JSContext)]

JS_DestroyContextMaybeGC = libsmjs.JS_DestroyContextMaybeGC
JS_DestroyContextMaybeGC.restype = None
JS_DestroyContextMaybeGC.argtypes = [POINTER(JSContext)]

JS_GetContextPrivate = libsmjs.JS_GetContextPrivate
JS_GetContextPrivate.restype = c_void_p
JS_GetContextPrivate.argtypes = [POINTER(JSContext)]

JS_SetContextPrivate = libsmjs.JS_SetContextPrivate
JS_SetContextPrivate.restype = None
JS_SetContextPrivate.argtypes = [POINTER(JSContext),c_void_p]

JS_GetRuntime = libsmjs.JS_GetRuntime
JS_GetRuntime.restype = POINTER(JSRuntime)
JS_GetRuntime.argtypes = [POINTER(JSContext)]

JS_ContextIterator = libsmjs.JS_ContextIterator
JS_ContextIterator.restype = POINTER(JSContext)
JS_ContextIterator.argtypes = [POINTER(JSRuntime),POINTER(POINTER(JSContext))]

JS_GetVersion = libsmjs.JS_GetVersion
JS_GetVersion.restype = JSVersion
JS_GetVersion.argtypes = [POINTER(JSContext)]

JS_SetVersion = libsmjs.JS_SetVersion
JS_SetVersion.restype = JSVersion
JS_SetVersion.argtypes = [POINTER(JSContext),c_int]

JS_VersionToString = libsmjs.JS_VersionToString
JS_VersionToString.restype = c_char_p
JS_VersionToString.argtypes = [c_int]

JS_StringToVersion = libsmjs.JS_StringToVersion
JS_StringToVersion.restype = JSVersion
JS_StringToVersion.argtypes = [c_char_p]

JS_GetOptions = libsmjs.JS_GetOptions
JS_GetOptions.restype = uint32
JS_GetOptions.argtypes = [POINTER(JSContext)]

JS_SetOptions = libsmjs.JS_SetOptions
JS_SetOptions.restype = uint32
JS_SetOptions.argtypes = [POINTER(JSContext),c_uint]

JS_ToggleOptions = libsmjs.JS_ToggleOptions
JS_ToggleOptions.restype = uint32
JS_ToggleOptions.argtypes = [POINTER(JSContext),c_uint]

JS_GetImplementationVersion = libsmjs.JS_GetImplementationVersion
JS_GetImplementationVersion.restype = c_char_p
JS_GetImplementationVersion.argtypes = []

JS_GetGlobalObject = libsmjs.JS_GetGlobalObject
JS_GetGlobalObject.restype = POINTER(JSObject)
JS_GetGlobalObject.argtypes = [POINTER(JSContext)]

JS_SetGlobalObject = libsmjs.JS_SetGlobalObject
JS_SetGlobalObject.restype = None
JS_SetGlobalObject.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_InitStandardClasses = libsmjs.JS_InitStandardClasses
JS_InitStandardClasses.restype = JSBool
JS_InitStandardClasses.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_ResolveStandardClass = libsmjs.JS_ResolveStandardClass
JS_ResolveStandardClass.restype = JSBool
JS_ResolveStandardClass.argtypes = [POINTER(JSContext),POINTER(JSObject),c_long,POINTER(JSBool)]

JS_EnumerateStandardClasses = libsmjs.JS_EnumerateStandardClasses
JS_EnumerateStandardClasses.restype = JSBool
JS_EnumerateStandardClasses.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_GetScopeChain = libsmjs.JS_GetScopeChain
JS_GetScopeChain.restype = POINTER(JSObject)
JS_GetScopeChain.argtypes = [POINTER(JSContext)]

JS_malloc = libsmjs.JS_malloc
JS_malloc.restype = c_void_p
JS_malloc.argtypes = [POINTER(JSContext),c_uint]

JS_realloc = libsmjs.JS_realloc
JS_realloc.restype = c_void_p
JS_realloc.argtypes = [POINTER(JSContext),c_void_p,c_uint]

JS_free = libsmjs.JS_free
JS_free.restype = None
JS_free.argtypes = [POINTER(JSContext),c_void_p]

JS_strdup = libsmjs.JS_strdup
JS_strdup.restype = c_char_p
JS_strdup.argtypes = [POINTER(JSContext),c_char_p]

JS_NewDouble = libsmjs.JS_NewDouble
JS_NewDouble.restype = POINTER(jsdouble)
JS_NewDouble.argtypes = [POINTER(JSContext),c_double]

JS_NewDoubleValue = libsmjs.JS_NewDoubleValue
JS_NewDoubleValue.restype = JSBool
JS_NewDoubleValue.argtypes = [POINTER(JSContext),c_double,POINTER(jsval)]

JS_NewNumberValue = libsmjs.JS_NewNumberValue
JS_NewNumberValue.restype = JSBool
JS_NewNumberValue.argtypes = [POINTER(JSContext),c_double,POINTER(jsval)]

JS_AddRoot = libsmjs.JS_AddRoot
JS_AddRoot.restype = JSBool
JS_AddRoot.argtypes = [POINTER(JSContext),c_void_p]

JS_AddNamedRoot = libsmjs.JS_AddNamedRoot
JS_AddNamedRoot.restype = JSBool
JS_AddNamedRoot.argtypes = [POINTER(JSContext),c_void_p,c_char_p]

JS_AddNamedRootRT = libsmjs.JS_AddNamedRootRT
JS_AddNamedRootRT.restype = JSBool
JS_AddNamedRootRT.argtypes = [POINTER(JSRuntime),c_void_p,c_char_p]

JS_RemoveRoot = libsmjs.JS_RemoveRoot
JS_RemoveRoot.restype = JSBool
JS_RemoveRoot.argtypes = [POINTER(JSContext),c_void_p]

JS_RemoveRootRT = libsmjs.JS_RemoveRootRT
JS_RemoveRootRT.restype = JSBool
JS_RemoveRootRT.argtypes = [POINTER(JSRuntime),c_void_p]

JS_ClearNewbornRoots = libsmjs.JS_ClearNewbornRoots
JS_ClearNewbornRoots.restype = None
JS_ClearNewbornRoots.argtypes = [POINTER(JSContext)]

JSGCRootMapFun = CFUNCTYPE(intN,c_void_p,c_char_p,c_void_p)

JS_MapGCRoots = libsmjs.JS_MapGCRoots
JS_MapGCRoots.restype = uint32
JS_MapGCRoots.argtypes = [POINTER(JSRuntime),CFUNCTYPE(intN,c_void_p,c_char_p,c_void_p),c_void_p]

JS_LockGCThing = libsmjs.JS_LockGCThing
JS_LockGCThing.restype = JSBool
JS_LockGCThing.argtypes = [POINTER(JSContext),c_void_p]

JS_LockGCThingRT = libsmjs.JS_LockGCThingRT
JS_LockGCThingRT.restype = JSBool
JS_LockGCThingRT.argtypes = [POINTER(JSRuntime),c_void_p]

JS_UnlockGCThing = libsmjs.JS_UnlockGCThing
JS_UnlockGCThing.restype = JSBool
JS_UnlockGCThing.argtypes = [POINTER(JSContext),c_void_p]

JS_UnlockGCThingRT = libsmjs.JS_UnlockGCThingRT
JS_UnlockGCThingRT.restype = JSBool
JS_UnlockGCThingRT.argtypes = [POINTER(JSRuntime),c_void_p]

JS_MarkGCThing = libsmjs.JS_MarkGCThing
JS_MarkGCThing.restype = None
JS_MarkGCThing.argtypes = [POINTER(JSContext),c_void_p,c_char_p,c_void_p]

JS_GC = libsmjs.JS_GC
JS_GC.restype = None
JS_GC.argtypes = [POINTER(JSContext)]

JS_MaybeGC = libsmjs.JS_MaybeGC
JS_MaybeGC.restype = None
JS_MaybeGC.argtypes = [POINTER(JSContext)]

JS_SetGCCallback = libsmjs.JS_SetGCCallback
JS_SetGCCallback.restype = JSGCCallback
JS_SetGCCallback.argtypes = [POINTER(JSContext),CFUNCTYPE(JSBool,POINTER(JSContext),c_int)]

JS_SetGCCallbackRT = libsmjs.JS_SetGCCallbackRT
JS_SetGCCallbackRT.restype = JSGCCallback
JS_SetGCCallbackRT.argtypes = [POINTER(JSRuntime),CFUNCTYPE(JSBool,POINTER(JSContext),c_int)]

JS_IsAboutToBeFinalized = libsmjs.JS_IsAboutToBeFinalized
JS_IsAboutToBeFinalized.restype = JSBool
JS_IsAboutToBeFinalized.argtypes = [POINTER(JSContext),c_void_p]

JS_AddExternalStringFinalizer = libsmjs.JS_AddExternalStringFinalizer
JS_AddExternalStringFinalizer.restype = intN
JS_AddExternalStringFinalizer.argtypes = [CFUNCTYPE(None,POINTER(JSContext),POINTER(JSString))]

JS_RemoveExternalStringFinalizer = libsmjs.JS_RemoveExternalStringFinalizer
JS_RemoveExternalStringFinalizer.restype = intN
JS_RemoveExternalStringFinalizer.argtypes = [CFUNCTYPE(None,POINTER(JSContext),POINTER(JSString))]

JS_NewExternalString = libsmjs.JS_NewExternalString
JS_NewExternalString.restype = POINTER(JSString)
JS_NewExternalString.argtypes = [POINTER(JSContext),POINTER(jschar),c_uint,c_int]

JS_GetExternalStringGCType = libsmjs.JS_GetExternalStringGCType
JS_GetExternalStringGCType.restype = intN
JS_GetExternalStringGCType.argtypes = [POINTER(JSRuntime),POINTER(JSString)]

JS_SetThreadStackLimit = libsmjs.JS_SetThreadStackLimit
JS_SetThreadStackLimit.restype = None
JS_SetThreadStackLimit.argtypes = [POINTER(JSContext),c_ulong]

JS_DestroyIdArray = libsmjs.JS_DestroyIdArray
JS_DestroyIdArray.restype = None
JS_DestroyIdArray.argtypes = [POINTER(JSContext),POINTER(JSIdArray)]

JS_ValueToId = libsmjs.JS_ValueToId
JS_ValueToId.restype = JSBool
JS_ValueToId.argtypes = [POINTER(JSContext),c_long,POINTER(jsid)]

JS_IdToValue = libsmjs.JS_IdToValue
JS_IdToValue.restype = JSBool
JS_IdToValue.argtypes = [POINTER(JSContext),c_long,POINTER(jsval)]

JS_PropertyStub = JSPropertyOp(libsmjs.JS_PropertyStub)
#JS_PropertyStub.restype = JSBool
#JS_PropertyStub.argtypes = [POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval)]

JS_EnumerateStub = JSEnumerateOp(libsmjs.JS_EnumerateStub)
#JS_EnumerateStub.restype = JSBool
#JS_EnumerateStub.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_ResolveStub = JSResolveOp(libsmjs.JS_ResolveStub)
#JS_ResolveStub.restype = JSBool
#JS_ResolveStub.argtypes = [POINTER(JSContext),POINTER(JSObject),c_long]

JS_ConvertStub = JSConvertOp(libsmjs.JS_ConvertStub)
#JS_ConvertStub.restype = JSBool
#JS_ConvertStub.argtypes = [POINTER(JSContext),POINTER(JSObject),c_int,POINTER(jsval)]

JS_FinalizeStub = JSFinalizeOp(libsmjs.JS_FinalizeStub)
#JS_FinalizeStub.restype = None
#JS_FinalizeStub.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_InitClass = libsmjs.JS_InitClass
JS_InitClass.restype = POINTER(JSObject)
JS_InitClass.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSObject),POINTER(JSClass),CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_uint,POINTER(jsval),POINTER(jsval)),c_uint,POINTER(JSPropertySpec),POINTER(JSFunctionSpec),POINTER(JSPropertySpec),POINTER(JSFunctionSpec)]

JS_GetClass = libsmjs.JS_GetClass
JS_GetClass.restype = POINTER(JSClass)
JS_GetClass.argtypes = [POINTER(JSContext),POINTER(JSObject)]
#JS_GetClass.argtypes = [POINTER(JSObject)]

JS_InstanceOf = libsmjs.JS_InstanceOf
JS_InstanceOf.restype = JSBool
JS_InstanceOf.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSClass),POINTER(jsval)]

JS_GetPrivate = libsmjs.JS_GetPrivate
JS_GetPrivate.restype = c_void_p
JS_GetPrivate.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_SetPrivate = libsmjs.JS_SetPrivate
JS_SetPrivate.restype = JSBool
JS_SetPrivate.argtypes = [POINTER(JSContext),POINTER(JSObject),c_void_p]

JS_GetInstancePrivate = libsmjs.JS_GetInstancePrivate
JS_GetInstancePrivate.restype = c_void_p
JS_GetInstancePrivate.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSClass),POINTER(jsval)]

JS_GetPrototype = libsmjs.JS_GetPrototype
JS_GetPrototype.restype = POINTER(JSObject)
JS_GetPrototype.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_SetPrototype = libsmjs.JS_SetPrototype
JS_SetPrototype.restype = JSBool
JS_SetPrototype.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSObject)]

JS_GetParent = libsmjs.JS_GetParent
JS_GetParent.restype = POINTER(JSObject)
JS_GetParent.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_SetParent = libsmjs.JS_SetParent
JS_SetParent.restype = JSBool
JS_SetParent.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSObject)]

JS_GetConstructor = libsmjs.JS_GetConstructor
JS_GetConstructor.restype = POINTER(JSObject)
JS_GetConstructor.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_GetObjectId = libsmjs.JS_GetObjectId
JS_GetObjectId.restype = JSBool
JS_GetObjectId.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jsid)]

JS_NewObject = libsmjs.JS_NewObject
JS_NewObject.restype = POINTER(JSObject)
JS_NewObject.argtypes = [POINTER(JSContext),POINTER(JSClass),POINTER(JSObject),POINTER(JSObject)]

JS_SealObject = libsmjs.JS_SealObject
JS_SealObject.restype = JSBool
JS_SealObject.argtypes = [POINTER(JSContext),POINTER(JSObject),c_int]

JS_ConstructObject = libsmjs.JS_ConstructObject
JS_ConstructObject.restype = POINTER(JSObject)
JS_ConstructObject.argtypes = [POINTER(JSContext),POINTER(JSClass),POINTER(JSObject),POINTER(JSObject)]

JS_ConstructObjectWithArguments = libsmjs.JS_ConstructObjectWithArguments
JS_ConstructObjectWithArguments.restype = POINTER(JSObject)
JS_ConstructObjectWithArguments.argtypes = [POINTER(JSContext),POINTER(JSClass),POINTER(JSObject),POINTER(JSObject),c_uint,POINTER(jsval)]

JS_DefineObject = libsmjs.JS_DefineObject
JS_DefineObject.restype = POINTER(JSObject)
JS_DefineObject.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,POINTER(JSClass),POINTER(JSObject),c_uint]

JS_DefineConstDoubles = libsmjs.JS_DefineConstDoubles
JS_DefineConstDoubles.restype = JSBool
JS_DefineConstDoubles.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSConstDoubleSpec)]

JS_DefineProperties = libsmjs.JS_DefineProperties
JS_DefineProperties.restype = JSBool
JS_DefineProperties.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSPropertySpec)]

JS_DefineProperty = libsmjs.JS_DefineProperty
JS_DefineProperty.restype = JSBool
#JS_DefineProperty.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_long,CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval)),CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval)),c_uint]
JS_DefineProperty.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_long,c_void_p,c_void_p,c_uint]

JS_GetPropertyAttributes = libsmjs.JS_GetPropertyAttributes
JS_GetPropertyAttributes.restype = JSBool
JS_GetPropertyAttributes.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,POINTER(uintN),POINTER(JSBool)]

JS_SetPropertyAttributes = libsmjs.JS_SetPropertyAttributes
JS_SetPropertyAttributes.restype = JSBool
JS_SetPropertyAttributes.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_uint,POINTER(JSBool)]

JS_DefinePropertyWithTinyId = libsmjs.JS_DefinePropertyWithTinyId
JS_DefinePropertyWithTinyId.restype = JSBool
JS_DefinePropertyWithTinyId.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_char,c_long,CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval)),CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval)),c_uint]

JS_AliasProperty = libsmjs.JS_AliasProperty
JS_AliasProperty.restype = JSBool
JS_AliasProperty.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_char_p]

JS_LookupProperty = libsmjs.JS_LookupProperty
JS_LookupProperty.restype = JSBool
JS_LookupProperty.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,POINTER(jsval)]

JS_GetProperty = libsmjs.JS_GetProperty
JS_GetProperty.restype = JSBool
JS_GetProperty.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,POINTER(jsval)]

JS_SetProperty = libsmjs.JS_SetProperty
JS_SetProperty.restype = JSBool
JS_SetProperty.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,POINTER(jsval)]

JS_DeleteProperty = libsmjs.JS_DeleteProperty
JS_DeleteProperty.restype = JSBool
JS_DeleteProperty.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p]

JS_DeleteProperty2 = libsmjs.JS_DeleteProperty2
JS_DeleteProperty2.restype = JSBool
JS_DeleteProperty2.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,POINTER(jsval)]

JS_DefineUCProperty = libsmjs.JS_DefineUCProperty
JS_DefineUCProperty.restype = JSBool
JS_DefineUCProperty.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jschar),c_uint,c_long,CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval)),CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval)),c_uint]

JS_GetUCPropertyAttributes = libsmjs.JS_GetUCPropertyAttributes
JS_GetUCPropertyAttributes.restype = JSBool
JS_GetUCPropertyAttributes.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jschar),c_uint,POINTER(uintN),POINTER(JSBool)]

JS_SetUCPropertyAttributes = libsmjs.JS_SetUCPropertyAttributes
JS_SetUCPropertyAttributes.restype = JSBool
JS_SetUCPropertyAttributes.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jschar),c_uint,c_uint,POINTER(JSBool)]

JS_DefineUCPropertyWithTinyId = libsmjs.JS_DefineUCPropertyWithTinyId
JS_DefineUCPropertyWithTinyId.restype = JSBool
JS_DefineUCPropertyWithTinyId.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jschar),c_uint,c_char,c_long,CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval)),CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,POINTER(jsval)),c_uint]

JS_LookupUCProperty = libsmjs.JS_LookupUCProperty
JS_LookupUCProperty.restype = JSBool
JS_LookupUCProperty.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jschar),c_uint,POINTER(jsval)]

JS_GetUCProperty = libsmjs.JS_GetUCProperty
JS_GetUCProperty.restype = JSBool
JS_GetUCProperty.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jschar),c_uint,POINTER(jsval)]

JS_SetUCProperty = libsmjs.JS_SetUCProperty
JS_SetUCProperty.restype = JSBool
JS_SetUCProperty.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jschar),c_uint,POINTER(jsval)]

JS_DeleteUCProperty2 = libsmjs.JS_DeleteUCProperty2
JS_DeleteUCProperty2.restype = JSBool
JS_DeleteUCProperty2.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jschar),c_uint,POINTER(jsval)]

JS_NewArrayObject = libsmjs.JS_NewArrayObject
JS_NewArrayObject.restype = POINTER(JSObject)
JS_NewArrayObject.argtypes = [POINTER(JSContext),c_int,POINTER(jsval)]

JS_IsArrayObject = libsmjs.JS_IsArrayObject
JS_IsArrayObject.restype = JSBool
JS_IsArrayObject.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_GetArrayLength = libsmjs.JS_GetArrayLength
JS_GetArrayLength.restype = JSBool
JS_GetArrayLength.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jsuint)]

JS_SetArrayLength = libsmjs.JS_SetArrayLength
JS_SetArrayLength.restype = JSBool
JS_SetArrayLength.argtypes = [POINTER(JSContext),POINTER(JSObject),c_uint]

JS_HasArrayLength = libsmjs.JS_HasArrayLength
JS_HasArrayLength.restype = JSBool
JS_HasArrayLength.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jsuint)]

JS_DefineElement = libsmjs.JS_DefineElement
JS_DefineElement.restype = JSBool
#JS_DefineElement.argtypes = [POINTER(JSContext),POINTER(JSObject),c_int,c_long,JSPropertyOp,JSPropertyOp,c_uint]
JS_DefineElement.argtypes = [POINTER(JSContext),POINTER(JSObject),c_int,c_long,c_void_p,c_void_p,c_uint]

JS_AliasElement = libsmjs.JS_AliasElement
JS_AliasElement.restype = JSBool
JS_AliasElement.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_int]

JS_LookupElement = libsmjs.JS_LookupElement
JS_LookupElement.restype = JSBool
JS_LookupElement.argtypes = [POINTER(JSContext),POINTER(JSObject),c_int,POINTER(jsval)]

JS_GetElement = libsmjs.JS_GetElement
JS_GetElement.restype = JSBool
JS_GetElement.argtypes = [POINTER(JSContext),POINTER(JSObject),c_int,POINTER(jsval)]

JS_SetElement = libsmjs.JS_SetElement
JS_SetElement.restype = JSBool
JS_SetElement.argtypes = [POINTER(JSContext),POINTER(JSObject),c_int,POINTER(jsval)]

JS_DeleteElement = libsmjs.JS_DeleteElement
JS_DeleteElement.restype = JSBool
JS_DeleteElement.argtypes = [POINTER(JSContext),POINTER(JSObject),c_int]

JS_DeleteElement2 = libsmjs.JS_DeleteElement2
JS_DeleteElement2.restype = JSBool
JS_DeleteElement2.argtypes = [POINTER(JSContext),POINTER(JSObject),c_int,POINTER(jsval)]

JS_ClearScope = libsmjs.JS_ClearScope
JS_ClearScope.restype = None
JS_ClearScope.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_Enumerate = libsmjs.JS_Enumerate
JS_Enumerate.restype = POINTER(JSIdArray)
JS_Enumerate.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_CheckAccess = libsmjs.JS_CheckAccess
JS_CheckAccess.restype = JSBool
JS_CheckAccess.argtypes = [POINTER(JSContext),POINTER(JSObject),c_long,c_int,POINTER(jsval),POINTER(uintN)]

JS_SetCheckObjectAccessCallback = libsmjs.JS_SetCheckObjectAccessCallback
JS_SetCheckObjectAccessCallback.restype = JSCheckAccessOp
JS_SetCheckObjectAccessCallback.argtypes = [POINTER(JSRuntime),CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_long,c_int,POINTER(jsval))]

JS_GetReservedSlot = libsmjs.JS_GetReservedSlot
JS_GetReservedSlot.restype = JSBool
JS_GetReservedSlot.argtypes = [POINTER(JSContext),POINTER(JSObject),c_uint,POINTER(jsval)]

JS_SetReservedSlot = libsmjs.JS_SetReservedSlot
JS_SetReservedSlot.restype = JSBool
JS_SetReservedSlot.argtypes = [POINTER(JSContext),POINTER(JSObject),c_uint,c_long]

JS_SetPrincipalsTranscoder = libsmjs.JS_SetPrincipalsTranscoder
JS_SetPrincipalsTranscoder.restype = JSPrincipalsTranscoder
JS_SetPrincipalsTranscoder.argtypes = [POINTER(JSRuntime),CFUNCTYPE(JSBool,POINTER(JSXDRState),POINTER(POINTER(JSPrincipals)))]

JS_SetObjectPrincipalsFinder = libsmjs.JS_SetObjectPrincipalsFinder
JS_SetObjectPrincipalsFinder.restype = JSObjectPrincipalsFinder
JS_SetObjectPrincipalsFinder.argtypes = [POINTER(JSContext),CFUNCTYPE(POINTER(JSPrincipals),POINTER(JSContext),POINTER(JSObject))]

JS_NewFunction = libsmjs.JS_NewFunction
JS_NewFunction.restype = POINTER(JSFunction)
JS_NewFunction.argtypes = [POINTER(JSContext),CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_uint,POINTER(jsval),POINTER(jsval)),c_uint,c_uint,POINTER(JSObject),c_char_p]

JS_GetFunctionObject = libsmjs.JS_GetFunctionObject
JS_GetFunctionObject.restype = POINTER(JSObject)
JS_GetFunctionObject.argtypes = [POINTER(JSFunction)]

JS_GetFunctionName = libsmjs.JS_GetFunctionName
JS_GetFunctionName.restype = c_char_p
JS_GetFunctionName.argtypes = [POINTER(JSFunction)]

JS_GetFunctionId = libsmjs.JS_GetFunctionId
JS_GetFunctionId.restype = POINTER(JSString)
JS_GetFunctionId.argtypes = [POINTER(JSFunction)]

JS_GetFunctionFlags = libsmjs.JS_GetFunctionFlags
JS_GetFunctionFlags.restype = uintN
JS_GetFunctionFlags.argtypes = [POINTER(JSFunction)]

JS_ObjectIsFunction = libsmjs.JS_ObjectIsFunction
JS_ObjectIsFunction.restype = JSBool
JS_ObjectIsFunction.argtypes = [POINTER(JSContext),POINTER(JSObject)]

JS_DefineFunctions = libsmjs.JS_DefineFunctions
JS_DefineFunctions.restype = JSBool
JS_DefineFunctions.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSFunctionSpec)]

JS_DefineFunction = libsmjs.JS_DefineFunction
JS_DefineFunction.restype = POINTER(JSFunction)
JS_DefineFunction.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSObject),c_uint,POINTER(jsval),POINTER(jsval)),c_uint,c_uint]

JS_CloneFunctionObject = libsmjs.JS_CloneFunctionObject
JS_CloneFunctionObject.restype = POINTER(JSObject)
JS_CloneFunctionObject.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSObject)]

JS_BufferIsCompilableUnit = libsmjs.JS_BufferIsCompilableUnit
JS_BufferIsCompilableUnit.restype = JSBool
JS_BufferIsCompilableUnit.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_uint]

JS_CompileScript = libsmjs.JS_CompileScript
JS_CompileScript.restype = POINTER(JSScript)
JS_CompileScript.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_uint,c_char_p,c_uint]

JS_CompileScriptForPrincipals = libsmjs.JS_CompileScriptForPrincipals
JS_CompileScriptForPrincipals.restype = POINTER(JSScript)
JS_CompileScriptForPrincipals.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSPrincipals),c_char_p,c_uint,c_char_p,c_uint]

JS_CompileUCScript = libsmjs.JS_CompileUCScript
JS_CompileUCScript.restype = POINTER(JSScript)
JS_CompileUCScript.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jschar),c_uint,c_char_p,c_uint]

JS_CompileUCScriptForPrincipals = libsmjs.JS_CompileUCScriptForPrincipals
JS_CompileUCScriptForPrincipals.restype = POINTER(JSScript)
JS_CompileUCScriptForPrincipals.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSPrincipals),POINTER(jschar),c_uint,c_char_p,c_uint]

JS_CompileFile = libsmjs.JS_CompileFile
JS_CompileFile.restype = POINTER(JSScript)
JS_CompileFile.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p]

class _IO_marker(Structure):
	_fields_ = [
		('_next', c_void_p),
		('_sbuf', POINTER(_IO_FILE)),
		('_pos', c_int),
	]

t__off_t = c_long

_IO_lock_t = None

t__quad_t = c_longlong

t__off64_t = t__quad_t

class _IO_FILE(Structure):
	_fields_ = [
		('_flags', c_int),
		('_IO_read_ptr', c_char_p),
		('_IO_read_end', c_char_p),
		('_IO_read_base', c_char_p),
		('_IO_write_base', c_char_p),
		('_IO_write_ptr', c_char_p),
		('_IO_write_end', c_char_p),
		('_IO_buf_base', c_char_p),
		('_IO_buf_end', c_char_p),
		('_IO_save_base', c_char_p),
		('_IO_backup_base', c_char_p),
		('_IO_save_end', c_char_p),
		('_markers', POINTER(_IO_marker)),
		('_chain', c_void_p),
		('_fileno', c_int),
		('_flags2', c_int),
		('_old_offset', t__off_t),
		('_cur_column', c_ushort),
		('_vtable_offset', c_char),
		('_shortbuf', c_char*1),
		('_lock', POINTER(_IO_lock_t)),
		('_offset', t__off64_t),
		('__pad1', c_void_p),
		('__pad2', c_void_p),
		('_mode', c_int),
		('_unused2', c_char*52),
	]

FILE = _IO_FILE

JS_CompileFileHandle = libsmjs.JS_CompileFileHandle
JS_CompileFileHandle.restype = POINTER(JSScript)
JS_CompileFileHandle.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,POINTER(FILE)]

JS_CompileFileHandleForPrincipals = libsmjs.JS_CompileFileHandleForPrincipals
JS_CompileFileHandleForPrincipals.restype = POINTER(JSScript)
JS_CompileFileHandleForPrincipals.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,POINTER(FILE),POINTER(JSPrincipals)]

JS_NewScriptObject = libsmjs.JS_NewScriptObject
JS_NewScriptObject.restype = POINTER(JSObject)
JS_NewScriptObject.argtypes = [POINTER(JSContext),POINTER(JSScript)]

JS_GetScriptObject = libsmjs.JS_GetScriptObject
JS_GetScriptObject.restype = POINTER(JSObject)
JS_GetScriptObject.argtypes = [POINTER(JSScript)]

JS_DestroyScript = libsmjs.JS_DestroyScript
JS_DestroyScript.restype = None
JS_DestroyScript.argtypes = [POINTER(JSContext),POINTER(JSScript)]

JS_CompileFunction = libsmjs.JS_CompileFunction
JS_CompileFunction.restype = POINTER(JSFunction)
JS_CompileFunction.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_uint,POINTER(c_char_p),c_char_p,c_uint,c_char_p,c_uint]

JS_CompileFunctionForPrincipals = libsmjs.JS_CompileFunctionForPrincipals
JS_CompileFunctionForPrincipals.restype = POINTER(JSFunction)
JS_CompileFunctionForPrincipals.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSPrincipals),c_char_p,c_uint,POINTER(c_char_p),c_char_p,c_uint,c_char_p,c_uint]

JS_CompileUCFunction = libsmjs.JS_CompileUCFunction
JS_CompileUCFunction.restype = POINTER(JSFunction)
JS_CompileUCFunction.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_uint,POINTER(c_char_p),POINTER(jschar),c_uint,c_char_p,c_uint]

JS_CompileUCFunctionForPrincipals = libsmjs.JS_CompileUCFunctionForPrincipals
JS_CompileUCFunctionForPrincipals.restype = POINTER(JSFunction)
JS_CompileUCFunctionForPrincipals.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSPrincipals),c_char_p,c_uint,POINTER(c_char_p),POINTER(jschar),c_uint,c_char_p,c_uint]

JS_DecompileScript = libsmjs.JS_DecompileScript
JS_DecompileScript.restype = POINTER(JSString)
JS_DecompileScript.argtypes = [POINTER(JSContext),POINTER(JSScript),c_char_p,c_uint]

JS_DecompileFunction = libsmjs.JS_DecompileFunction
JS_DecompileFunction.restype = POINTER(JSString)
JS_DecompileFunction.argtypes = [POINTER(JSContext),POINTER(JSFunction),c_uint]

JS_DecompileFunctionBody = libsmjs.JS_DecompileFunctionBody
JS_DecompileFunctionBody.restype = POINTER(JSString)
JS_DecompileFunctionBody.argtypes = [POINTER(JSContext),POINTER(JSFunction),c_uint]

JS_ExecuteScript = libsmjs.JS_ExecuteScript
JS_ExecuteScript.restype = JSBool
JS_ExecuteScript.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSScript),POINTER(jsval)]

# enumeration JSExecPart
JSEXEC_PROLOG = 0
JSEXEC_MAIN = 1

JSExecPart = c_int

JS_ExecuteScriptPart = libsmjs.JS_ExecuteScriptPart
JS_ExecuteScriptPart.restype = JSBool
JS_ExecuteScriptPart.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSScript),c_int,POINTER(jsval)]

JS_EvaluateScript = libsmjs.JS_EvaluateScript
JS_EvaluateScript.restype = JSBool
JS_EvaluateScript.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_uint,c_char_p,c_uint,POINTER(jsval)]

JS_EvaluateScriptForPrincipals = libsmjs.JS_EvaluateScriptForPrincipals
JS_EvaluateScriptForPrincipals.restype = JSBool
JS_EvaluateScriptForPrincipals.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSPrincipals),c_char_p,c_uint,c_char_p,c_uint,POINTER(jsval)]

JS_EvaluateUCScript = libsmjs.JS_EvaluateUCScript
JS_EvaluateUCScript.restype = JSBool
JS_EvaluateUCScript.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(jschar),c_uint,c_char_p,c_uint,POINTER(jsval)]

JS_EvaluateUCScriptForPrincipals = libsmjs.JS_EvaluateUCScriptForPrincipals
JS_EvaluateUCScriptForPrincipals.restype = JSBool
JS_EvaluateUCScriptForPrincipals.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSPrincipals),POINTER(jschar),c_uint,c_char_p,c_uint,POINTER(jsval)]

JS_CallFunction = libsmjs.JS_CallFunction
JS_CallFunction.restype = JSBool
JS_CallFunction.argtypes = [POINTER(JSContext),POINTER(JSObject),POINTER(JSFunction),c_uint,POINTER(jsval),POINTER(jsval)]

JS_CallFunctionName = libsmjs.JS_CallFunctionName
JS_CallFunctionName.restype = JSBool
JS_CallFunctionName.argtypes = [POINTER(JSContext),POINTER(JSObject),c_char_p,c_uint,POINTER(jsval),POINTER(jsval)]

JS_CallFunctionValue = libsmjs.JS_CallFunctionValue
JS_CallFunctionValue.restype = JSBool
JS_CallFunctionValue.argtypes = [POINTER(JSContext),POINTER(JSObject),c_long,c_uint,POINTER(jsval),POINTER(jsval)]

JS_SetBranchCallback = libsmjs.JS_SetBranchCallback
JS_SetBranchCallback.restype = JSBranchCallback
JS_SetBranchCallback.argtypes = [POINTER(JSContext),CFUNCTYPE(JSBool,POINTER(JSContext),POINTER(JSScript))]

JS_IsRunning = libsmjs.JS_IsRunning
JS_IsRunning.restype = JSBool
JS_IsRunning.argtypes = [POINTER(JSContext)]

JS_IsConstructing = libsmjs.JS_IsConstructing
JS_IsConstructing.restype = JSBool
JS_IsConstructing.argtypes = [POINTER(JSContext)]

JS_IsAssigning = libsmjs.JS_IsAssigning
JS_IsAssigning.restype = JSBool
JS_IsAssigning.argtypes = [POINTER(JSContext)]

JS_SetCallReturnValue2 = libsmjs.JS_SetCallReturnValue2
JS_SetCallReturnValue2.restype = None
JS_SetCallReturnValue2.argtypes = [POINTER(JSContext),c_long]

JS_NewString = libsmjs.JS_NewString
JS_NewString.restype = POINTER(JSString)
JS_NewString.argtypes = [POINTER(JSContext),c_char_p,c_uint]

JS_NewStringCopyN = libsmjs.JS_NewStringCopyN
JS_NewStringCopyN.restype = POINTER(JSString)
JS_NewStringCopyN.argtypes = [POINTER(JSContext),c_char_p,c_uint]

JS_NewStringCopyZ = libsmjs.JS_NewStringCopyZ
JS_NewStringCopyZ.restype = POINTER(JSString)
JS_NewStringCopyZ.argtypes = [POINTER(JSContext),c_char_p]

JS_InternString = libsmjs.JS_InternString
JS_InternString.restype = POINTER(JSString)
JS_InternString.argtypes = [POINTER(JSContext),c_char_p]

JS_NewUCString = libsmjs.JS_NewUCString
JS_NewUCString.restype = POINTER(JSString)
JS_NewUCString.argtypes = [POINTER(JSContext),POINTER(jschar),c_uint]

JS_NewUCStringCopyN = libsmjs.JS_NewUCStringCopyN
JS_NewUCStringCopyN.restype = POINTER(JSString)
JS_NewUCStringCopyN.argtypes = [POINTER(JSContext),POINTER(jschar),c_uint]

JS_NewUCStringCopyZ = libsmjs.JS_NewUCStringCopyZ
JS_NewUCStringCopyZ.restype = POINTER(JSString)
JS_NewUCStringCopyZ.argtypes = [POINTER(JSContext),POINTER(jschar)]

JS_InternUCStringN = libsmjs.JS_InternUCStringN
JS_InternUCStringN.restype = POINTER(JSString)
JS_InternUCStringN.argtypes = [POINTER(JSContext),POINTER(jschar),c_uint]

JS_InternUCString = libsmjs.JS_InternUCString
JS_InternUCString.restype = POINTER(JSString)
JS_InternUCString.argtypes = [POINTER(JSContext),POINTER(jschar)]

JS_GetStringBytes = libsmjs.JS_GetStringBytes
JS_GetStringBytes.restype = c_char_p
JS_GetStringBytes.argtypes = [POINTER(JSString)]

JS_GetStringChars = libsmjs.JS_GetStringChars
JS_GetStringChars.restype = POINTER(jschar)
JS_GetStringChars.argtypes = [POINTER(JSString)]

JS_GetStringLength = libsmjs.JS_GetStringLength
JS_GetStringLength.restype = size_t
JS_GetStringLength.argtypes = [POINTER(JSString)]

JS_CompareStrings = libsmjs.JS_CompareStrings
JS_CompareStrings.restype = intN
JS_CompareStrings.argtypes = [POINTER(JSString),POINTER(JSString)]

JS_NewGrowableString = libsmjs.JS_NewGrowableString
JS_NewGrowableString.restype = POINTER(JSString)
JS_NewGrowableString.argtypes = [POINTER(JSContext),POINTER(jschar),c_uint]

JS_NewDependentString = libsmjs.JS_NewDependentString
JS_NewDependentString.restype = POINTER(JSString)
JS_NewDependentString.argtypes = [POINTER(JSContext),POINTER(JSString),c_uint,c_uint]

JS_ConcatStrings = libsmjs.JS_ConcatStrings
JS_ConcatStrings.restype = POINTER(JSString)
JS_ConcatStrings.argtypes = [POINTER(JSContext),POINTER(JSString),POINTER(JSString)]

JS_UndependString = libsmjs.JS_UndependString
JS_UndependString.restype = POINTER(jschar)
JS_UndependString.argtypes = [POINTER(JSContext),POINTER(JSString)]

JS_MakeStringImmutable = libsmjs.JS_MakeStringImmutable
JS_MakeStringImmutable.restype = JSBool
JS_MakeStringImmutable.argtypes = [POINTER(JSContext),POINTER(JSString)]

JS_SetLocaleCallbacks = libsmjs.JS_SetLocaleCallbacks
JS_SetLocaleCallbacks.restype = None
JS_SetLocaleCallbacks.argtypes = [POINTER(JSContext),POINTER(JSLocaleCallbacks)]

JS_GetLocaleCallbacks = libsmjs.JS_GetLocaleCallbacks
JS_GetLocaleCallbacks.restype = POINTER(JSLocaleCallbacks)
JS_GetLocaleCallbacks.argtypes = [POINTER(JSContext)]

JS_ReportError = libsmjs.JS_ReportError
JS_ReportError.restype = None
JS_ReportError.argtypes = [POINTER(JSContext),c_char_p]

JS_ReportErrorNumber = libsmjs.JS_ReportErrorNumber
JS_ReportErrorNumber.restype = None
JS_ReportErrorNumber.argtypes = [POINTER(JSContext),CFUNCTYPE(POINTER(JSErrorFormatString),c_void_p,c_char_p,c_uint),c_void_p,c_uint]

JS_ReportErrorNumberUC = libsmjs.JS_ReportErrorNumberUC
JS_ReportErrorNumberUC.restype = None
JS_ReportErrorNumberUC.argtypes = [POINTER(JSContext),CFUNCTYPE(POINTER(JSErrorFormatString),c_void_p,c_char_p,c_uint),c_void_p,c_uint]

JS_ReportWarning = libsmjs.JS_ReportWarning
JS_ReportWarning.restype = JSBool
JS_ReportWarning.argtypes = [POINTER(JSContext),c_char_p]

JS_ReportErrorFlagsAndNumber = libsmjs.JS_ReportErrorFlagsAndNumber
JS_ReportErrorFlagsAndNumber.restype = JSBool
JS_ReportErrorFlagsAndNumber.argtypes = [POINTER(JSContext),c_uint,CFUNCTYPE(POINTER(JSErrorFormatString),c_void_p,c_char_p,c_uint),c_void_p,c_uint]

JS_ReportErrorFlagsAndNumberUC = libsmjs.JS_ReportErrorFlagsAndNumberUC
JS_ReportErrorFlagsAndNumberUC.restype = JSBool
JS_ReportErrorFlagsAndNumberUC.argtypes = [POINTER(JSContext),c_uint,CFUNCTYPE(POINTER(JSErrorFormatString),c_void_p,c_char_p,c_uint),c_void_p,c_uint]

JS_ReportOutOfMemory = libsmjs.JS_ReportOutOfMemory
JS_ReportOutOfMemory.restype = None
JS_ReportOutOfMemory.argtypes = [POINTER(JSContext)]

JS_SetErrorReporter = libsmjs.JS_SetErrorReporter
JS_SetErrorReporter.restype = JSErrorReporter
JS_SetErrorReporter.argtypes = [POINTER(JSContext),CFUNCTYPE(None,POINTER(JSContext),c_char_p,POINTER(JSErrorReport))]

JS_NewRegExpObject = libsmjs.JS_NewRegExpObject
JS_NewRegExpObject.restype = POINTER(JSObject)
JS_NewRegExpObject.argtypes = [POINTER(JSContext),c_char_p,c_uint,c_uint]

JS_NewUCRegExpObject = libsmjs.JS_NewUCRegExpObject
JS_NewUCRegExpObject.restype = POINTER(JSObject)
JS_NewUCRegExpObject.argtypes = [POINTER(JSContext),POINTER(jschar),c_uint,c_uint]

JS_SetRegExpInput = libsmjs.JS_SetRegExpInput
JS_SetRegExpInput.restype = None
JS_SetRegExpInput.argtypes = [POINTER(JSContext),POINTER(JSString),c_int]

JS_ClearRegExpStatics = libsmjs.JS_ClearRegExpStatics
JS_ClearRegExpStatics.restype = None
JS_ClearRegExpStatics.argtypes = [POINTER(JSContext)]

JS_ClearRegExpRoots = libsmjs.JS_ClearRegExpRoots
JS_ClearRegExpRoots.restype = None
JS_ClearRegExpRoots.argtypes = [POINTER(JSContext)]

JS_IsExceptionPending = libsmjs.JS_IsExceptionPending
JS_IsExceptionPending.restype = JSBool
JS_IsExceptionPending.argtypes = [POINTER(JSContext)]

JS_GetPendingException = libsmjs.JS_GetPendingException
JS_GetPendingException.restype = JSBool
JS_GetPendingException.argtypes = [POINTER(JSContext),POINTER(jsval)]

JS_SetPendingException = libsmjs.JS_SetPendingException
JS_SetPendingException.restype = None
JS_SetPendingException.argtypes = [POINTER(JSContext),c_long]

JS_ClearPendingException = libsmjs.JS_ClearPendingException
JS_ClearPendingException.restype = None
JS_ClearPendingException.argtypes = [POINTER(JSContext)]

JS_SaveExceptionState = libsmjs.JS_SaveExceptionState
JS_SaveExceptionState.restype = POINTER(JSExceptionState)
JS_SaveExceptionState.argtypes = [POINTER(JSContext)]

JS_RestoreExceptionState = libsmjs.JS_RestoreExceptionState
JS_RestoreExceptionState.restype = None
JS_RestoreExceptionState.argtypes = [POINTER(JSContext),POINTER(JSExceptionState)]

JS_DropExceptionState = libsmjs.JS_DropExceptionState
JS_DropExceptionState.restype = None
JS_DropExceptionState.argtypes = [POINTER(JSContext),POINTER(JSExceptionState)]

JS_ErrorFromException = libsmjs.JS_ErrorFromException
JS_ErrorFromException.restype = POINTER(JSErrorReport)
JS_ErrorFromException.argtypes = [POINTER(JSContext),c_long]

JSACC_TYPEMASK = (JSACC_WRITE - 1)
JSLL_MAXINT = JSLL_MaxInt()
JSLL_MININT = JSLL_MinInt()
JSLL_ZERO = JSLL_Zero()

_tabs = 0

def _log_call(func, *args, **kargs):
	global _tabs
	_tabs += 1
	try:
		print '\t'*_tabs + 'CALL {',func,args,kargs,'}'
		r = func(*args,**kargs)
		print '\t'*_tabs + "RETURNED",r
	finally:
		_tabs += 0
	return r

def log_call(func):
	return lambda *args, **kargs: _log_call(func,*args,**kargs)

class JSError(Exception):
	pass

def dict_from_JShash(context, hash):
	#~ cdef JSIdArray *prop_arr
	#~ cdef int i
	#~ cdef jsval jskey
	#~ cdef jsval jsvalue
	#~ cdef JSObject *obj

	
	cx = context.cx

	prop_arr = JS_Enumerate(cx, hash).contents

	jskey = jsval()
	jsvalue = jsval()

	d = {}
	
	for i in range(prop_arr.length):
		vector = cast(addressof(prop_arr.vector),POINTER(c_long))
		JS_IdToValue(cx, (vector)[i], byref(jskey))

		if JSVAL_IS_STRING(jskey):
			key = JS_GetStringBytes(JSVAL_TO_STRING(jskey))
			JS_GetProperty(cx, hash, key, byref(jsvalue))
		elif JSVAL_IS_INT(jskey):
			key = JSVAL_TO_INT(jskey)
			JS_GetElement(cx, hash, key, byref(jsvalue))
		else:
			assert False, "can't happen"

		if JSVAL_IS_PRIMITIVE(jsvalue):
			d[key] = Py_from_JSprimitive(jsvalue)
		else:
			if JSVAL_IS_OBJECT(jsvalue):
				obj = JSVAL_TO_OBJECT(jsvalue)
				if JS_IsArrayObject(cx, obj):
					d[key] = list_from_JSarray(context, obj)
				else:
					d[key] = dict_from_JShash(context, obj)

	JS_DestroyIdArray(cx, prop_arr)

	return d

def list_from_JSarray(context, array):
	#~ cdef int nr_elems, i
	#~ cdef jsval elem
	#~ cdef JSObject *jsobj

	nr_elems = c_uint()	
	elem = jsval()

	cx = context.cx
	JS_GetArrayLength(cx, array, byref(nr_elems))
	nr_elems = nr_elems.value

	l = [None]*nr_elems

	for i in range(nr_elems):
		JS_GetElement(cx, array, i, byref(elem))

		if JSVAL_IS_PRIMITIVE(elem):
			l[i] = Py_from_JSprimitive(elem)
		elif JSVAL_IS_OBJECT(elem):
			jsobj = JSVAL_TO_OBJECT(elem)
			if JS_IsArrayObject(cx, jsobj):
				l[i] = list_from_JSarray(context, jsobj)
			else:
				l[i] = dict_from_JShash(context, jsobj)

	return l

def Py_from_JSprimitive(v):
	# JS_NULL is null, JS_VOID is undefined
	if JSVAL_IS_NULL(v) or JSVAL_IS_VOID(v):
		return None
	elif JSVAL_IS_INT(v):
		return JSVAL_TO_INT(v)
	elif JSVAL_IS_DOUBLE(v):
		return JSVAL_TO_DOUBLE(v)[0]
	elif JSVAL_IS_STRING(v):
		return JS_GetStringBytes(JSVAL_TO_STRING(v))
	elif JSVAL_IS_BOOLEAN(v):
		return bool(JSVAL_TO_BOOLEAN(v))
	else:
		raise SystemError("unknown primitive type")

def Py_from_JS(context, v):
	# Convert JavaScript value to equivalent Python value.
	#~ cdef JSObject *object
	#~ cdef ProxyObject proxy_obj
	#~ cdef Context context

	if JSVAL_IS_PRIMITIVE(v):
		return Py_from_JSprimitive(v)
	else:
		if JSVAL_IS_OBJECT(v):
			object = JSVAL_TO_OBJECT(v)

			if JS_IsArrayObject(context.cx, object):
				return list_from_JSarray(context, object)
			else:
				try:
					proxy_obj = context.get_object(object)
				except ValueError:
					return dict_from_JShash(context, object)
				else:
					return proxy_obj.obj

def isinteger(x):
	return bool(compat_isinstance(x, (IntType, LongType)))

def isfloat(x):
	return bool(compat_isinstance(x, FloatType))

def isstringlike(x):
	return bool(compat_isinstance(x, StringTypes))

def issequence(x):
	return bool(compat_isinstance(x, (ListType, TupleType)))

def ismapping(x):
	return bool(compat_isinstance(x, DictType))

def js_classname(pobj):
	# class or instance?
	try:
		klass = pobj.__class__
	except AttributeError:
		klass = pobj

	try:
		name = klass.js_name
	except AttributeError:
		name = klass.__name__

	if not isstringlike(name):
		raise AttributeError("%s js_name attribute is not string-like" % klass)
	return name

def JS_from_Py(context, parent, py_obj):
	# Convert Python value to equivalent JavaScript value.
	#~ cdef JSObject *jsobj
	#~ cdef JSString *s

	#~ cdef jsval elem
	#~ cdef jsval rval

	#~ cdef int i
	#~ cdef int nr_elems
	#~ cdef jsval *elems
	#~ cdef JSObject *arr_obj

	#~ cdef Context context
	#~ cdef ProxyClass proxy_class
	#~ cdef ProxyObject proxy_obj

	rval = jsval()
	cx = context.cx

	if py_obj is None:
		return JSVAL_VOID
	elif isinteger(py_obj):
		return INT_TO_JSVAL(py_obj)
	elif isfloat(py_obj):
		d = JS_NewDouble(cx, py_obj)
		if d == None:
			raise SystemError("can't create new double")
		return DOUBLE_TO_JSVAL(d)
	elif isstringlike(py_obj):
		s = JS_NewStringCopyN(cx, py_obj, len(py_obj))
		if s == None:
			raise SystemError("can't create new string")
		return STRING_TO_JSVAL(s)
	elif ismapping(py_obj):
		jsobj = JS_NewObject(cx, None, None, None)

		if jsobj == None:
			raise SystemError("can't create new object")
		else:
			# assign properties
			for key, value in py_obj.iteritems():
				elem = JS_from_Py(context, parent, value)
				ok = JS_DefineProperty(cx, jsobj, key, elem, None, None, JSPROP_ENUMERATE)
				if not ok:
					raise SystemError("can't define property")

			return OBJECT_TO_JSVAL(jsobj)

	elif issequence(py_obj):
		arr_obj = JS_NewArrayObject(cx, 0, None)

		if arr_obj == None:
			raise SystemError("can't create new array object")
		else:
			for i in range(len(py_obj)):
				elem = JS_from_Py(context, parent, py_obj[i])
				ok = JS_DefineElement(cx, arr_obj, i, elem, None, None, JSPROP_ENUMERATE)
				if not ok:
					raise SystemError("can't define element")

		return OBJECT_TO_JSVAL(arr_obj)
	elif compat_isinstance(py_obj, MethodType):
		# XXX leak? -- calls JS_DefineFunction every time a method
		#  is called
		return context.new_method(py_obj)
	elif compat_isinstance(py_obj, (FunctionType, LambdaType)):
		# XXX implement me?
		return JSVAL_VOID
	else:
		# If we get here, py_obj is probably a Python class or a class instance.
		# XXXX could problems be caused if some weird object such a module or
		#  regexp or code object were, eg., returned by a Python function?
		
		# is object already bound to a JS proxy?...
		try:
			proxy_obj = context.get_object_from_py(py_obj)
		except ValueError:
			# ...no, so create and register a new JS proxy
			proxy_class = context.get_class(js_classname(py_obj))
			# XXXX I have *no idea* if using globj as the proto here is
			#  correct!  If I don't put globj in here, JS does a get_property
			#  on an object that hasn't been registered with the Context --
			#  dunno why.			
			jsobj = proxy_class.new_object(parent=parent,py_obj = py_obj) # JS_NewObject(cx, proxy_class.jsc, context.globj, parent)
			if jsobj == None:
				raise SystemError("couldn't look up or create new object")			
		else:
			# ...yes, use existing proxy
			jsobj = proxy_obj.jsobj
		return OBJECT_TO_JSVAL(jsobj)

class Runtime:
	
	def __init__(self, memsize = (8*1024*1024), max_context = 32):

		self.rt = JS_Init(memsize)
		self._cxs = []
                self._max_context = max_context

	def __dealloc__(self):
		JS_Finish(self.rt)
		
	def new_context(self, globj = None, stacksize = 8192):
		context = Context(globj, self, stacksize)
		self._cxs.append(context)
                if len(self._cxs) > self._max_context:
                    old_cx = self._cxs.pop(0)
                    old_cx.alive = False
                    JS_DestroyContext(old_cx.cx)
		context.initialize()
		return context

import sys, inspect

class ProxyObject:
	def __init__(self, obj, jsobj = None):
		self.obj = obj
		self.jsobj = jsobj

def compat_isinstance(obj, tuple_or_obj):
	if type(tuple_or_obj) == TupleType:
		for otherobj in tuple_or_obj:
			if isinstance(obj, otherobj):
				return True
		return False
	return isinstance(obj, tuple_or_obj)

from types import *

class ProxyClass:
	def __init__(self, context, classobject, bind_constructor, is_global, flags):
		self.context = context
		name = js_classname(classobject)
		self.classobject = classobject
		self.jsclass = JSClass()
		self.jsclass.name = name
		self.jsclass.flags = flags
		self.jsclass.addProperty = JS_PropertyStub
		self.jsclass.delProperty = JS_PropertyStub
		self.jsclass.getProperty = self.context._get_property
		self.jsclass.setProperty = self.context._set_property
		self.jsclass.enumerate = JS_EnumerateStub
		if is_global:
			self._resolve_global = JSResolveOp(self.resolve_global)
			self.jsclass.resolve = self._resolve_global
		else:
			self.jsclass.resolve = JS_ResolveStub
		self.jsclass.convert = JS_ConvertStub
		self.jsclass.finalize = JS_FinalizeStub
		
		if bind_constructor:
			self._constructor_cb = JSNative(self.constructor_cb)
			res = JS_InitClass(context.cx, context._global, None, self.jsclass, self._constructor_cb, 0, None, None, None, None)
			assert res, "couldn't initialise JavaScript proxy class"
			
	def resolve_global(self, cx, obj, id):
		#~ cdef Context context
		#~ cdef ProxyObject proxy_obj
		#~ cdef object thing
		#~ cdef object key

		try:			
			proxy_obj = self.context.get_object(obj)
			thing = proxy_obj.obj
			key = Py_from_JS(self.context, id)
			if type(key) == str and hasattr(thing, key):
				attr = getattr(thing, key)
				if compat_isinstance(attr, MethodType):
					self.context.bind_callable(key, attr)
				else:
					self.context.bind_attribute(key, thing, key)
			return JS_TRUE
		except:
			return self.context.report()
		return JS_FALSE
				
	def constructor_cb(self, cx, obj, argc, argv, rval):
		#~ cdef ProxyClass proxy_class
		#~ cdef Context context
		#~ cdef char *fname
		#~ cdef JSFunction *func
		#~ cdef int arg
		#~ cdef ProxyObject object
		func = JS_ValueToFunction(cx, argv[-2])
		if not func:
			msg = "couldn't get JS constructor"
			JS_ReportError(cx, msg)
			return JS_FALSE
		fname = JS_GetFunctionName(func)
		try:
			args = []
			for arg in range(argc):
				args.append(Py_from_JS(cx, argv[arg]))
			if hasattr(self.classobject, "js_constructor"):
				py_rval = self.classobject.js_constructor[0](self.context, *args)
			else:
				py_rval = self.classobject(*args)
			self.context.register_object(py_rval, obj)
		except:
			self.context.report()

		return JS_TRUE

	def new_object(self, parent = None, py_obj = None):
		proto = self.context._global
		jsobj = JS_NewObject(self.context.cx, byref(self.jsclass), proto, parent)
		if py_obj:
			self.context.register_object(py_obj, jsobj)
		return jsobj

stderr = sys.stderr

class DestroyedContext(Exception):
    def __str__(self):
        return "Context Memory has been released previously by Runtime Class sanity checks."

class Context:
	cx = None
	
	class global_class:
		js_name = 'global'
		
	_global = None
	
	def __init__(self, globj, runtime, stacksize):
		self.cx = JS_NewContext(runtime.rt, stacksize)
                self.alive = True
		self.classes = []
		self.objects = []
		self.funcs = []
		#self.runtime = runtime
		self._get_property = JSPropertyOp(self.get_property)
		self._set_property = JSPropertyOp(self.set_property)
		self._bound_method_cb = JSNative(self.bound_method_cb)
		if not globj:
			globj = self.global_class()
		global_class = self.bind_class(globj.__class__, bind_constructor = False, is_global = True)
		self._global = global_class.new_object(py_obj = globj)
		assert self._global
		
	def get_object_from_py(self, py_obj):
		for proxy_obj in self.objects:
			if proxy_obj.obj == py_obj:
				return proxy_obj
		raise ValueError, py_obj
		
	def get_object(self, jsobj):
		for proxy_obj in self.objects:
			if addressof(proxy_obj.jsobj.contents) == addressof(jsobj.contents):
				return proxy_obj
		raise ValueError, jsobj.contents
		
	def get_class(self, name):
		#cdef ProxyClass cl
		for cl in self.classes:
			if cl.jsclass.name == name:
				return cl
		raise ValueError("no class named '%s' is bound" % name)
		
	def get_global(self, name):
		"""Only works with undotted names.  Use eval_script for anything
		else."""
		# XXXX probably best to get rid of this -- eval_script does the job
		#cdef jsval jsv
		if not isstringlike(name):
			raise TypeError("name must be string-like")
		jsv = jsval()
		if not JS_GetProperty(self.cx, self._global, name, byref(jsv)):
			raise SystemError("can't get JavaScript property")
		val = Py_from_JS(self, jsv)
		if val is None:
			raise ValueError("no global named '%s'" % name)
			##         # XXXX why does this hang??
			##             raise AttributeError("%s instance has no attribute '%s'" %
			##                                  (self.__class__.__name__, name))
		else:
			return val

	def register_object(self, obj, jsobj):		
		self.objects.append(ProxyObject(obj, jsobj))
		
	def report(self):
		import traceback
		self.report_error(traceback.format_exc())
		
	def report_error(self, msg, *args):
		JS_ReportError(self.cx, msg, *args)
		
	def error_reporter(self, cx, text, er):
		print >> stderr, text
		
	#def __del__(self):
		#JS_DestroyContext(self.cx)

	def new_method(self, py_method):
		#~ cdef JSFunction *method
		#~ cdef JSObject *method_obj

		# Method (hence its func_name attribute) will go away only when the
		# context is GC'd by Python, because the Python function object is
		# stored in Context extension type instance.  XXX erm, no it isn't:
		# the class instance is kept in the ProxyClass, but the instance's
		# function is not.  Hmm...  XXX also, JS objects exist in runtime,
		# not in context!
		method = JS_NewFunction(self.cx, self._bound_method_cb, 0, 0, None, py_method.func_name)
		method_obj = JS_GetFunctionObject(method)
		return OBJECT_TO_JSVAL(method_obj)
		
	def get_property(self, cx, obj, id, vp):		
		#~ cdef Context context
		#~ cdef ProxyObject proxy_obj
		#~ cdef object thing
		#~ cdef object key

		try:
			key = Py_from_JS(self, id)
			proxy_obj = self.get_object(obj)
			thing = proxy_obj.obj
			if type(key) == IntType:
				try:
					attr = thing[key]
				except:
					pass
				else:
					vp[0] = JS_from_Py(self, obj, attr)
			elif type(key) == StringType:
				if not key.startswith("_"):
					try:
						attr = getattr(thing, key)
					except:
						pass
					else:
						vp[0] = JS_from_Py(self, obj, attr)
			else:
				#in original version: assert False
                                return JS_FALSE
			return JS_TRUE
		except:
			self.report()
		return JS_FALSE
		
	def set_property(self, cx, obj, id, vp):
		#~ cdef Context context
		#~ cdef ProxyObject proxy_obj
		#~ cdef object thing
		#~ cdef object key
		#~ cdef object value
		#~ cdef object attr

		try:
			proxy_obj = self.get_object(obj)

			thing = proxy_obj.obj
			key = Py_from_JS(self, id)
			value = Py_from_JS(self, vp[0])
			if type(key) == IntType:
				try:
					thing[key] = value
				except:
					pass
			elif type(key) == StringType:
				if hasattr(thing, key) and not key.startswith("_"):
					attr = getattr(thing, key)
					if not callable(attr):
						try:
							setattr(thing, key, value)
						except:
							pass
			else:
				assert False
			return JS_TRUE
		except:
			return self.report()

		return JS_FALSE
		
	def bound_method_cb(self, cx, obj, argc, argv, rval):
		#~ cdef Context context
		#~ cdef JSFunction *func
		#~ cdef int arg
		#~ cdef JSClass *jsclass
		#~ cdef ProxyObject proxy_obj

		func = JS_ValueToFunction(cx, argv[-2])
		method_name = JS_GetFunctionName(func)
		jsclass = JS_GetClass(self.cx, obj)

		try:
			proxy_obj = self.get_object(obj)

			py_args = []
			for arg in range(argc):
				py_args.append(Py_from_JS(self, argv[arg]))
			meth = getattr(proxy_obj.obj, method_name)
			py_rval = meth(*py_args)
			rval[0] = JS_from_Py(self, obj, py_rval)
		except:
			return self.report()
		return JS_TRUE

	def get_callback_fn(self, name):
		for cbname, fn in self.funcs:
			if cbname == name:
				return fn
		raise ValueError("no callback function named '%s' is bound" % name)
			
	def function_cb(self, cx, obj, argc, argv, rval):
		#~ cdef JSFunction *jsfunc
		#~ cdef int i
		#~ cdef char *name

		# XXX is this argv[-2] documented anywhere??
		jsfunc = JS_ValueToFunction(cx, argv[-2])
		if not jsfunc:
			return JS_FALSE
		name = JS_GetFunctionName(jsfunc)
		if not name:
			return JS_FALSE

		try:
			callback = self.get_callback_fn(name)
			args = []
			for i in range(argc):
				args.append(Py_from_JS(self, argv[i]))
			pyrval = callback(*args)

			# XXX shouldn't NULL be the JSObject if it's a Python class instance?
			rval[0] = JS_from_Py(self, None, pyrval)
		except:
			return self.report()

		return JS_TRUE
		
	def bind_callable(self, name, function):
		if not callable(function):
			raise ValueError("not a callable object")
		self._function_cb = JSNative(self.function_cb)
		self.funcs.append((name, function))
		JS_DefineFunction(self.cx, self._global, name, self._function_cb, 0, 0)

	def bind_attribute(self, name, obj, attr_name):
		#cdef jsval initial_value
		if not isstringlike(name):
			raise TypeError("name must be string-like")
		if not isstringlike(attr_name):
			raise TypeError("name must be string-like")
		initial_value = JS_from_Py(self, None, getattr(obj, name))
		JS_DefineProperty(self.cx, self._global, name, initial_value, cast(self._get_property,c_void_p), cast(self._set_property,c_void_p), 0)

	def bind_class(self, classobject, bind_constructor = True, is_global = False, flags = 0):
		if not inspect.isclass(classobject): raise TypeError("klass must be a class")
		if not isinteger(flags): raise TypeError("flags must be an integer")
		
		proxy_class = ProxyClass(self, classobject, bind_constructor, is_global, flags)
		self.classes.append(proxy_class)
		return proxy_class
		
	def bind_object(self, name, obj):
		#~ cdef JSObject *jsobj
		#~ cdef ProxyClass proxy_class

		if not isstringlike(name):
			raise TypeError("name must be string-like")

		proxy_class = self.get_class(js_classname(obj))
		jsobj = JS_DefineObject(self.cx, self._global, name, proxy_class.jsclass, None, JSPROP_READONLY)
		if jsobj:
			self.register_object(obj, jsobj)
		else:
			raise ValueError("failed to bind Python object %s" % obj)

	def initialize(self):
		JS_InitStandardClasses(self.cx, self._global)
		self._error_reporter = JSErrorReporter(self.error_reporter)
		JS_SetErrorReporter(self.cx, self._error_reporter)
			
	def eval_script(self, script):
		if not isstringlike(script):
			raise TypeError("name must be string-like")
		if not self.alive:
                    raise DestroyedContext
		rval = jsval()
		if not JS_EvaluateScript(self.cx, self._global, script, len(script), 'Python', 0, byref(rval)):
			raise JSError, "Failed to execute script."
		
		retval = Py_from_JS(self, rval)
		JS_MaybeGC(self.cx)
		return retval

if __name__ == '__main__':
	rt = Runtime()
	cx = rt.new_context()

	class foo:
		def test(self):
			return 1.0

	cx.bind_class(foo, bind_constructor=True)
	f = cx.eval_script("""var f = new foo();
	f.test(); // script return value
	""")
	print f
