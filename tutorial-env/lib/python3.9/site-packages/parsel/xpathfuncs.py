import re
from typing import Any, Callable, Optional

from lxml import etree

from w3lib.html import HTML5_WHITESPACE


regex = f"[{HTML5_WHITESPACE}]+"
replace_html5_whitespaces = re.compile(regex).sub


def set_xpathfunc(fname: str, func: Optional[Callable]) -> None:  # type: ignore[type-arg]
    """Register a custom extension function to use in XPath expressions.

    The function ``func`` registered under ``fname`` identifier will be called
    for every matching node, being passed a ``context`` parameter as well as
    any parameters passed from the corresponding XPath expression.

    If ``func`` is ``None``, the extension function will be removed.

    See more `in lxml documentation`_.

    .. _`in lxml documentation`: https://lxml.de/extensions.html#xpath-extension-functions

    """
    ns_fns = etree.FunctionNamespace(None)  # type: ignore[attr-defined]
    if func is not None:
        ns_fns[fname] = func
    else:
        del ns_fns[fname]


def setup() -> None:
    set_xpathfunc("has-class", has_class)


def has_class(context: Any, *classes: str) -> bool:
    """has-class function.

    Return True if all ``classes`` are present in element's class attr.

    """
    if not context.eval_context.get("args_checked"):
        if not classes:
            raise ValueError(
                "XPath error: has-class must have at least 1 argument"
            )
        for c in classes:
            if not isinstance(c, str):
                raise ValueError(
                    "XPath error: has-class arguments must be strings"
                )
        context.eval_context["args_checked"] = True

    node_cls = context.context_node.get("class")
    if node_cls is None:
        return False
    node_cls = " " + node_cls + " "
    node_cls = replace_html5_whitespaces(" ", node_cls)
    for cls in classes:
        if " " + cls + " " not in node_cls:
            return False
    return True
