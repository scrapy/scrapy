import warnings

from types import MappingProxyType
from typing import Any

from itemadapter._imports import attr, pydantic


__all__ = ["is_item", "get_field_meta_from_class"]


def _is_attrs_class(obj: Any) -> bool:
    if attr is None:
        return False
    return attr.has(obj)


def _is_pydantic_model(obj: Any) -> bool:
    if pydantic is None:
        return False
    return issubclass(obj, pydantic.BaseModel)


def _get_pydantic_model_metadata(item_model: Any, field_name: str) -> MappingProxyType:
    metadata = {}
    field = item_model.__fields__[field_name].field_info

    for attribute in [
        "alias",
        "title",
        "description",
        "const",
        "gt",
        "ge",
        "lt",
        "le",
        "multiple_of",
        "min_items",
        "max_items",
        "min_length",
        "max_length",
        "regex",
    ]:
        value = getattr(field, attribute)
        if value is not None:
            metadata[attribute] = value
    if not field.allow_mutation:
        metadata["allow_mutation"] = field.allow_mutation
    metadata.update(field.extra)

    return MappingProxyType(metadata)


def is_item(obj: Any) -> bool:
    """Return True if the given object belongs to one of the supported types, False otherwise.

    Alias for ItemAdapter.is_item
    """
    from itemadapter.adapter import ItemAdapter

    return ItemAdapter.is_item(obj)


def get_field_meta_from_class(item_class: type, field_name: str) -> MappingProxyType:
    """Return a read-only mapping with metadata for the given field name, within the given
    item class. If there is no metadata for the field, or the item class does not support
    field metadata, an empty object is returned.

    Field metadata is taken from different sources, depending on the item type:
    * scrapy.item.Item: corresponding scrapy.item.Field object
    * dataclass items: "metadata" attribute for the corresponding field
    * attrs items: "metadata" attribute for the corresponding field
    * pydantic models: corresponding pydantic.field.FieldInfo/ModelField object

    The returned value is an instance of types.MappingProxyType, i.e. a dynamic read-only view
    of the original mapping, which gets automatically updated if the original mapping changes.
    """

    from itemadapter.adapter import ItemAdapter

    return ItemAdapter.get_field_meta_from_class(item_class, field_name)


# deprecated


def is_dataclass_instance(obj: Any) -> bool:
    warnings.warn(
        "itemadapter.utils.is_dataclass_instance is deprecated"
        " and it will be removed in a future version",
        category=DeprecationWarning,
        stacklevel=2,
    )
    from itemadapter.adapter import DataclassAdapter

    return DataclassAdapter.is_item(obj)


def is_attrs_instance(obj: Any) -> bool:
    warnings.warn(
        "itemadapter.utils.is_attrs_instance is deprecated"
        " and it will be removed in a future version",
        category=DeprecationWarning,
        stacklevel=2,
    )
    from itemadapter.adapter import AttrsAdapter

    return AttrsAdapter.is_item(obj)


def is_pydantic_instance(obj: Any) -> bool:
    warnings.warn(
        "itemadapter.utils.is_pydantic_instance is deprecated"
        " and it will be removed in a future version",
        category=DeprecationWarning,
        stacklevel=2,
    )
    from itemadapter.adapter import PydanticAdapter

    return PydanticAdapter.is_item(obj)


def is_scrapy_item(obj: Any) -> bool:
    warnings.warn(
        "itemadapter.utils.is_scrapy_item is deprecated"
        " and it will be removed in a future version",
        category=DeprecationWarning,
        stacklevel=2,
    )
    from itemadapter.adapter import ScrapyItemAdapter

    return ScrapyItemAdapter.is_item(obj)
