"""Robust apply mechanism

Provides a function "call", which can sort out
what arguments a given callable object can take,
and subset the given arguments to match only
those which are acceptable.
"""
import six


def function(receiver):
    """Get function-like callable object for given receiver
    returns (function_or_method, codeObject, fromMethod).
    If fromMethod is true, then the callable already
    has its first argument bound.
    """
    if hasattr(receiver, '__call__'):
        # receiver is a class instance; assume it is callable.
        # Reassign receiver to the actual method that will be called.
        if hasattr(receiver.__call__, '__func__') \
                or hasattr(receiver.__call__, '__code__'):
            receiver = receiver.__call__
    if hasattr(receiver, '__func__'):
        # an instance-method...
        return receiver, receiver.__code__, True
    elif not hasattr(receiver, '__code__'):
        raise ValueError('unknown reciever type %s %s' %
                         (receiver, type(receiver)))
    return receiver, receiver.__code__, False


def robust_apply(receiver, *arguments, **named):
    """Call receiver with arguments and an appropriate subset of named
    """
    receiver, codeObject, startIndex = function(receiver)
    acceptable = codeObject.co_varnames[startIndex+len(arguments):
                                        codeObject.co_argcount]
    for name in codeObject.co_varnames[startIndex:startIndex+len(arguments)]:
        if name in named:
            raise TypeError(
                """Argument %r specified both positionally and"""
                """as a keyword for calling %r""" % (
                    name, receiver,
                )
            )
    if not (codeObject.co_flags & 8):
        # fc does not have a **kwds type parameter, therefore
        # remove unacceptable arguments.
        for arg in list(named):
            if arg not in acceptable:
                del named[arg]
    return receiver(*arguments, **named)
