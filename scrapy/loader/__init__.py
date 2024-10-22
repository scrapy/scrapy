"""
Item Loader

See documentation in docs/topics/loaders.rst
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import itemloaders

from scrapy.item import Item
from scrapy.selector import Selector

if TYPE_CHECKING:
    from scrapy.http import TextResponse


class ItemLoader(itemloaders.ItemLoader):
    """
    A user-friendly abstraction to populate an :ref:`item <topics-items>` with data
    by applying :ref:`field processors <topics-loaders-processors>` to scraped data.
    When instantiated with a ``selector`` or a ``response`` it supports
    data extraction from web pages using :ref:`selectors <topics-selectors>`.

    :param item: The item instance to populate using subsequent calls to
        :meth:`~ItemLoader.add_xpath`, :meth:`~ItemLoader.add_css`,
        or :meth:`~ItemLoader.add_value`.
    :type item: scrapy.item.Item

    :param selector: The selector to extract data from, when using the
        :meth:`add_xpath`, :meth:`add_css`, :meth:`replace_xpath`, or
        :meth:`replace_css` method.
    :type selector: :class:`~scrapy.selector.Selector` object

    :param response: The response used to construct the selector using the
        :attr:`default_selector_class`, unless the selector argument is given,
        in which case this argument is ignored.
    :type response: :class:`~scrapy.http.Response` object

    If no item is given, one is instantiated automatically using the class in
    :attr:`default_item_class`.

    The item, selector, response and remaining keyword arguments are
    assigned to the Loader context (accessible through the :attr:`context` attribute).

    .. attribute:: item

        The item object being parsed by this Item Loader.
        This is mostly used as a property so, when attempting to override this
        value, you may want to check out :attr:`default_item_class` first.

    .. attribute:: context

        The currently active :ref:`Context <loaders-context>` of this Item Loader.

    .. attribute:: default_item_class

        An :ref:`item <topics-items>` class (or factory), used to instantiate
        items when not given in the ``__init__`` method.

    .. attribute:: default_input_processor

        The default input processor to use for those fields which don't specify
        one.

    .. attribute:: default_output_processor

        The default output processor to use for those fields which don't specify
        one.

    .. attribute:: default_selector_class

        The class used to construct the :attr:`selector` of this
        :class:`ItemLoader`, if only a response is given in the ``__init__`` method.
        If a selector is given in the ``__init__`` method this attribute is ignored.
        This attribute is sometimes overridden in subclasses.

    .. attribute:: selector

        The :class:`~scrapy.selector.Selector` object to extract data from.
        It's either the selector given in the ``__init__`` method or one created from
        the response given in the ``__init__`` method using the
        :attr:`default_selector_class`. This attribute is meant to be
        read-only.
    """

    default_item_class: type = Item
    default_selector_class = Selector

    def __init__(
        self,
        item: Any = None,
        selector: Selector | None = None,
        response: TextResponse | None = None,
        parent: itemloaders.ItemLoader | None = None,
        **context: Any,
    ):
        if selector is None and response is not None:
            try:
                selector = self.default_selector_class(response)
            except AttributeError:
                selector = None
        context.update(response=response)
        super().__init__(item=item, selector=selector, parent=parent, **context)
