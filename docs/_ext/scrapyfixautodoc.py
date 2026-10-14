"""
Must be included after 'sphinx.ext.autodoc'. Fixes unwanted 'alias of' behavior.
https://github.com/sphinx-doc/sphinx/issues/4422
"""

from typing import Any

# pylint: disable=import-error
from sphinx.application import Sphinx
from sphinx.util import inspect

from scrapy.utils.trackref import object_ref


def maybe_skip_member(app: Sphinx, what, name: str, obj, skip: bool, options) -> bool:
    if not skip:
        # autodoc was generating the text "alias of" for the following members
        return name in {"default_item_class", "default_selector_class"}
    return skip


def _stringify(app: Sphinx, func) -> str:
    return inspect.stringify_signature(
        inspect.signature(func, bound_method=True),
        show_return_annotation=False,
        unqualified_typehints=app.config.autodoc_typehints_format == "short",
    )


def fix_object_ref_signature(
    app: Sphinx, what: str, name: str, obj, options, signature, return_annotation
) -> tuple[str, str] | None:
    # autodoc takes class signatures from __new__ before __init__, and
    # object_ref.__new__ accepts any arguments.
    if (
        what == "class"
        and issubclass(obj, object_ref)
        and obj.__init__ is not object.__init__
        and signature == _stringify(app, object_ref.__new__)
    ):
        return _stringify(app, obj.__init__), return_annotation
    return None


def setup(app: Sphinx) -> dict[str, Any]:
    app.connect("autodoc-process-signature", fix_object_ref_signature)
    app.connect("autodoc-skip-member", maybe_skip_member)
    return {"parallel_read_safe": True}
