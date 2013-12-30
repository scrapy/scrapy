"""Some helpers for deprecation messages"""

import warnings
import inspect
from scrapy.exceptions import ScrapyDeprecationWarning

def attribute(obj, oldattr, newattr, version='0.12'):
    cname = obj.__class__.__name__
    warnings.warn("%s.%s attribute is deprecated and will be no longer supported "
        "in Scrapy %s, use %s.%s attribute instead" % \
        (cname, oldattr, version, cname, newattr), ScrapyDeprecationWarning, stacklevel=3)


def deprecated_base_class(new_class, message=None, category=ScrapyDeprecationWarning):
    """
    Return a metaclass that causes classes to issue a warning when
    they are subclassed.

    In addition to that, subclasses of ``new_class`` are considered subclasses
    of a class this metaclass is applied to.

    It can be used to rename a base class of some user classes, e.g. if we
    have

        class OldName(SomeClass):
            # ...

    and we want to rename it to NewName, we can do the following::

        class NewName(SomeClass):
            # ...

        class OldName(NewName):
            __metaclass__ = deprecated_base_class(NewName, "OldName is deprecated. Please inherit from NewName.")

    Then, if user class inherits from OldName, warning is issued. Also, if
    some code uses ``issubclass(sub, OldName)`` or ``isinstance(sub(), OldName)``
    checks they'll still return True if sub is a subclass of NewName instead of
    OldName.
    """
    class Metaclass(type):
        def __init__(cls, name, bases, clsdict):

            if not issubclass(cls, new_class):
                raise ValueError("first parameter of `warn_when_subclassed` must be a superclass of %s" % cls)

            warn_message = message
            if warn_message is None:
                # XXX: how to get a name of deprecated base class?
                cls_name = cls.__module__ + '.' + name
                new_name = new_class.__module__ + '.' + new_class.__name__
                warn_message = "Base class of %s was deprecated. Please inherit from %s." % (cls_name, new_name)

            if len(cls.mro()) > len(new_class.mro()) + 1:
                warnings.warn(warn_message, category, stacklevel=2)
            super(Metaclass, cls).__init__(name, bases, clsdict)

        # see http://www.python.org/dev/peps/pep-3119/#overloading-isinstance-and-issubclass
        # and http://docs.python.org/2/reference/datamodel.html#customizing-instance-and-subclass-checks
        # for implementation details
        def __instancecheck__(cls, inst):
            return any(cls.__subclasscheck__(c)
                       for c in {type(inst), inst.__class__})

        def __subclasscheck__(cls, sub):
            if not inspect.isclass(sub):
                raise TypeError("issubclass() arg 1 must be a class")

            mro = getattr(sub, '__mro__', ())
            candidates = {cls, new_class}
            return any(c in candidates for c in mro)

    return Metaclass

