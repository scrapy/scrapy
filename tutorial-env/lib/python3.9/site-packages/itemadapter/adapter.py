import dataclasses
from abc import abstractmethod, ABCMeta
from collections import deque
from collections.abc import KeysView, MutableMapping
from types import MappingProxyType
from typing import Any, Deque, Iterator, Type, Optional, List

from itemadapter.utils import (
    _get_pydantic_model_metadata,
    _is_attrs_class,
    _is_pydantic_model,
)

from itemadapter._imports import attr, _scrapy_item_classes


__all__ = [
    "AdapterInterface",
    "AttrsAdapter",
    "DataclassAdapter",
    "DictAdapter",
    "ItemAdapter",
    "PydanticAdapter",
    "ScrapyItemAdapter",
]


class AdapterInterface(MutableMapping, metaclass=ABCMeta):
    """Abstract Base Class for adapters.

    An adapter that handles a specific type of item should inherit from this
    class and implement the abstract methods defined here, plus the
    abtract methods inherited from the MutableMapping base class.
    """

    def __init__(self, item: Any) -> None:
        self.item = item

    @classmethod
    @abstractmethod
    def is_item_class(cls, item_class: type) -> bool:
        """Return True if the adapter can handle the given item class, False otherwise."""
        raise NotImplementedError()

    @classmethod
    def is_item(cls, item: Any) -> bool:
        """Return True if the adapter can handle the given item, False otherwise."""
        return cls.is_item_class(item.__class__)

    @classmethod
    def get_field_meta_from_class(cls, item_class: type, field_name: str) -> MappingProxyType:
        return MappingProxyType({})

    @classmethod
    def get_field_names_from_class(cls, item_class: type) -> Optional[List[str]]:
        """Return a list of fields defined for ``item_class``.
        If a class doesn't support fields, None is returned."""
        return None

    def get_field_meta(self, field_name: str) -> MappingProxyType:
        """Return metadata for the given field name, if available."""
        return self.get_field_meta_from_class(self.item.__class__, field_name)

    def field_names(self) -> KeysView:
        """Return a dynamic view of the item's field names."""
        return self.keys()  # type: ignore[return-value]


class _MixinAttrsDataclassAdapter:

    _fields_dict: dict
    item: Any

    def get_field_meta(self, field_name: str) -> MappingProxyType:
        return self._fields_dict[field_name].metadata

    def field_names(self) -> KeysView:
        return KeysView(self._fields_dict)

    def __getitem__(self, field_name: str) -> Any:
        if field_name in self._fields_dict:
            return getattr(self.item, field_name)
        raise KeyError(field_name)

    def __setitem__(self, field_name: str, value: Any) -> None:
        if field_name in self._fields_dict:
            setattr(self.item, field_name, value)
        else:
            raise KeyError(f"{self.item.__class__.__name__} does not support field: {field_name}")

    def __delitem__(self, field_name: str) -> None:
        if field_name in self._fields_dict:
            try:
                delattr(self.item, field_name)
            except AttributeError:
                raise KeyError(field_name)
        else:
            raise KeyError(f"{self.item.__class__.__name__} does not support field: {field_name}")

    def __iter__(self) -> Iterator:
        return iter(attr for attr in self._fields_dict if hasattr(self.item, attr))

    def __len__(self) -> int:
        return len(list(iter(self)))


class AttrsAdapter(_MixinAttrsDataclassAdapter, AdapterInterface):
    def __init__(self, item: Any) -> None:
        super().__init__(item)
        if attr is None:
            raise RuntimeError("attr module is not available")
        # store a reference to the item's fields to avoid O(n) lookups and O(n^2) traversals
        self._fields_dict = attr.fields_dict(self.item.__class__)

    @classmethod
    def is_item(cls, item: Any) -> bool:
        return _is_attrs_class(item) and not isinstance(item, type)

    @classmethod
    def is_item_class(cls, item_class: type) -> bool:
        return _is_attrs_class(item_class)

    @classmethod
    def get_field_meta_from_class(cls, item_class: type, field_name: str) -> MappingProxyType:
        if attr is None:
            raise RuntimeError("attr module is not available")
        try:
            return attr.fields_dict(item_class)[field_name].metadata  # type: ignore
        except KeyError:
            raise KeyError(f"{item_class.__name__} does not support field: {field_name}")

    @classmethod
    def get_field_names_from_class(cls, item_class: type) -> Optional[List[str]]:
        if attr is None:
            raise RuntimeError("attr module is not available")
        return [a.name for a in attr.fields(item_class)]


