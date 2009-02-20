from scrapy.utils.python import get_func_args


class ItemExtractor(object):
    def __init__(self, response=None, item=None):
        if item:
            self.item_instance = item
        else:
            self.item_instance = self.item_class()
        
        self._response = response
        self._field_extractors = self._get_field_extractors()

    def _get_field_extractors(self):
        fe = {}
        for field in self.item_instance._fields.keys():
            if self.__class__.__dict__.has_key(field):
                fe[field] = self.__class__.__dict__[field]
        return fe

    def __setattr__(self, name, value):
        if (name.startswith('_') or name == 'item_instance'):
            return object.__setattr__(self, name, value)

        try:
            fieldextractor = self._field_extractors[name]
        except KeyError:
            raise AttributeError(name)

        adaptor_args = {'response': self._response}
        final = fieldextractor(value, adaptor_args=adaptor_args)
        setattr(self.item_instance, name, final)

    def __getattribute__(self, name):
        if not (name.startswith('_') or name.startswith('item_')):
            return getattr(self.item_instance, name)
        else:
            return object.__getattribute__(self, name)


class ExtractorField(object):
    def __init__(self, funcs):
        if not hasattr(funcs, '__iter__'):
            raise TypeError(
                'You must initialize ExtractorField with a list of callables')

        self._funcs = []

        for func in funcs:
            func_args = get_func_args(func)
            takes_args = True if 'adaptor_args' in func_args else False
            self._funcs.append((func, takes_args))

    def __call__(self, value, adaptor_args=None):
        values = [value]

        for func, takes_args in self._funcs:
            next_round = []

            for val in values:
                val = func(val, adaptor_args) if takes_args else func(val)

                if isinstance(val, tuple):
                    next_round.extend(val)
                elif val is not None:
                    next_round.append(val)

            values = next_round

        return list(values)


def treeadapt(*funcs, **adaptor_args):
    pipe_adaptor_args = adaptor_args
    _funcs = []
    for func in funcs:
        takes_args = 'adaptor_args' in get_func_args(func)
        _funcs.append((func, takes_args))

    def _adaptor(value, adaptor_args=None):
        values = value if isinstance(value, (list, tuple)) else [value]
        pipe_adaptor_args.update(adaptor_args or {})
        pipe_kwargs = {'adaptor_args': pipe_adaptor_args}

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


