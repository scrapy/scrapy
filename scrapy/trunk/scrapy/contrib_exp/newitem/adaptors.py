from scrapy.contrib_exp.newitem.declarative import Declarative
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

        cls.field_adaptors = cls.field_adaptors.copy()
    
        if cls.item_class:
            for item_field in cls.item_class.fields.keys():
                if item_field in attrs:
                    adaptor = adaptize(attrs[item_field])
                    cls.field_adaptors[item_field] = adaptor
                    setattr(cls, item_field, staticmethod(adaptor))

        return cls

    def __getattr__(cls, name):
        if name in cls.item_class.fields:
            return cls.default_adaptor

        raise AttributeError


class ItemAdaptor(object):
    __metaclass__ = ItemAdaptorMeta

    item_class = None
    field_adaptors = {}
    default_adaptor = IDENTITY

    def __init__(self, response=None, item=None):
        self.item_instance = item if item else self.item_class()
        self._response = response

    def __setattr__(self, name, value):
        if (name.startswith('_') or name == 'item_instance' \
            or name == 'default_adaptor' or name == 'field_adaptors'):
            return object.__setattr__(self, name, value)

        try:
            fa = self.field_adaptors[name]
        except KeyError:
            fa = self.default_adaptor

        adaptor_args = {'response': self._response, 'item': self.item_instance}
        ovalue = fa(value, adaptor_args=adaptor_args)
        setattr(self.item_instance, name, ovalue)

    def __getattribute__(self, name):
        if (name.startswith('_') or name.startswith('item_') \
            or name == 'default_adaptor' or name == 'field_adaptors'):
            return object.__getattribute__(self, name)

        return getattr(self.item_instance, name)


def adaptor(*funcs, **adaptor_args):
    """A pipe adaptor implementing the tree adaption logic

    It takes multiples unnamed arguments used as functions of the pipe, and
    keywords used as adaptor_args to be passed to functions that supports it

    If an adaptor function returns a list of values, each value is used as
    input for next adaptor function

    Always returns a list of values
    """

    pipe_adaptor_args = adaptor_args
    _funcs = []
    for func in funcs:
        takes_args = 'adaptor_args' in get_func_args(func)
        _funcs.append((func, takes_args))

    def _adaptor(value, adaptor_args=None):
        values = value if isinstance(value, (list, tuple)) else [value]
        aargs = dict(t for d in [pipe_adaptor_args, adaptor_args or {}] for t in d.items())
        pipe_kwargs = {'adaptor_args': aargs}

        for func, takes_args in _funcs:
            next = []
            kwargs = pipe_kwargs if takes_args else {}

            for val in values:
                val = func(val, **kwargs)

                if isinstance(val, (list, tuple)):
                    next.extend(val)
                elif val is not None:
                    next.append(val)

            values = next
        return list(values)

    return _adaptor


