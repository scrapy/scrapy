from scrapy.contrib_exp.newitem.declarative import Declarative
from scrapy.utils.python import get_func_args


def adaptize(func):
    func_args = get_func_args(func)
    if 'adaptor_args' in func_args:
        return func

    def _adaptor(value, adaptor_args):
        return func(value)
    return _adaptor


class ItemAdaptor(Declarative):

    item_class = None
    default_adaptor = None
    field_adaptors = {}

    def __classinit__(cls, attrs):
        def set_adaptor(cls, name, func):
            adaptor = adaptize(func)
            cls.field_adaptors[name] = adaptor
            # define adaptor as a staticmethod
            setattr(cls, name, staticmethod(adaptor))

        cls.field_adaptors = cls.field_adaptors.copy()
        if cls.item_class:
            # set new adaptors
            for n, v in attrs.items():
                if n in cls.item_class.fields.keys():
                    set_adaptor(cls, n, v)
            
            # if default_adaptor is set, use it for the unadapted fields
            if cls.default_adaptor:
                for field in cls.item_class.fields.keys():
                    if field not in cls.field_adaptors.keys():
                        set_adaptor(cls, field, cls.default_adaptor.im_func)

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
            return setattr(self.item_instance, name, value)

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


