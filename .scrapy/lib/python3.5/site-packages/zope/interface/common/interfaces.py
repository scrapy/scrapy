##############################################################################
#
# Copyright (c) 2003 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Interfaces for standard python exceptions
"""
from zope.interface import Interface
from zope.interface import classImplements

class IException(Interface): pass
class IStandardError(IException): pass
class IWarning(IException): pass
class ISyntaxError(IStandardError): pass
class ILookupError(IStandardError): pass
class IValueError(IStandardError): pass
class IRuntimeError(IStandardError): pass
class IArithmeticError(IStandardError): pass
class IAssertionError(IStandardError): pass
class IAttributeError(IStandardError): pass
class IDeprecationWarning(IWarning): pass
class IEOFError(IStandardError): pass
class IEnvironmentError(IStandardError): pass
class IFloatingPointError(IArithmeticError): pass
class IIOError(IEnvironmentError): pass
class IImportError(IStandardError): pass
class IIndentationError(ISyntaxError): pass
class IIndexError(ILookupError): pass
class IKeyError(ILookupError): pass
class IKeyboardInterrupt(IStandardError): pass
class IMemoryError(IStandardError): pass
class INameError(IStandardError): pass
class INotImplementedError(IRuntimeError): pass
class IOSError(IEnvironmentError): pass
class IOverflowError(IArithmeticError): pass
class IOverflowWarning(IWarning): pass
class IReferenceError(IStandardError): pass
class IRuntimeWarning(IWarning): pass
class IStopIteration(IException): pass
class ISyntaxWarning(IWarning): pass
class ISystemError(IStandardError): pass
class ISystemExit(IException): pass
class ITabError(IIndentationError): pass
class ITypeError(IStandardError): pass
class IUnboundLocalError(INameError): pass
class IUnicodeError(IValueError): pass
class IUserWarning(IWarning): pass
class IZeroDivisionError(IArithmeticError): pass

classImplements(ArithmeticError, IArithmeticError)
classImplements(AssertionError, IAssertionError)
classImplements(AttributeError, IAttributeError)
classImplements(DeprecationWarning, IDeprecationWarning)
classImplements(EnvironmentError, IEnvironmentError)
classImplements(EOFError, IEOFError)
classImplements(Exception, IException)
classImplements(FloatingPointError, IFloatingPointError)
classImplements(ImportError, IImportError)
classImplements(IndentationError, IIndentationError)
classImplements(IndexError, IIndexError)
classImplements(IOError, IIOError)
classImplements(KeyboardInterrupt, IKeyboardInterrupt)
classImplements(KeyError, IKeyError)
classImplements(LookupError, ILookupError)
classImplements(MemoryError, IMemoryError)
classImplements(NameError, INameError)
classImplements(NotImplementedError, INotImplementedError)
classImplements(OSError, IOSError)
classImplements(OverflowError, IOverflowError)
try:
    classImplements(OverflowWarning, IOverflowWarning)
except NameError:  #pragma NO COVER
    pass # OverflowWarning was removed in Python 2.5
classImplements(ReferenceError, IReferenceError)
classImplements(RuntimeError, IRuntimeError)
classImplements(RuntimeWarning, IRuntimeWarning)
try:
    classImplements(StandardError, IStandardError)
except NameError:  #pragma NO COVER
    pass # StandardError does not exist in Python 3
classImplements(StopIteration, IStopIteration)
classImplements(SyntaxError, ISyntaxError)
classImplements(SyntaxWarning, ISyntaxWarning)
classImplements(SystemError, ISystemError)
classImplements(SystemExit, ISystemExit)
classImplements(TabError, ITabError)
classImplements(TypeError, ITypeError)
classImplements(UnboundLocalError, IUnboundLocalError)
classImplements(UnicodeError, IUnicodeError)
classImplements(UserWarning, IUserWarning)
classImplements(ValueError, IValueError)
classImplements(Warning, IWarning)
classImplements(ZeroDivisionError, IZeroDivisionError)

