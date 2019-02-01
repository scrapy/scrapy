"""
This module provides some commonly used processors for Item Loaders.

See documentation in docs/topics/loaders.rst
"""

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.datatypes import MergeDict
from .common import wrap_loader_context


class MapCompose(object):
    """A processor which is constructed from the composition of the given
    functions, similar to the :class:`Compose` processor. The difference with
    this processor is the way internal results are passed among functions,
    which is as follows:

    The input value of this processor is *iterated* and the first function is
    applied to each element. The results of these function calls (one for each element)
    are concatenated to construct a new iterable, which is then used to apply the
    second function, and so on, until the last function is applied to each
    value of the list of values collected so far. The output values of the last
    function are concatenated together to produce the output of this processor.

    Each particular function can return a value or a list of values, which is
    flattened with the list of values returned by the same function applied to
    the other input values. The functions can also return ``None`` in which
    case the output of that function is ignored for further processing over the
    chain.

    This processor provides a convenient way to compose functions that only
    work with single values (instead of iterables). For this reason the
    :class:`MapCompose` processor is typically used as input processor, since
    data is often extracted using the
    :meth:`~scrapy.selector.Selector.extract` method of :ref:`selectors
    <topics-selectors>`, which returns a list of unicode strings.

    The example below should clarify how it works::

        >>> def filter_world(x):
        ...     return None if x == 'world' else x
        ...
        >>> from scrapy.loader.processors import MapCompose
        >>> proc = MapCompose(filter_world, str.upper)
        >>> proc(['hello', 'world', 'this', 'is', 'scrapy'])
        ['HELLO', 'THIS', 'IS', 'SCRAPY']

    As with the Compose processor, functions can receive Loader contexts, and
    constructor keyword arguments are used as default context values. See
    :class:`Compose` processor for more info.
    """

    def __init__(self, *functions, **default_loader_context):
        self.functions = functions
        self.default_loader_context = default_loader_context

    def __call__(self, value, loader_context=None):
        values = arg_to_iter(value)
        if loader_context:
            context = MergeDict(loader_context, self.default_loader_context)
        else:
            context = self.default_loader_context
        wrapped_funcs = [wrap_loader_context(f, context) for f in self.functions]
        for func in wrapped_funcs:
            next_values = []
            for v in values:
                next_values += arg_to_iter(func(v))
            values = next_values
        return values


class Compose(object):
    """A processor which is constructed from the composition of the given
    functions. This means that each input value of this processor is passed to
    the first function, and the result of that function is passed to the second
    function, and so on, until the last function returns the output value of
    this processor.

    By default, stop process on ``None`` value. This behaviour can be changed by
    passing keyword argument ``stop_on_none=False``.

    Example::

        >>> from scrapy.loader.processors import Compose
        >>> proc = Compose(lambda v: v[0], str.upper)
        >>> proc(['hello', 'world'])
        'HELLO'

    Each function can optionally receive a ``loader_context`` parameter. For
    those which do, this processor will pass the currently active :ref:`Loader
    context <topics-loaders-context>` through that parameter.

    The keyword arguments passed in the constructor are used as the default
    Loader context values passed to each function call. However, the final
    Loader context values passed to functions are overridden with the currently
    active Loader context accessible through the :meth:`ItemLoader.context`
    attribute.
    """

    def __init__(self, *functions, **default_loader_context):
        self.functions = functions
        self.stop_on_none = default_loader_context.get('stop_on_none', True)
        self.default_loader_context = default_loader_context

    def __call__(self, value, loader_context=None):
        if loader_context:
            context = MergeDict(loader_context, self.default_loader_context)
        else:
            context = self.default_loader_context
        wrapped_funcs = [wrap_loader_context(f, context) for f in self.functions]
        for func in wrapped_funcs:
            if value is None and self.stop_on_none:
                break
            value = func(value)
        return value


class TakeFirst(object):
    """Returns the first non-null/non-empty value from the values received,
    so it's typically used as an output processor to single-valued fields.
    It doesn't receive any constructor arguments, nor does it accept Loader contexts.

    Example::

        >>> from scrapy.loader.processors import TakeFirst
        >>> proc = TakeFirst()
        >>> proc(['', 'one', 'two', 'three'])
        'one'
    """

    def __call__(self, values):
        for value in values:
            if value is not None and value != '':
                return value


class Identity(object):
    """The simplest processor, which doesn't do anything. It returns the original
    values unchanged. It doesn't receive any constructor arguments, nor does it
    accept Loader contexts.

    Example::

        >>> from scrapy.loader.processors import Identity
        >>> proc = Identity()
        >>> proc(['one', 'two', 'three'])
        ['one', 'two', 'three']
    """

    def __call__(self, values):
        return values


class SelectJmes(object):
    """Queries the value using the JSON path provided to the constructor and
    returns the output.

    Requires `jmespath <https://github.com/jmespath/jmespath>`_.

    This processor takes only one input at a time.

    Example::

        >>> from scrapy.loader.processors import SelectJmes, Compose, MapCompose
        >>> proc = SelectJmes("foo") #for direct use on lists and dictionaries
        >>> proc({'foo': 'bar'})
        'bar'
        >>> proc({'foo': {'bar': 'baz'}})
        {'bar': 'baz'}

    Working with JSON::

        >>> import json
        >>> proc_single_json_str = Compose(json.loads, SelectJmes("foo"))
        >>> proc_single_json_str('{"foo": "bar"}')
        'bar'
        >>> proc_json_list = Compose(json.loads, MapCompose(SelectJmes('foo')))
        >>> proc_json_list('[{"foo":"bar"}, {"baz":"tar"}]')
        ['bar']
    """
    def __init__(self, json_path):
        self.json_path = json_path
        import jmespath
        self.compiled_path = jmespath.compile(self.json_path)

    def __call__(self, value):
        """Query value for the jmespath query and return answer
        :param value: a data structure (dict, list) to extract from
        :return: Element extracted according to jmespath query
        """
        return self.compiled_path.search(value)


class Join(object):
    """Returns the values joined with the separator given in the constructor, which
    defaults to ``u' '``. It doesn't accept Loader contexts.

    When using the default separator, this processor is equivalent to the
    function: ``u' '.join``

    Examples::

        >>> from scrapy.loader.processors import Join
        >>> proc = Join()
        >>> proc(['one', 'two', 'three'])
        'one two three'
        >>> proc = Join('<br>')
        >>> proc(['one', 'two', 'three'])
        'one<br>two<br>three'
    """

    def __init__(self, separator=u' '):
        self.separator = separator

    def __call__(self, values):
        return self.separator.join(values)
