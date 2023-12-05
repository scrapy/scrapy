"""Robust apply mechanism

Provides a function "call", which can sort out
what arguments a given callable object can take,
and subset the given arguments to match only
those which are acceptable.
"""
import sys
if sys.hexversion >= 0x3000000:
    im_func = '__func__'
    im_self = '__self__'
    im_code = '__code__'
    func_code = '__code__'
else:
    im_func = 'im_func'
    im_self = 'im_self'
    im_code = 'im_code'
    func_code = 'func_code'

def function( receiver ):
    """Get function-like callable object for given receiver

    returns (function_or_method, codeObject, fromMethod)

    If fromMethod is true, then the callable already
    has its first argument bound
    """
    if hasattr(receiver, '__call__'):
        # Reassign receiver to the actual method that will be called.
        if hasattr( receiver.__call__, im_func) or hasattr( receiver.__call__, im_code):
            receiver = receiver.__call__
    if hasattr( receiver, im_func ):
        # an instance-method...
        return receiver, getattr(getattr(receiver, im_func), func_code), 1
    elif not hasattr( receiver, func_code):
        raise ValueError('unknown reciever type %s %s'%(receiver, type(receiver)))
    return receiver, getattr(receiver,func_code), 0

def robustApply(receiver, *arguments, **named):
    """Call receiver with arguments and an appropriate subset of named
    """
    receiver, codeObject, startIndex = function( receiver )
    acceptable = codeObject.co_varnames[startIndex+len(arguments):codeObject.co_argcount]
    for name in codeObject.co_varnames[startIndex:startIndex+len(arguments)]:
        if name in named:
            raise TypeError(
                """Argument %r specified both positionally and as a keyword for calling %r"""% (
                    name, receiver,
                )
            )
    if not (codeObject.co_flags & 8):
        # fc does not have a **kwds type parameter, therefore 
        # remove unacceptable arguments.
        named = dict([(k,v) for k,v in named.items() if k in acceptable])
    return receiver(*arguments, **named)
