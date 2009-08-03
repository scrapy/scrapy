from collections import defaultdict

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import get_func_args


class BuilderField(object):

    def __init__(self, *args, **kwargs):
        self.expander = self.tree_expander(*args)
        self.reducer = kwargs.get('reducer')

    def tree_expander(self, *funcs, **default_expander_args):
        """A pipe expander implementing tree logic

        It takes multiples unnamed arguments used as functions of the pipe, and
        keywords used as expander_args to be passed to functions that supports it

        If an expander function returns a list of values, each value is used as
        input for next expander function

        Always returns a list of values
        """

        _funcs = []
        for func in funcs:
            accepts_args = 'expander_args' in get_func_args(func)
            _funcs.append((func, accepts_args))

        def _expander(value, expander_args=None):
            values = arg_to_iter(value)
            aargs = default_expander_args
            if expander_args:
                aargs = aargs.copy()
                aargs.update(expander_args)
            pipe_kwargs = {'expander_args': aargs}
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

        return _expander


class ItemBuilderMeta(type):
    def __new__(mcs, class_name, bases, attrs):
        cls = type.__new__(mcs, class_name, bases, attrs)
        cls._builder_fields = cls._builder_fields.copy()
    
        if cls.item_class:
            for name, field in cls.item_class.fields.iteritems():
                bfield = None
                if name in attrs:
                    bfield = attrs[name] 
                else:
                    if name not in cls._builder_fields and cls.default_builder:
                        bfield = cls.default_builder
                        #actually add the field to the class
                        setattr(cls, name, bfield)
                if bfield:
                    cls._builder_fields.add(name)
        return cls


class ItemBuilder(object):
    __metaclass__ = ItemBuilderMeta

    item_class = None
    default_builder = None

    _builder_fields = set()

    def __init__(self, response=None, item=None, **expander_args):
        self._response = response
        self._item = item if item else self.item_class()

        self._expander_args = {'response': self._response}
        if expander_args:
            self._expander_args.update(expander_args)

        self._values = defaultdict(list)

    def add_value(self, field_name, value, **new_expander_args):
        field = self._get_builder_field(field_name)
        evalue = self._expand_value(field, value, **new_expander_args)
        self._values[field_name].extend(evalue)

    def get_item(self):
        item = self._item
        for field in self._values:
            item[field] = self.get_value(field)
        return item

    def get_value(self, field_name):
        field = self._get_builder_field(field_name)
        reducer = field.reducer or self._item.fields[field_name].from_unicode_list 
        return reducer(self._values[field_name])

    def replace_value(self, field_name, value, **new_expander_args):
        field = self._get_builder_field(field_name)
        evalue = self._expand_value(field, value, **new_expander_args)
        self._values[field_name] = evalue

    def _get_builder_field(self, name):
        if name not in self._builder_fields:
            raise KeyError

        return getattr(self, name)

    def _expand_value(self, field, value, **new_expander_args):
        if new_expander_args:
            expander_args = self._expander_args.copy()
            expander_args.update(new_expander_args)
        else:
            expander_args = self._expander_args

        evalue = field.expander(value, expander_args=expander_args)

        if not isinstance(evalue, list):
            evalue = [evalue]

        return evalue