class DataclassAdapter(_MixinAttrsDataclassAdapter, AdapterInterface):
    def __init__(self, item: Any) -> None:
        super().__init__(item)
        # store a reference to the item's fields to avoid O(n) lookups and O(n^2) traversals
        self._fields_dict = {field.name: field for field in dataclasses.fields(self.item)}

    @classmethod
    def is_item(cls, item: Any) -> bool:
        return dataclasses.is_dataclass(item) and not isinstance(item, type)

    @classmethod
    def is_item_class(cls, item_class: type) -> bool:
        return dataclasses.is_dataclass(item_class)

    @classmethod
    def get_field_meta_from_class(cls, item_class: type, field_name: str) -> MappingProxyType:
        for field in dataclasses.fields(item_class):
            if field.name == field_name:
                return field.metadata  # type: ignore
        raise KeyError(f"{item_class.__name__} does not support field: {field_name}")

    @classmethod
    def get_field_names_from_class(cls, item_class: type) -> Optional[List[str]]:
        return [a.name for a in dataclasses.fields(item_class)]


class PydanticAdapter(AdapterInterface):

    item: Any

    @classmethod
    def is_item_class(cls, item_class: type) -> bool:
        return _is_pydantic_model(item_class)

    @classmethod
    def get_field_meta_from_class(cls, item_class: type, field_name: str) -> MappingProxyType:
        try:
            return _get_pydantic_model_metadata(item_class, field_name)
        except KeyError:
            raise KeyError(f"{item_class.__name__} does not support field: {field_name}")

    @classmethod
    def get_field_names_from_class(cls, item_class: type) -> Optional[List[str]]:
        return list(item_class.__fields__.keys())  # type: ignore[attr-defined]

    def field_names(self) -> KeysView:
        return KeysView(self.item.__fields__)

    def __getitem__(self, field_name: str) -> Any:
        if field_name in self.item.__fields__:
            return getattr(self.item, field_name)
        raise KeyError(field_name)

    def __setitem__(self, field_name: str, value: Any) -> None:
        if field_name in self.item.__fields__:
            setattr(self.item, field_name, value)
        else:
            raise KeyError(f"{self.item.__class__.__name__} does not support field: {field_name}")

    def __delitem__(self, field_name: str) -> None:
        if field_name in self.item.__fields__:
            try:
                delattr(self.item, field_name)
            except AttributeError:
                raise KeyError(field_name)
        else:
            raise KeyError(f"{self.item.__class__.__name__} does not support field: {field_name}")

    def __iter__(self) -> Iterator:
        return iter(attr for attr in self.item.__fields__ if hasattr(self.item, attr))

    def __len__(self) -> int:
        return len(list(iter(self)))


class _MixinDictScrapyItemAdapter:

    _fields_dict: dict
    item: Any

    def __getitem__(self, field_name: str) -> Any:
        return self.item[field_name]

    def __setitem__(self, field_name: str, value: Any) -> None:
        self.item[field_name] = value

    def __delitem__(self, field_name: str) -> None:
        del self.item[field_name]

    def __iter__(self) -> Iterator:
        return iter(self.item)

    def __len__(self) -> int:
        return len(self.item)


class DictAdapter(_MixinDictScrapyItemAdapter, AdapterInterface):
    @classmethod
    def is_item(cls, item: Any) -> bool:
        return isinstance(item, dict)

    @classmethod
    def is_item_class(cls, item_class: type) -> bool:
        return issubclass(item_class, dict)

    def field_names(self) -> KeysView:
        return KeysView(self.item)


