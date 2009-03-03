class DeclarativeMeta(type):
    """Metaclass for declarative objects"""

    def __new__(meta, class_name, bases, attrs):
        cls = type.__new__(meta, class_name, bases, attrs)
        cls.__classinit__.im_func(cls, attrs)
        return cls


class Declarative(object):
    """Base class for declarative objects"""

    __metaclass__ = DeclarativeMeta

    def __classinit__(cls, attrs): 
        """Override this method to initialize your class"""
        pass

