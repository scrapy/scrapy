# -*- coding: utf-8 -*-
import warnings

from functools import wraps,partial
from scrapy.exceptions import ScrapyDeprecationWarning
from six import create_bound_method

from .generator import RequestGenerator
from .utils import get_args

__all__ = ['inline_requests']


def inline_requests(method_or_func,crawler,spider):
    #A decorator to use coroutine-like spider callbacks.

    args = get_args(method_or_func)
    if not args:
        raise TypeError("Function must accept at least one argument.")
    # XXX: hardcoded convention of 'self' as first argument for methods
    if args[0] == 'self':
        def wrapper(self, response,crawler,spider, **kwargs):
            callback = create_bound_method(method_or_func, self)
            genwrapper = RequestGenerator(callback,crawler,spider, **kwargs)
            try:
                return genwrapper(response).__await__()
            except :
                return genwrapper(response)
    else:
        '''warnings.warn("Decorating a non-method function will be deprecated",
                      ScrapyDeprecationWarning, stacklevel=1)'''

        def wrapper(response,crawler,spider, **kwargs):
            genwrapper = RequestGenerator(method_or_func,crawler,spider, **kwargs)
            
            try:
                return genwrapper(response)
            except:
                return genwrapper(response)

    return wraps(method_or_func)(partial(wrapper,crawler=crawler,spider=spider))
