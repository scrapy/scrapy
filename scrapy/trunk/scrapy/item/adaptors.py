import inspect

from traceback import format_exc
from scrapy.conf import settings

class AdaptorPipe(list):
    """
    Class that represents an item's attribute pipeline.

    This class is itself a list, filled by adaptors to be run
    in order to filter the input.
    """
    def __init__(self, adaptors):
        super(AdaptorPipe, self).__init__([adaptor for adaptor in adaptors if callable(adaptor)])

    def __call__(self, value, **kwargs):
        """
        Execute the adaptor pipeline for this attribute.
        """
        debug = kwargs.pop('debug', all([settings.getbool('LOG_ENABLED'), settings.get('LOGLEVEL') == 'TRACE']))

        for adaptor in self:
            if inspect.isfunction(adaptor):
                func_args, _, _ ,_ = inspect.getargspec(adaptor)
            else:
                func_args = []

            name = getattr(adaptor, 'func_name', None)
            if not name:
                name = adaptor.__class__.__name__ if hasattr(adaptor, '__class__') else adaptor.__name__

            try:
                if debug:
                    print "  %07s | input >" % name, repr(value)

                if 'adaptor_args' in func_args:
                    value = adaptor(value, kwargs)
                else:
                    value = adaptor(value)

                if debug:
                    print "  %07s | output >" % name, repr(value)
            except Exception:
                print "Error in '%s' adaptor. Traceback text:" % name
                print format_exc()
                return

        return value

    def __add__(self, other):
        if isinstance(other, list):
            return AdaptorPipe(super(AdaptorPipe, self).__add__(other))
        elif callable(other):
            return AdaptorPipe(self + [other])

def adaptize(adaptor, my_args=None):
    """
    This decorator helps you add to your pipelines adaptors that are able
    to receive extra keyword arguments from the spiders.

    If my_args is None, it'll try to guess the arguments your adaptor receives
    by instropection, and if it can't guess them, it will act as if it were a normal
    adaptor.
    To do the last, you may also call adaptize with my_args = [], or @adaptize([])
    """
    if my_args is None:
        if inspect.isfunction(adaptor):
            my_args, _, _, _ = inspect.getargspec(adaptor)
        else:
            my_args = []

    def _adaptor(value, adaptor_args):
        kwargs = dict((key, val) for key, val in adaptor_args.items() if key in my_args)
        return adaptor(value, **kwargs)
    return _adaptor
