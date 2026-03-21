"""
Must be included after 'sphinx.ext.autodoc'. Fixes unwanted 'alias of' behavior.
https://github.com/sphinx-doc/sphinx/issues/4422
"""

# pylint: disable=import-error
from sphinx.application import Sphinx


def maybe_skip_member(app: Sphinx, what, name: str, obj, skip: bool, options) -> bool:
    if not skip:
        # autodocs was generating a text "alias of" for the following members
        return name in {"default_item_class", "default_selector_class"}
    return skip


def setup(app: Sphinx) -> None:
    app.connect("autodoc-skip-member", maybe_skip_member)
