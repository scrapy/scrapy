# https://github.com/david-salac/classutilities/issues/1
# Unmodified copy of
# https://github.com/david-salac/classutilities/blob/a6e4a86331936d432afaa454ed4c963528165a61/src/classutilities/classproperty.py

# Allows creating a class level property
from typing import Any, Callable, Optional, Union


class ClassPropertyContainer:
    """
    Allows creating a class level property (functionality for
    decorator).
    """

    def __init__(self, prop_get: Any, prop_set: Any = None):
        """
        Container that allows having a class property decorator.
        :param prop_get: Class property getter.
        :param prop_set: Class property setter.
        """
        self.prop_get: Any = prop_get
        self.prop_set: Any = prop_set

    def __get__(self, obj: Any, cls: Optional[type] = None) -> Callable:
        """
        Get the property getter.
        :param obj: Instance of the class.
        :param cls: Type of the class.
        :return: Class property getter.
        """
        if cls is None:
            cls = type(obj)
        return self.prop_get.__get__(obj, cls)()

    def __set__(self, obj, value) -> Callable:
        """
        Get the property setter.
        :param obj: Instance of the class.
        :param value: A value to be set.
        :return: Class property setter.
        """
        if not self.prop_set:
            raise AttributeError("cannot set attribute")
        _type: type = type(obj)
        if _type == ClassPropertyMetaClass:
            _type = obj
        return self.prop_set.__get__(obj, _type)(value)

    def setter(
        self, func: Union[Callable, classmethod, staticmethod]
    ) -> "ClassPropertyContainer":
        """
        Allows creating setter in a property like way.
        :param func: Getter function.
        :return: Setter object for the decorator.
        """
        if not isinstance(func, (classmethod, staticmethod)):
            func = classmethod(func)
        self.prop_set = func
        return self


def classproperty(func):
    """
    Create a decorator for a class level property.
    :param func: This class method is decorated.
    :return: Modified class method behaving like a class property.
    """
    if not isinstance(func, (classmethod, staticmethod)):
        # The method must be a classmethod (or staticmethod)
        func = classmethod(func)
    return ClassPropertyContainer(func)


class ClassPropertyMetaClass(type):
    """
    Metaclass that allows creating a standard setter.
    """

    def __setattr__(self, key, value):
        """Overloads setter for class"""
        if key in self.__dict__:
            obj = self.__dict__.get(key)
        if obj and type(obj) is ClassPropertyContainer:
            return obj.__set__(self, value)

        return super().__setattr__(key, value)


class ClassPropertiesMixin(metaclass=ClassPropertyMetaClass):
    """
    This mixin allows using class properties setter (getter works
    correctly even without this mixin)
    """

    pass
