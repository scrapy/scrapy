from __future__ import annotations

import copy
import json
from importlib import import_module
from pprint import pformat
from types import ModuleType
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
    Union,
    cast,
)

from scrapy.settings import default_settings

# The key types are restricted in BaseSettings._get_key() to ones supported by JSON,
# see https://github.com/scrapy/scrapy/issues/5383.
_SettingsKeyT = Union[bool, float, int, str, None]

if TYPE_CHECKING:
    # https://github.com/python/typing/issues/445#issuecomment-1131458824
    from _typeshed import SupportsItems

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    _SettingsInputT = Union[SupportsItems[_SettingsKeyT, Any], str, None]


SETTINGS_PRIORITIES: Dict[str, int] = {
    "default": 0,
    "command": 10,
    "addon": 15,
    "project": 20,
    "spider": 30,
    "cmdline": 40,
}


def get_settings_priority(priority: Union[int, str]) -> int:
    """
    Small helper function that looks up a given string priority in the
    :attr:`~scrapy.settings.SETTINGS_PRIORITIES` dictionary and returns its
    numerical value, or directly returns a given numerical priority.
    """
    if isinstance(priority, str):
        return SETTINGS_PRIORITIES[priority]
    return priority


class SettingsAttribute:

    """Class for storing data related to settings attributes.

    This class is intended for internal usage, you should try Settings class
    for settings configuration, not this one.
    """

    def __init__(self, value: Any, priority: int):
        self.value: Any = value
        self.priority: int
        if isinstance(self.value, BaseSettings):
            self.priority = max(self.value.maxpriority(), priority)
        else:
            self.priority = priority

    def set(self, value: Any, priority: int) -> None:
        """Sets value if priority is higher or equal than current priority."""
        if priority >= self.priority:
            if isinstance(self.value, BaseSettings):
                value = BaseSettings(value, priority=priority)
            self.value = value
            self.priority = priority

    def __repr__(self) -> str:
        return f"<SettingsAttribute value={self.value!r} priority={self.priority}>"