class ScrapyItemAdapter(_MixinDictScrapyItemAdapter, AdapterInterface):
    @classmethod
    def is_item(cls, item: Any) -> bool:
        return isinstance(item, _scrapy_item_classes)

    @classmethod
    def is_item_class(cls, item_class: type) -> bool:
        return issubclass(item_class, _scrapy_item_classes)

    @classmethod
    def get_field_meta_from_class(cls, item_class: type, field_name: str) -> MappingProxyType:
        return MappingProxyType(item_class.fields[field_name])  # type: ignore[attr-defined]

    @classmethod
    def get_field_names_from_class(cls, item_class: type) -> Optional[List[str]]:
        return list(item_class.fields.keys())  # type: ignore[attr-defined]

    def field_names(self) -> KeysView:
        return KeysView(self.item.fields)


class ItemAdapter(MutableMapping):
    """Wrapper class to interact with data container objects. It provides a common interface
    to extract and set data without having to take the object's type into account.
    """

    ADAPTER_CLASSES: Deque[Type[AdapterInterface]] = deque(
        [
            ScrapyItemAdapter,
            DictAdapter,
            DataclassAdapter,
            AttrsAdapter,
            PydanticAdapter,
        ]
    )

    def __init__(self, item: Any) -> None:
        for cls in self.ADAPTER_CLASSES:
            if cls.is_item(item):
                self.adapter = cls(item)
                break
        else:
            raise TypeError(f"No adapter found for objects of type: {type(item)} ({item})")

    @classmethod
    def is_item(cls, item: Any) -> bool:
        for adapter_class in cls.ADAPTER_CLASSES:
            if adapter_class.is_item(item):
                return True
        return False

    @classmethod
    def is_item_class(cls, item_class: type) -> bool:
        for adapter_class in cls.ADAPTER_CLASSES:
            if adapter_class.is_item_class(item_class):
                return True
        return False

    @classmethod
    def _get_adapter_class(cls, item_class: type) -> Type[AdapterInterface]:
        for adapter_class in cls.ADAPTER_CLASSES:
            if adapter_class.is_item_class(item_class):
                return adapter_class
        raise TypeError(f"{item_class} is not a valid item class")

    @classmethod
    def get_field_meta_from_class(cls, item_class: type, field_name: str) -> MappingProxyType:
        adapter_class = cls._get_adapter_class(item_class)
        return adapter_class.get_field_meta_from_class(item_class, field_name)

    @classmethod
    def get_field_names_from_class(cls, item_class: type) -> Optional[List[str]]:
        adapter_class = cls._get_adapter_class(item_class)
        return adapter_class.get_field_names_from_class(item_class)

    @property
    def item(self) -> Any:
        return self.adapter.item

    def __repr__(self) -> str:
        values = ", ".join([f"{key}={value!r}" for key, value in self.items()])
        return f"<{self.__class__.__name__} for {self.item.__class__.__name__}({values})>"

    def __getitem__(self, field_name: str) -> Any:
        return self.adapter.__getitem__(field_name)

    def __setitem__(self, field_name: str, value: Any) -> None:
        self.adapter.__setitem__(field_name, value)

    def __delitem__(self, field_name: str) -> None:
        self.adapter.__delitem__(field_name)

    def __iter__(self) -> Iterator:
        return self.adapter.__iter__()

    def __len__(self) -> int:
        return self.adapter.__len__()

    def get_field_meta(self, field_name: str) -> MappingProxyType:
        """Return metadata for the given field name."""
        return self.adapter.get_field_meta(field_name)

    def field_names(self) -> KeysView:
        """Return read-only key view with the names of all the defined fields for the item."""
        return self.adapter.field_names()

    def asdict(self) -> dict:
        """Return a dict object with the contents of the adapter. This works slightly different
        than calling `dict(adapter)`: it's applied recursively to nested items (if there are any).
        """
        return {key: self._asdict(value) for key, value in self.items()}

    @classmethod
    def _asdict(cls, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {key: cls._asdict(value) for key, value in obj.items()}
        if isinstance(obj, (list, set, tuple)):
            return obj.__class__(cls._asdict(x) for x in obj)
        if isinstance(obj, cls):
            return obj.asdict()
        if cls.is_item(obj):
            return cls(obj).asdict()
        return obj
