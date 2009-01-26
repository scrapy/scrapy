import inspect

from traceback import format_exc
from scrapy.conf import settings

class AdaptorFunc(object):
    """
    This is a private class that the AdaptorPipe uses to store
    its adaptation functions and their attributes.
    """
    def __init__(self, adaptor):
        self.adaptor = adaptor

        if inspect.isfunction(adaptor):
            self.func_args, _, _, _ = inspect.getargspec(adaptor)
        elif hasattr(adaptor, '__call__'):
            try:
                self.func_args, _, _, _ = inspect.getargspec(adaptor.__call__)
            except Exception:
                self.func_args = []

        self.name = getattr(adaptor, 'func_name', None)
        if not self.name:
            if hasattr(adaptor, '__class__') and adaptor.__class__ is not type:
                self.name = adaptor.__class__.__name__
            else:
                self.name = adaptor.__name__

    def __call__(self, value, kwargs):
        if 'adaptor_args' in self.func_args:
            return self.adaptor(value, kwargs)
        else:
            return self.adaptor(value)

    def __repr__(self):
        return '<Adaptor %s >' % self.name

class AdaptorPipe(list):
    """
    Class that represents an item's attribute pipeline.

    This class is itself a list, filled by adaptors to be run
    in order to filter the input.
    """
    def __init__(self, adaptors):
        def _filter_adaptor(adaptor):
            return AdaptorFunc(adaptor) if not isinstance(adaptor, AdaptorFunc) else adaptor

        if not hasattr(adaptors, '__iter__'):
            raise TypeError('You must provide AdaptorPipe a list of adaptors')

        for adaptor in adaptors:
            if not callable(adaptor):
                raise TypeError("%s is not a callable" % adaptor)
        super(AdaptorPipe, self).__init__(map(_filter_adaptor, adaptors))
        self.debug = settings.getbool('ADAPTORS_DEBUG')

    def __call__(self, value, kwargs=None):
        """
        Execute the adaptor pipeline for this attribute.
        """

        debug_padding = 0
        values = [value]

        for adaptor in self:
            next_round = []
            for val in values:
                try:
                    if self.debug:
                        print "%sinput | %s <" % (' ' * debug_padding, adaptor.name), repr(val)

                    val = adaptor(val, kwargs or {})
                    if isinstance(val, tuple):
                        next_round.extend(val)
                    else:
                        next_round.append(val)

                    if self.debug:
                        print "%soutput | %s >" % (' ' * debug_padding, adaptor.name), repr(val)
                except Exception:
                    print "Error in '%s' adaptor. Traceback text:" % adaptor.name
                    print format_exc()
                    return

            debug_padding += 2
            values = next_round

        return tuple(values)

    def __add__(self, other):
        if callable(other):
            other = [other]
        elif hasattr(other, '__iter__'):
            other = list(other)
        return AdaptorPipe(super(AdaptorPipe, self).__add__(other))

    def __repr__(self):
        return '<AdaptorPipe %s >' % super(AdaptorPipe, self).__repr__()

    def add_adaptor(self, adaptor, position=None):
        if callable(adaptor):
            if not isinstance(adaptor, AdaptorFunc):
                adaptor = AdaptorFunc(adaptor)
            if position is None:
                self.append(adaptor)
            else:
                self.insert(position, adaptor)

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
