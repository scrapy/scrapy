
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import get_func_args


def adaptize(func):
    func_args = get_func_args(func)
    if 'adaptor_args' in func_args:
        return func

    def _adaptor(value, adaptor_args):
        return func(value)
    return _adaptor


def IDENTITY(v):
    return v


class ItemAdaptorMeta(type):
    def __new__(meta, class_name, bases, attrs):
        da = attrs.get('default_adaptor')
        if da:
            attrs['default_adaptor'] = staticmethod(adaptize(da))

        cls = type.__new__(meta, class_name, bases, attrs)

        cls._field_adaptors = cls._field_adaptors.copy()
    
        if cls.item_class:
            for item_field in cls.item_class.fields.keys():
                if item_field in attrs:
                    adaptor = adaptize(attrs[item_field])
                    cls._field_adaptors[item_field] = adaptor
                    setattr(cls, item_field, staticmethod(adaptor))
        return cls

    def __getattr__(cls, name):
        if name in cls.item_class.fields:
            return cls.default_adaptor
        raise AttributeError(name)


class ItemAdaptor(object):
    __metaclass__ = ItemAdaptorMeta

    item_class = None
    default_adaptor = IDENTITY

    _field_adaptors = {}

    def __init__(self, response=None, item=None):
        self.item_instance = item if item else self.item_class()
        self._response = response

    def __setattr__(self, name, value):
        if (name.startswith('_') or name == 'item_instance' \
                or name == 'default_adaptor'):
            return object.__setattr__(self, name, value)

        fa = self._field_adaptors.get(name, self.default_adaptor)

        adaptor_args = {'response': self._response, 'item': self.item_instance}
        ovalue = fa(value, adaptor_args=adaptor_args)
        setattr(self.item_instance, name, ovalue)

    def __getattribute__(self, name):
        if (name.startswith('_') or name.startswith('item_') \
                or name == 'default_adaptor'):
            return object.__getattribute__(self, name)

        return getattr(self.item_instance, name)


def adaptor(*funcs, **default_adaptor_args):
    """A pipe adaptor implementing the tree adaption logic

    It takes multiples unnamed arguments used as functions of the pipe, and
    keywords used as adaptor_args to be passed to functions that supports it

    If an adaptor function returns a list of values, each value is used as
    input for next adaptor function

    Always returns a list of values
    """

    _funcs = []
    for func in funcs:
        accepts_args = 'adaptor_args' in get_func_args(func)
        _funcs.append((func, accepts_args))

    def _adaptor(value, adaptor_args=None):
        values = arg_to_iter(value)
        aargs = default_adaptor_args
        if adaptor_args:
            aargs = aargs.copy()
            aargs.update(adaptor_args)
        pipe_kwargs = {'adaptor_args': aargs}
        for func, accepts_args in _funcs:
            next = []
            kwargs = pipe_kwargs if accepts_args else {}
            for val in values:
                val = func(val, **kwargs)
                if hasattr(val, '__iter__'):
                    next.extend(val)
                elif val is not None:
                    next.append(val)
            values = next
        return list(values)

    return _adaptor