class BaseSettings(MutableMapping[_SettingsKeyT, Any]):
    """
    Instances of this class behave like dictionaries, but store priorities
    along with their ``(key, value)`` pairs, and can be frozen (i.e. marked
    immutable).

    Key-value entries can be passed on initialization with the ``values``
    argument, and they would take the ``priority`` level (unless ``values`` is
    already an instance of :class:`~scrapy.settings.BaseSettings`, in which
    case the existing priority levels will be kept).  If the ``priority``
    argument is a string, the priority name will be looked up in
    :attr:`~scrapy.settings.SETTINGS_PRIORITIES`. Otherwise, a specific integer
    should be provided.

    Once the object is created, new settings can be loaded or updated with the
    :meth:`~scrapy.settings.BaseSettings.set` method, and can be accessed with
    the square bracket notation of dictionaries, or with the
    :meth:`~scrapy.settings.BaseSettings.get` method of the instance and its
    value conversion variants. When requesting a stored key, the value with the
    highest priority will be retrieved.
    """

    __default = object()

    def __init__(
        self, values: _SettingsInputT = None, priority: Union[int, str] = "project"
    ):
        self.frozen: bool = False
        self.attributes: dict[_SettingsKeyT, SettingsAttribute] = {}
        if values:
            self.update(values, priority)

    def __getitem__(self, opt_name: _SettingsKeyT) -> Any:
        if opt_name not in self:
            return None
        return self.attributes[opt_name].value

    def __contains__(self, name: Any) -> bool:
        return name in self.attributes

    def get(self, name: _SettingsKeyT, default: Any = None) -> Any:
        """
        Get a setting value without affecting its original type.

        :param name: the setting name
        :type name: str

        :param default: the value to return if no setting is found
        :type default: object
        """
        return self[name] if self[name] is not None else default

    def getbool(self, name: _SettingsKeyT, default: bool = False) -> bool:
        """
        Get a setting value as a boolean.

        ``1``, ``'1'``, `True`` and ``'True'`` return ``True``,
        while ``0``, ``'0'``, ``False``, ``'False'`` and ``None`` return ``False``.

        For example, settings populated through environment variables set to
        ``'0'`` will return ``False`` when using this method.

        :param name: the setting name
        :type name: str

        :param default: the value to return if no setting is found
        :type default: object
        """
        got = self.get(name, default)
        try:
            return bool(int(got))
        except ValueError:
            if got in ("True", "true"):
                return True
            if got in ("False", "false"):
                return False
            raise ValueError(
                "Supported values for boolean settings "
                "are 0/1, True/False, '0'/'1', "
                "'True'/'False' and 'true'/'false'"
            )

    def getint(self, name: _SettingsKeyT, default: int = 0) -> int:
        """
        Get a setting value as an int.

        :param name: the setting name
        :type name: str

        :param default: the value to return if no setting is found
        :type default: object
        """
        return int(self.get(name, default))

    def getfloat(self, name: _SettingsKeyT, default: float = 0.0) -> float:
        """
        Get a setting value as a float.

        :param name: the setting name
        :type name: str

        :param default: the value to return if no setting is found
        :type default: object
        """
        return float(self.get(name, default))

    def getlist(
        self, name: _SettingsKeyT, default: Optional[List[Any]] = None
    ) -> List[Any]:
        """
        Get a setting value as a list. If the setting original type is a list, a
        copy of it will be returned. If it's a string it will be split by ",".

        For example, settings populated through environment variables set to
        ``'one,two'`` will return a list ['one', 'two'] when using this method.

        :param name: the setting name
        :type name: str

        :param default: the value to return if no setting is found
        :type default: object
        """
        value = self.get(name, default or [])
        if isinstance(value, str):
            value = value.split(",")
        return list(value)

    def getdict(
        self, name: _SettingsKeyT, default: Optional[Dict[Any, Any]] = None
    ) -> Dict[Any, Any]:
        """
        Get a setting value as a dictionary. If the setting original type is a
        dictionary, a copy of it will be returned. If it is a string it will be
        evaluated as a JSON dictionary. In the case that it is a
        :class:`~scrapy.settings.BaseSettings` instance itself, it will be
        converted to a dictionary, containing all its current settings values
        as they would be returned by :meth:`~scrapy.settings.BaseSettings.get`,
        and losing all information about priority and mutability.

        :param name: the setting name
        :type name: str

        :param default: the value to return if no setting is found
        :type default: object
        """
        value = self.get(name, default or {})
        if isinstance(value, str):
            value = json.loads(value)
        return dict(value)

    def getdictorlist(
        self,
        name: _SettingsKeyT,
        default: Union[Dict[Any, Any], List[Any], Tuple[Any], None] = None,
    ) -> Union[Dict[Any, Any], List[Any]]:
        """Get a setting value as either a :class:`dict` or a :class:`list`.

        If the setting is already a dict or a list, a copy of it will be
        returned.

        If it is a string it will be evaluated as JSON, or as a comma-separated
        list of strings as a fallback.

        For example, settings populated from the command line will return:

        -   ``{'key1': 'value1', 'key2': 'value2'}`` if set to
            ``'{"key1": "value1", "key2": "value2"}'``

        -   ``['one', 'two']`` if set to ``'["one", "two"]'`` or ``'one,two'``

        :param name: the setting name
        :type name: string

        :param default: the value to return if no setting is found
        :type default: any
        """
        value = self.get(name, default)
        if value is None:
            return {}
        if isinstance(value, str):
            try:
                value_loaded = json.loads(value)
                assert isinstance(value_loaded, (dict, list))
                return value_loaded
            except ValueError:
                return value.split(",")
        if isinstance(value, tuple):
            return list(value)
        assert isinstance(value, (dict, list))
        return copy.deepcopy(value)

    def getwithbase(self, name: _SettingsKeyT) -> "BaseSettings":
        """Get a composition of a dictionary-like setting and its `_BASE`
        counterpart.

        :param name: name of the dictionary-like setting
        :type name: str
        """
        if not isinstance(name, str):
            raise ValueError(f"Base setting key must be a string, got {name}")
        compbs = BaseSettings()
        compbs.update(self[name + "_BASE"])
        compbs.update(self[name])
        return compbs

    def getpriority(self, name: _SettingsKeyT) -> Optional[int]:
        """
        Return the current numerical priority value of a setting, or ``None`` if
        the given ``name`` does not exist.

        :param name: the setting name
        :type name: str
        """
        if name not in self:
            return None
        return self.attributes[name].priority

    def maxpriority(self) -> int:
        """
        Return the numerical value of the highest priority present throughout
        all settings, or the numerical value for ``default`` from
        :attr:`~scrapy.settings.SETTINGS_PRIORITIES` if there are no settings
        stored.
        """
        if len(self) > 0:
            return max(cast(int, self.getpriority(name)) for name in self)
        return get_settings_priority("default")

    def __setitem__(self, name: _SettingsKeyT, value: Any) -> None:
        self.set(name, value)

    def set(
        self, name: _SettingsKeyT, value: Any, priority: Union[int, str] = "project"
    ) -> None:
        """
        Store a key/value attribute with a given priority.

        Settings should be populated *before* configuring the Crawler object
        (through the :meth:`~scrapy.crawler.Crawler.configure` method),
        otherwise they won't have any effect.

        :param name: the setting name
        :type name: str

        :param value: the value to associate with the setting
        :type value: object

        :param priority: the priority of the setting. Should be a key of
            :attr:`~scrapy.settings.SETTINGS_PRIORITIES` or an integer
        :type priority: str or int
        """
        self._assert_mutability()
        priority = get_settings_priority(priority)
        if name not in self:
            if isinstance(value, SettingsAttribute):
                self.attributes[name] = value
            else:
                self.attributes[name] = SettingsAttribute(value, priority)
        else:
            self.attributes[name].set(value, priority)

    def setdefault(
        self,
        name: _SettingsKeyT,
        default: Any = None,
        priority: Union[int, str] = "project",
    ) -> Any:
        if name not in self:
            self.set(name, default, priority)
            return default

        return self.attributes[name].value

    def setdict(
        self, values: _SettingsInputT, priority: Union[int, str] = "project"
    ) -> None:
        self.update(values, priority)

    def setmodule(
        self, module: Union[ModuleType, str], priority: Union[int, str] = "project"
    ) -> None:
        """
        Store settings from a module with a given priority.

        This is a helper function that calls
        :meth:`~scrapy.settings.BaseSettings.set` for every globally declared
        uppercase variable of ``module`` with the provided ``priority``.

        :param module: the module or the path of the module
        :type module: types.ModuleType or str

        :param priority: the priority of the settings. Should be a key of
            :attr:`~scrapy.settings.SETTINGS_PRIORITIES` or an integer
        :type priority: str or int
        """
        self._assert_mutability()
        if isinstance(module, str):
            module = import_module(module)
        for key in dir(module):
            if key.isupper():
                self.set(key, getattr(module, key), priority)

    # BaseSettings.update() doesn't support all inputs that MutableMapping.update() supports
    def update(self, values: _SettingsInputT, priority: Union[int, str] = "project") -> None:  # type: ignore[override]
        """
        Store key/value pairs with a given priority.

        This is a helper function that calls
        :meth:`~scrapy.settings.BaseSettings.set` for every item of ``values``
        with the provided ``priority``.

        If ``values`` is a string, it is assumed to be JSON-encoded and parsed
        into a dict with ``json.loads()`` first. If it is a
        :class:`~scrapy.settings.BaseSettings` instance, the per-key priorities
        will be used and the ``priority`` parameter ignored. This allows
        inserting/updating settings with different priorities with a single
        command.

        :param values: the settings names and values
        :type values: dict or string or :class:`~scrapy.settings.BaseSettings`

        :param priority: the priority of the settings. Should be a key of
            :attr:`~scrapy.settings.SETTINGS_PRIORITIES` or an integer
        :type priority: str or int
        """
        self._assert_mutability()
        if isinstance(values, str):
            values = cast(dict, json.loads(values))
        if values is not None:
            if isinstance(values, BaseSettings):
                for name, value in values.items():
                    self.set(name, value, cast(int, values.getpriority(name)))
            else:
                for name, value in values.items():
                    self.set(name, value, priority)

    def delete(
        self, name: _SettingsKeyT, priority: Union[int, str] = "project"
    ) -> None:
        if name not in self:
            raise KeyError(name)
        self._assert_mutability()
        priority = get_settings_priority(priority)
        if priority >= cast(int, self.getpriority(name)):
            del self.attributes[name]

    def __delitem__(self, name: _SettingsKeyT) -> None:
        self._assert_mutability()
        del self.attributes[name]

    def _assert_mutability(self) -> None:
        if self.frozen:
            raise TypeError("Trying to modify an immutable Settings object")

    def copy(self) -> "Self":
        """
        Make a deep copy of current settings.

        This method returns a new instance of the :class:`Settings` class,
        populated with the same values and their priorities.

        Modifications to the new object won't be reflected on the original
        settings.
        """
        return copy.deepcopy(self)

    def freeze(self) -> None:
        """
        Disable further changes to the current settings.

        After calling this method, the present state of the settings will become
        immutable. Trying to change values through the :meth:`~set` method and
        its variants won't be possible and will be alerted.
        """
        self.frozen = True

    def frozencopy(self) -> "Self":
        """
        Return an immutable copy of the current settings.

        Alias for a :meth:`~freeze` call in the object returned by :meth:`copy`.
        """
        copy = self.copy()
        copy.freeze()
        return copy

    def __iter__(self) -> Iterator[_SettingsKeyT]:
        return iter(self.attributes)

    def __len__(self) -> int:
        return len(self.attributes)

    def _to_dict(self) -> Dict[_SettingsKeyT, Any]:
        return {
            self._get_key(k): (v._to_dict() if isinstance(v, BaseSettings) else v)
            for k, v in self.items()
        }

    def _get_key(self, key_value: Any) -> _SettingsKeyT:
        return (
            key_value
            if isinstance(key_value, (bool, float, int, str, type(None)))
            else str(key_value)
        )

    def copy_to_dict(self) -> Dict[_SettingsKeyT, Any]:
        """
        Make a copy of current settings and convert to a dict.

        This method returns a new dict populated with the same values
        and their priorities as the current settings.

        Modifications to the returned dict won't be reflected on the original
        settings.

        This method can be useful for example for printing settings
        in Scrapy shell.
        """
        settings = self.copy()
        return settings._to_dict()

    # https://ipython.readthedocs.io/en/stable/config/integrating.html#pretty-printing
    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            p.text(repr(self))
        else:
            p.text(pformat(self.copy_to_dict()))

    def pop(self, name: _SettingsKeyT, default: Any = __default) -> Any:
        try:
            value = self.attributes[name].value
        except KeyError:
            if default is self.__default:
                raise

            return default
        else:
            self.__delitem__(name)
            return value


