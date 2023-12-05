from functools import partial
from typing import Dict, Any, Sequence, Callable, Optional

from django.db.models import Model

from . import compare as base_compare
from .comparison import _compare_mapping, register, CompareContext, unspecified, Registry


def instance_fields(instance):
    opts = instance._meta
    for name in (
        'concrete_fields',
        'virtual_fields',
        'private_fields',
    ):
        fields = getattr(opts, name, None)
        if fields:
            for field in fields:
                yield field


def model_to_dict(
        instance: Any,
        exclude: Sequence[str],
        include_not_editable: bool,
) -> Dict[str, Any]:
    data = {}
    for f in instance_fields(instance):
        if f.name in exclude:
            continue
        if not getattr(f, 'editable', False) and not include_not_editable:
            continue
        data[f.name] = f.value_from_object(instance)
    return data


def compare_model(x, y, context: CompareContext):
    """
    Returns an informative string describing the differences between the two
    supplied Django model instances. The way in which this comparison is
    performed can be controlled using the following parameters:

    :param ignore_fields:
      A sequence of fields to ignore during comparison, most commonly
      set to ``['id']``. By default, no fields are ignored.

    :param non_editable_fields:
      If `True`, then fields with ``editable=False`` will be included in the
      comparison. By default, these fields are ignored.
    """
    ignore_fields = context.get_option('ignore_fields', set())
    non_editable_fields= context.get_option('non_editable_fields', False)
    args = []
    for obj in x, y:
        args.append(model_to_dict(obj, ignore_fields, non_editable_fields))
    args.append(context)
    args.append(x)
    return _compare_mapping(*args)


register(Model, compare_model)


def compare(
        *args,
        x: Any = unspecified,
        y: Any = unspecified,
        expected: Any = unspecified,
        actual: Any = unspecified,
        prefix: str = None,
        suffix: str = None,
        x_label: str = None,
        y_label: str = None,
        raises: bool = True,
        recursive: bool = True,
        strict: bool = False,
        ignore_eq: bool = True,
        comparers: Registry = None,
        **options: Any
) -> Optional[str]:
    """
    This is identical to :func:`~testfixtures.compare`, but with ``ignore=True``
    automatically set to make comparing django :class:`~django.db.models.Model`
    instances easier.
    """
    return base_compare(
        *args,
        x=x,
        y=y,
        expected=expected,
        actual=actual,
        prefix=prefix,
        suffix=suffix,
        x_label=x_label,
        y_label=y_label,
        raises=raises,
        recursive=recursive,
        strict=strict,
        ignore_eq=ignore_eq,
        comparers=comparers,
        **options
    )
