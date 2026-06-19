# https://github.com/david-salac/classutilities/issues/1
# Modified copy of
# https://github.com/david-salac/classutilities/blob/a6e4a86331936d432afaa454ed4c963528165a61/src/classutilities/classproperty.py

# Allows creating a class level property
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


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

    def __get__(self, obj: Any, cls: type | None = None) -> Any:
        """
        Return the value of the class property.
        :param obj: Instance of the class.
        :param cls: Type of the class.
        :return: Value of the class property.
        """
        if cls is None:
            cls = type(obj)
        return self.prop_get.__get__(obj, cls)()

    def __set__(self, obj: Any, value: Any) -> None:
        """
        Set the value of the class property.
        :param obj: Instance of the class.
        :param value: A value to be set.
        """
        if not self.prop_set:
            raise AttributeError("cannot set attribute")
        _type: type = type(obj)
        if _type == ClassPropertyMetaClass:
            _type = obj
        self.prop_set.__get__(obj, _type)(value)

    def setter(
        self,
        func: Callable[..., Any] | classmethod[Any, Any, Any] | staticmethod[Any, Any],
    ) -> ClassPropertyContainer:
        """
        Allows creating setter in a property like way.
        :param func: Setter function.
        :return: Setter object for the decorator.
        """
        if not isinstance(func, (classmethod, staticmethod)):
            func = classmethod(func)
        self.prop_set = func
        return self


def classproperty(
    func: Callable[..., Any] | classmethod[Any, Any, Any] | staticmethod[Any, Any],
) -> ClassPropertyContainer:
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

    def __setattr__(cls, key: str, value: Any) -> None:
        """Overloads setter for class"""
        obj = None
        if key in cls.__dict__:
            obj = cls.__dict__.get(key)
        if obj and isinstance(obj, ClassPropertyContainer):
            return obj.__set__(cls, value)

        return super().__setattr__(key, value)


class ClassPropertiesMixin(metaclass=ClassPropertyMetaClass):
    """
    This mixin allows using class properties setter (getter works
    correctly even without this mixin)
    """
