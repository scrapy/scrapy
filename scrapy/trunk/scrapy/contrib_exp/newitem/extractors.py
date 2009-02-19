import inspect


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
        if not (name.startswith('_') or name == 'item_instance'):
            if name in self._field_extractors.keys():
                setattr(self.item_instance, name, 
                        self._field_extractors[name](value, self._response))
            else:
                raise AttributeError(name)
        else:
            object.__setattr__(self, name, value)

    def __getattribute__(self, name):
        if not (name.startswith('_') or name.startswith('item_')):
            return getattr(self.item_instance, name)
        else:
            return object.__getattribute__(self, name)


class ExtractorField(object):
    def __init__(self, funcs):
        self._funcs = []

        for func in funcs:
            if inspect.isfunction(func):
                func_args, _, _, _ = inspect.getargspec(func)
            elif hasattr(func, '__call__'):
                try:
                    func_args, _, _, _ = inspect.getargspec(func.__call__)
                except Exception:
                    func_args = []

            takes_args = True if 'adaptor_args' in func_args else False
            self._funcs.append((func, takes_args))

    def __call__(self, value, kwargs=None):
        values = [value]

        for func, takes_args in self._funcs:
            next_round = []

            for val in values:
                val = func(val, kwargs) if takes_args else func(val)

                if isinstance(val, tuple):
                    next_round.extend(val)
                elif val is not None:
                    next_round.append(val)

            values = next_round

        return list(values)