class Settings(BaseSettings):
    """
    This object stores Scrapy settings for the configuration of internal
    components, and can be used for any further customization.

    It is a direct subclass and supports all methods of
    :class:`~scrapy.settings.BaseSettings`. Additionally, after instantiation
    of this class, the new object will have the global default settings
    described on :ref:`topics-settings-ref` already populated.
    """

    def __init__(
        self, values: _SettingsInputT = None, priority: Union[int, str] = "project"
    ):
        # Do not pass kwarg values here. We don't want to promote user-defined
        # dicts, and we want to update, not replace, default dicts with the
        # values given by the user
        super().__init__()
        self.setmodule(default_settings, "default")
        # Promote default dictionaries to BaseSettings instances for per-key
        # priorities
        for name, val in self.items():
            if isinstance(val, dict):
                self.set(name, BaseSettings(val, "default"), "default")
        self.update(values, priority)


def iter_default_settings() -> Iterable[Tuple[str, Any]]:
    """Return the default settings as an iterator of (name, value) tuples"""
    for name in dir(default_settings):
        if name.isupper():
            yield name, getattr(default_settings, name)


def overridden_settings(
    settings: Mapping[_SettingsKeyT, Any]
) -> Iterable[Tuple[str, Any]]:
    """Return an iterable of the settings that have been overridden"""
    for name, defvalue in iter_default_settings():
        value = settings[name]
        if not isinstance(defvalue, dict) and value != defvalue:
            yield name, value
