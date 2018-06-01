# -*- coding: utf-8 -*-
import warnings

from functools import wraps
from scrapy.exceptions import ScrapyDeprecationWarning
from six import create_bound_method

from .generator import RequestGenerator
from .utils import get_args


__author__ = 'Rolando Espinoza'
__email__ = 'rolando at rmax.io'
__version__ = '0.3.1'

__all__ = ['inline_requests']


def inline_requests(method_or_func):
    """A decorator to use coroutine-like spider callbacks.

    Example:

    .. code:: python

        class MySpider(Spider):

            @inline_callbacks
            def parse(self, response):
                next_url = response.urjoin('?next')
                try:
                    next_resp = yield Request(next_url)
                except Exception as e:
                    self.logger.exception("An error occurred.")
                    return
                else:
                    yield {"next_url": next_resp.url}


    You must conform with the following conventions:

    * The decorated method must be a spider method.
    * The decorated method must use the ``yield`` keyword or return a generator.
    * The decorated method must accept ``response`` as the first argument.
    * The decorated method should yield ``Request`` objects without neither
      ``callback`` nor ``errback`` set.

    If your requests don't come back to the generator try setting the flag to
    handle all http statuses:

    .. code:: python

                request.meta['handle_httpstatus_all'] = True

    """
    args = get_args(method_or_func)
    if not args:
        raise TypeError("Function must accept at least one argument.")
    # XXX: hardcoded convention of 'self' as first argument for methods
    if args[0] == 'self':
        def wrapper(self, response, **kwargs):
            callback = create_bound_method(method_or_func, self)
            genwrapper = RequestGenerator(callback, **kwargs)
            try:
                return genwrapper(response).__await__()
            except :
                return genwrapper(response)
    else:
        '''warnings.warn("Decorating a non-method function will be deprecated",
                      ScrapyDeprecationWarning, stacklevel=1)'''

        def wrapper(response, **kwargs):
            genwrapper = RequestGenerator(method_or_func, **kwargs)
            
            try:
                return genwrapper(response)
            except:
                return genwrapper(response)

    return wraps(method_or_func)(wrapper)
