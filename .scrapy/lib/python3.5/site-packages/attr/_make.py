from __future__ import absolute_import, division, print_function

import hashlib
import linecache

from operator import itemgetter

from . import _config
from ._compat import iteritems, isclass, iterkeys
from .exceptions import FrozenInstanceError, NotAnAttrsClassError

# This is used at least twice, so cache it here.
_obj_setattr = object.__setattr__
_init_convert_pat = '__attr_convert_{}'
_tuple_property_pat = "    {attr_name} = property(itemgetter({index}))"


class _Nothing(object):
    """
    Sentinel class to indicate the lack of a value when ``None`` is ambiguous.

    All instances of `_Nothing` are equal.
    """
    def __copy__(self):
        return self

    def __deepcopy__(self, _):
        return self

    def __eq__(self, other):
        return other.__class__ == _Nothing

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "NOTHING"

    def __hash__(self):
        return 0xdeadbeef


NOTHING = _Nothing()
"""
Sentinel to indicate the lack of a value when ``None`` is ambiguous.
"""


def attr(default=NOTHING, validator=None,
         repr=True, cmp=True, hash=True, init=True,
         convert=None):
    """
    Create a new attribute on a class.

    ..  warning::

        Does *not* do anything unless the class is also decorated with
        :func:`attr.s`!

    :param default: A value that is used if an ``attrs``-generated ``__init__``
        is used and no value is passed while instantiating or the attribute is
        excluded using ``init=False``.

        If the value is an instance of :class:`Factory`, its callable will be
        used to construct a new value (useful for mutable datatypes like lists
        or dicts).

        If a default is not set (or set manually to ``attr.NOTHING``), a value
        *must* be supplied when instantiating; otherwise a :exc:`TypeError`
        will be raised.

    :type default: Any value.

    :param callable validator: :func:`callable` that is called by
        ``attrs``-generated ``__init__`` methods after the instance has been
        initialized.  They receive the initialized instance, the
        :class:`Attribute`, and the passed value.

        The return value is *not* inspected so the validator has to throw an
        exception itself.

        They can be globally disabled and re-enabled using
        :func:`get_run_validators`.

    :param bool repr: Include this attribute in the generated ``__repr__``
        method.
    :param bool cmp: Include this attribute in the generated comparison methods
        (``__eq__`` et al).
    :param bool hash: Include this attribute in the generated ``__hash__``
        method.
    :param bool init: Include this attribute in the generated ``__init__``
        method.  It is possible to set this to ``False`` and set a default
        value.  In that case this attributed is unconditionally initialized
        with the specified default value or factory.
    :param callable convert: :func:`callable` that is called by
        ``attrs``-generated ``__init__`` methods to convert attribute's value
        to the desired format.  It is given the passed-in value, and the
        returned value will be used as the new value of the attribute.  The
        value is converted before being passed to the validator, if any.
    """
    return _CountingAttr(
        default=default,
        validator=validator,
        repr=repr,
        cmp=cmp,
        hash=hash,
        init=init,
        convert=convert,
    )


def _make_attr_tuple_class(cls_name, attr_names):
    """
    Create a tuple subclass to hold `Attribute`s for an `attrs` class.

    The subclass is a bare tuple with properties for names.

    class MyClassAttributes(tuple):
        __slots__ = ()
        x = property(itemgetter(0))
    """
    attr_class_name = "{}Attributes".format(cls_name)
    attr_class_template = [
        "class {}(tuple):".format(attr_class_name),
        "    __slots__ = ()",
    ]
    if attr_names:
        for i, attr_name in enumerate(attr_names):
            attr_class_template.append(_tuple_property_pat.format(
                index=i,
                attr_name=attr_name,
            ))
    else:
        attr_class_template.append("    pass")
    globs = {'itemgetter': itemgetter}
    eval(compile("\n".join(attr_class_template), '', 'exec'), globs)
    return globs[attr_class_name]


def _transform_attrs(cls, these):
    """
    Transforms all `_CountingAttr`s on a class into `Attribute`s and saves the
    list as a namedtuple in `__attrs_attrs__`.

    If *these* is passed, use that and don't look for them on the class.
    """
    super_cls = []
    for c in reversed(cls.__mro__[1:-1]):
        sub_attrs = getattr(c, "__attrs_attrs__", None)
        if sub_attrs is not None:
            super_cls.extend(a for a in sub_attrs if a not in super_cls)
    if these is None:
        ca_list = [(name, attr)
                   for name, attr
                   in cls.__dict__.items()
                   if isinstance(attr, _CountingAttr)]
    else:
        ca_list = [(name, ca)
                   for name, ca
                   in iteritems(these)]

    non_super_attrs = [
        Attribute.from_counting_attr(name=attr_name, ca=ca)
        for attr_name, ca
        in sorted(ca_list, key=lambda e: e[1].counter)
    ]
    attr_names = [a.name for a in super_cls + non_super_attrs]

    AttrsClass = _make_attr_tuple_class(cls.__name__, attr_names)

    cls.__attrs_attrs__ = AttrsClass(super_cls + [
        Attribute.from_counting_attr(name=attr_name, ca=ca)
        for attr_name, ca
        in sorted(ca_list, key=lambda e: e[1].counter)
    ])

    had_default = False
    for a in cls.__attrs_attrs__:
        if these is None and a not in super_cls:
            setattr(cls, a.name, a)
        if had_default is True and a.default is NOTHING and a.init is True:
            raise ValueError(
                "No mandatory attributes allowed after an attribute with a "
                "default value or factory.  Attribute in question: {a!r}"
                .format(a=a)
            )
        elif had_default is False and \
                a.default is not NOTHING and \
                a.init is not False:
            had_default = True


def _frozen_setattrs(self, name, value):
    """
    Attached to frozen classes as __setattr__.
    """
    raise FrozenInstanceError()


def attributes(maybe_cls=None, these=None, repr_ns=None,
               repr=True, cmp=True, hash=True, init=True,
               slots=False, frozen=False):
    """
    A class decorator that adds `dunder
    <https://wiki.python.org/moin/DunderAlias>`_\ -methods according to the
    specified attributes using :func:`attr.ib` or the *these* argument.

    :param these: A dictionary of name to :func:`attr.ib` mappings.  This is
        useful to avoid the definition of your attributes within the class body
        because you can't (e.g. if you want to add ``__repr__`` methods to
        Django models) or don't want to (e.g. if you want to use
        :class:`properties <property>`).

        If *these* is not `None`, the class body is *ignored*.

    :type these: :class:`dict` of :class:`str` to :func:`attr.ib`

    :param str repr_ns: When using nested classes, there's no way in Python 2
        to automatically detect that.  Therefore it's possible to set the
        namespace explicitly for a more meaningful ``repr`` output.
    :param bool repr: Create a ``__repr__`` method with a human readable
        represantation of ``attrs`` attributes..
    :param bool cmp: Create ``__eq__``, ``__ne__``, ``__lt__``, ``__le__``,
        ``__gt__``, and ``__ge__`` methods that compare the class as if it were
        a tuple of its ``attrs`` attributes.  But the attributes are *only*
        compared, if the type of both classes is *identical*!
    :param bool hash: Create a ``__hash__`` method that returns the
        :func:`hash` of a tuple of all ``attrs`` attribute values.
    :param bool init: Create a ``__init__`` method that initialiazes the
        ``attrs`` attributes.  Leading underscores are stripped for the
        argument name.
    :param bool slots: Create a slots_-style class that's more
        memory-efficient.  See :ref:`slots` for further ramifications.
    :param bool frozen: Make instances immutable after initialization.  If
        someone attempts to modify a frozen instance,
        :exc:`attr.exceptions.FrozenInstanceError` is raised.

        Please note:

            1. This is achieved by installing a custom ``__setattr__`` method
               on your class so you can't implement an own one.

            2. True immutability is impossible in Python.

            3. This *does* have a minor a runtime performance :ref:`impact
               <how-frozen>` when initializing new instances.  In other words:
               ``__init__`` is slightly slower with ``frozen=True``.

        ..  _slots: https://docs.python.org/3.5/reference/datamodel.html#slots

    ..  versionadded:: 16.0.0 *slots*
    ..  versionadded:: 16.1.0 *frozen*
    """
    def wrap(cls):
        if getattr(cls, "__class__", None) is None:
            raise TypeError("attrs only works with new-style classes.")
        if slots:
            # Only need this later if we're using slots.
            if these is None:
                ca_list = [name
                           for name, attr
                           in cls.__dict__.items()
                           if isinstance(attr, _CountingAttr)]
            else:
                ca_list = list(iterkeys(these))
        _transform_attrs(cls, these)
        if repr is True:
            cls = _add_repr(cls, ns=repr_ns)
        if cmp is True:
            cls = _add_cmp(cls)
        if hash is True:
            cls = _add_hash(cls)
        if init is True:
            cls = _add_init(cls, frozen)
        if frozen is True:
            cls.__setattr__ = _frozen_setattrs
            if slots is True:
                # slots and frozen require __getstate__/__setstate__ to work
                cls = _add_pickle(cls)
        if slots is True:
            cls_dict = dict(cls.__dict__)
            cls_dict["__slots__"] = tuple(ca_list)
            for ca_name in ca_list:
                # It might not actually be in there, e.g. if using 'these'.
                cls_dict.pop(ca_name, None)
            cls_dict.pop('__dict__', None)

            if repr_ns is None:
                cls_name = getattr(cls, "__qualname__", cls.__name__)
            else:
                cls_name = cls.__name__

            cls = type(cls_name, cls.__bases__, cls_dict)

        return cls

    # attrs_or class type depends on the usage of the decorator.  It's a class
    # if it's used as `@attributes` but ``None`` if used # as `@attributes()`.
    if maybe_cls is None:
        return wrap
    else:
        return wrap(maybe_cls)


def _attrs_to_tuple(obj, attrs):
    """
    Create a tuple of all values of *obj*'s *attrs*.
    """
    return tuple(getattr(obj, a.name) for a in attrs)


def _add_hash(cls, attrs=None):
    """
    Add a hash method to *cls*.
    """
    if attrs is None:
        attrs = [a for a in cls.__attrs_attrs__ if a.hash]

    def hash_(self):
        """
        Automatically created by attrs.
        """
        return hash(_attrs_to_tuple(self, attrs))

    cls.__hash__ = hash_
    return cls


def _add_cmp(cls, attrs=None):
    """
    Add comparison methods to *cls*.
    """
    if attrs is None:
        attrs = [a for a in cls.__attrs_attrs__ if a.cmp]

    def attrs_to_tuple(obj):
        """
        Save us some typing.
        """
        return _attrs_to_tuple(obj, attrs)

    def eq(self, other):
        """
        Automatically created by attrs.
        """
        if other.__class__ is self.__class__:
            return attrs_to_tuple(self) == attrs_to_tuple(other)
        else:
            return NotImplemented

    def ne(self, other):
        """
        Automatically created by attrs.
        """
        result = eq(self, other)
        if result is NotImplemented:
            return NotImplemented
        else:
            return not result

    def lt(self, other):
        """
        Automatically created by attrs.
        """
        if isinstance(other, self.__class__):
            return attrs_to_tuple(self) < attrs_to_tuple(other)
        else:
            return NotImplemented

    def le(self, other):
        """
        Automatically created by attrs.
        """
        if isinstance(other, self.__class__):
            return attrs_to_tuple(self) <= attrs_to_tuple(other)
        else:
            return NotImplemented

    def gt(self, other):
        """
        Automatically created by attrs.
        """
        if isinstance(other, self.__class__):
            return attrs_to_tuple(self) > attrs_to_tuple(other)
        else:
            return NotImplemented

    def ge(self, other):
        """
        Automatically created by attrs.
        """
        if isinstance(other, self.__class__):
            return attrs_to_tuple(self) >= attrs_to_tuple(other)
        else:
            return NotImplemented

    cls.__eq__ = eq
    cls.__ne__ = ne
    cls.__lt__ = lt
    cls.__le__ = le
    cls.__gt__ = gt
    cls.__ge__ = ge

    return cls


def _add_repr(cls, ns=None, attrs=None):
    """
    Add a repr method to *cls*.
    """
    if attrs is None:
        attrs = [a for a in cls.__attrs_attrs__ if a.repr]

    def repr_(self):
        """
        Automatically created by attrs.
        """
        real_cls = self.__class__
        if ns is None:
            qualname = getattr(real_cls, "__qualname__", None)
            if qualname is not None:
                class_name = qualname.rsplit(">.", 1)[-1]
            else:
                class_name = real_cls.__name__
        else:
            class_name = ns + "." + real_cls.__name__

        return "{0}({1})".format(
            class_name,
            ", ".join(a.name + "=" + repr(getattr(self, a.name))
                      for a in attrs)
        )
    cls.__repr__ = repr_
    return cls


def _add_init(cls, frozen):
    """
    Add a __init__ method to *cls*.  If *frozen* is True, make it immutable.
    """
    attrs = [a for a in cls.__attrs_attrs__
             if a.init or a.default is not NOTHING]

    # We cache the generated init methods for the same kinds of attributes.
    sha1 = hashlib.sha1()
    sha1.update(repr(attrs).encode("utf-8"))
    unique_filename = "<attrs generated init {0}>".format(
        sha1.hexdigest()
    )

    script, globs = _attrs_to_script(attrs, frozen)
    locs = {}
    bytecode = compile(script, unique_filename, "exec")
    attr_dict = dict((a.name, a) for a in attrs)
    globs.update({
        "NOTHING": NOTHING,
        "attr_dict": attr_dict,
    })
    if frozen is True:
        # Save the lookup overhead in __init__ if we need to circumvent
        # immutability.
        globs["_cached_setattr"] = _obj_setattr
    eval(bytecode, globs, locs)
    init = locs["__init__"]

    # In order of debuggers like PDB being able to step through the code,
    # we add a fake linecache entry.
    linecache.cache[unique_filename] = (
        len(script),
        None,
        script.splitlines(True),
        unique_filename
    )
    cls.__init__ = init
    return cls


def _add_pickle(cls):
    """
    Add pickle helpers, needed for frozen and slotted classes
    """
    def _slots_getstate__(obj):
        """
        Play nice with pickle.
        """
        return tuple(getattr(obj, a.name) for a in fields(obj.__class__))

    def _slots_setstate__(obj, state):
        """
        Play nice with pickle.
        """
        __bound_setattr = _obj_setattr.__get__(obj, Attribute)
        for a, value in zip(fields(obj.__class__), state):
            __bound_setattr(a.name, value)

    cls.__getstate__ = _slots_getstate__
    cls.__setstate__ = _slots_setstate__
    return cls


def fields(cls):
    """
    Returns the tuple of ``attrs`` attributes for a class.

    The tuple also allows accessing the fields by their names (see below for
    examples).

    :param type cls: Class to introspect.

    :raise TypeError: If *cls* is not a class.
    :raise attr.exceptions.NotAnAttrsClassError: If *cls* is not an ``attrs``
        class.

    :rtype: tuple (with name accesors) of :class:`attr.Attribute`

    ..  versionchanged:: 16.2.0 Returned tuple allows accessing the fields
        by name.
    """
    if not isclass(cls):
        raise TypeError("Passed object must be a class.")
    attrs = getattr(cls, "__attrs_attrs__", None)
    if attrs is None:
        raise NotAnAttrsClassError(
            "{cls!r} is not an attrs-decorated class.".format(cls=cls)
        )
    return attrs


def validate(inst):
    """
    Validate all attributes on *inst* that have a validator.

    Leaves all exceptions through.

    :param inst: Instance of a class with ``attrs`` attributes.
    """
    if _config._run_validators is False:
        return

    for a in fields(inst.__class__):
        if a.validator is not None:
            a.validator(inst, a, getattr(inst, a.name))


def _attrs_to_script(attrs, frozen):
    """
    Return a script of an initializer for *attrs* and a dict of globals.

    The globals are expected by the generated script.

     If *frozen* is True, we cannot set the attributes directly so we use
    a cached ``object.__setattr__``.
    """
    lines = []
    if frozen is True:
        lines.append(
            # Circumvent the __setattr__ descriptor to save one lookup per
            # assignment.
            "_setattr = _cached_setattr.__get__(self, self.__class__)"
        )

        def fmt_setter(attr_name, value_var):
            return "_setattr('%(attr_name)s', %(value_var)s)" % {
                "attr_name": attr_name,
                "value_var": value_var,
            }

        def fmt_setter_with_converter(attr_name, value_var):
            conv_name = _init_convert_pat.format(attr_name)
            return "_setattr('%(attr_name)s', %(conv)s(%(value_var)s))" % {
                "attr_name": attr_name,
                "value_var": value_var,
                "conv": conv_name,
            }
    else:
        def fmt_setter(attr_name, value):
            return "self.%(attr_name)s = %(value)s" % {
                "attr_name": attr_name,
                "value": value,
            }

        def fmt_setter_with_converter(attr_name, value_var):
            conv_name = _init_convert_pat.format(attr_name)
            return "self.%(attr_name)s = %(conv)s(%(value_var)s)" % {
                "attr_name": attr_name,
                "value_var": value_var,
                "conv": conv_name,
            }

    args = []
    attrs_to_validate = []

    # This is a dictionary of names to validator and converter callables.
    # Injecting this into __init__ globals lets us avoid lookups.
    names_for_globals = {}

    for a in attrs:
        if a.validator is not None:
            attrs_to_validate.append(a)
        attr_name = a.name
        arg_name = a.name.lstrip("_")
        if a.init is False:
            if isinstance(a.default, Factory):
                if a.convert is not None:
                    lines.append(fmt_setter_with_converter(
                        attr_name,
                        "attr_dict['{attr_name}'].default.factory()"
                        .format(attr_name=attr_name)))
                    conv_name = _init_convert_pat.format(a.name)
                    names_for_globals[conv_name] = a.convert
                else:
                    lines.append(fmt_setter(
                        attr_name,
                        "attr_dict['{attr_name}'].default.factory()"
                        .format(attr_name=attr_name)
                    ))
            else:
                if a.convert is not None:
                    lines.append(fmt_setter_with_converter(
                        attr_name,
                        "attr_dict['{attr_name}'].default"
                        .format(attr_name=attr_name)
                    ))
                    conv_name = _init_convert_pat.format(a.name)
                    names_for_globals[conv_name] = a.convert
                else:
                    lines.append(fmt_setter(
                        attr_name,
                        "attr_dict['{attr_name}'].default"
                        .format(attr_name=attr_name)
                    ))
        elif a.default is not NOTHING and not isinstance(a.default, Factory):
            args.append(
                "{arg_name}=attr_dict['{attr_name}'].default".format(
                    arg_name=arg_name,
                    attr_name=attr_name,
                )
            )
            if a.convert is not None:
                lines.append(fmt_setter_with_converter(attr_name, arg_name))
                names_for_globals[_init_convert_pat.format(a.name)] = a.convert
            else:
                lines.append(fmt_setter(attr_name, arg_name))
        elif a.default is not NOTHING and isinstance(a.default, Factory):
            args.append("{arg_name}=NOTHING".format(arg_name=arg_name))
            lines.append("if {arg_name} is not NOTHING:"
                         .format(arg_name=arg_name))
            if a.convert is not None:
                lines.append("    " + fmt_setter_with_converter(attr_name,
                                                                arg_name))
                lines.append("else:")
                lines.append("    " + fmt_setter_with_converter(
                    attr_name,
                    "attr_dict['{attr_name}'].default.factory()"
                    .format(attr_name=attr_name)
                ))
                names_for_globals[_init_convert_pat.format(a.name)] = a.convert
            else:
                lines.append("    " + fmt_setter(attr_name, arg_name))
                lines.append("else:")
                lines.append("    " + fmt_setter(
                    attr_name,
                    "attr_dict['{attr_name}'].default.factory()"
                    .format(attr_name=attr_name)
                ))
        else:
            args.append(arg_name)
            if a.convert is not None:
                lines.append(fmt_setter_with_converter(attr_name, arg_name))
                names_for_globals[_init_convert_pat.format(a.name)] = a.convert
            else:
                lines.append(fmt_setter(attr_name, arg_name))

    if attrs_to_validate:  # we can skip this if there are no validators.
        names_for_globals["_config"] = _config
        lines.append("if _config._run_validators is False:")
        lines.append("    return")
    for a in attrs_to_validate:
        val_name = "__attr_validator_{}".format(a.name)
        attr_name = "__attr_{}".format(a.name)
        lines.append("{}(self, {}, self.{})".format(val_name, attr_name,
                                                    a.name))
        names_for_globals[val_name] = a.validator
        names_for_globals[attr_name] = a

    return """\
def __init__(self, {args}):
    {lines}
""".format(
        args=", ".join(args),
        lines="\n    ".join(lines) if lines else "pass",
    ), names_for_globals


class Attribute(object):
    """
    *Read-only* representation of an attribute.

    :attribute name: The name of the attribute.

    Plus *all* arguments of :func:`attr.ib`.
    """
    __slots__ = ('name', 'default', 'validator', 'repr', 'cmp', 'hash', 'init',
                 'convert')

    _optional = {"convert": None}

    def __init__(self, name, default, validator, repr, cmp, hash, init,
                 convert=None):
        # Cache this descriptor here to speed things up later.
        __bound_setattr = _obj_setattr.__get__(self, Attribute)

        __bound_setattr('name', name)
        __bound_setattr('default', default)
        __bound_setattr('validator', validator)
        __bound_setattr('repr', repr)
        __bound_setattr('cmp', cmp)
        __bound_setattr('hash', hash)
        __bound_setattr('init', init)
        __bound_setattr('convert', convert)

    def __setattr__(self, name, value):
        raise FrozenInstanceError()

    @classmethod
    def from_counting_attr(cls, name, ca):
        return cls(name=name,
                   **dict((k, getattr(ca, k))
                          for k
                          in Attribute.__slots__
                          if k != "name"))

    # Don't use _add_pickle since fields(Attribute) doesn't work
    def __getstate__(self):
        """
        Play nice with pickle.
        """
        return tuple(getattr(self, name) for name in self.__slots__)

    def __setstate__(self, state):
        """
        Play nice with pickle.
        """
        __bound_setattr = _obj_setattr.__get__(self, Attribute)
        for name, value in zip(self.__slots__, state):
            __bound_setattr(name, value)

_a = [Attribute(name=name, default=NOTHING, validator=None,
                repr=True, cmp=True, hash=True, init=True)
      for name in Attribute.__slots__]
Attribute = _add_hash(
    _add_cmp(_add_repr(Attribute, attrs=_a), attrs=_a), attrs=_a
)


class _CountingAttr(object):
    """
    Intermediate representation of attributes that uses a counter to preserve
    the order in which the attributes have been defined.
    """
    __attrs_attrs__ = [
        Attribute(name=name, default=NOTHING, validator=None,
                  repr=True, cmp=True, hash=True, init=True)
        for name
        in ("counter", "default", "repr", "cmp", "hash", "init",)
    ]
    counter = 0

    def __init__(self, default, validator, repr, cmp, hash, init, convert):
        _CountingAttr.counter += 1
        self.counter = _CountingAttr.counter
        self.default = default
        self.validator = validator
        self.repr = repr
        self.cmp = cmp
        self.hash = hash
        self.init = init
        self.convert = convert


_CountingAttr = _add_cmp(_add_repr(_CountingAttr))


@attributes(slots=True)
class Factory(object):
    """
    Stores a factory callable.

    If passed as the default value to :func:`attr.ib`, the factory is used to
    generate a new value.
    """
    factory = attr()


def make_class(name, attrs, **attributes_arguments):
    """
    A quick way to create a new class called *name* with *attrs*.

    :param name: The name for the new class.
    :type name: str

    :param attrs: A list of names or a dictionary of mappings of names to
        attributes.
    :type attrs: :class:`list` or :class:`dict`

    :param attributes_arguments: Passed unmodified to :func:`attr.s`.

    :return: A new class with *attrs*.
    :rtype: type
    """
    if isinstance(attrs, dict):
        cls_dict = attrs
    elif isinstance(attrs, (list, tuple)):
        cls_dict = dict((a, attr()) for a in attrs)
    else:
        raise TypeError("attrs argument must be a dict or a list.")

    return attributes(**attributes_arguments)(type(name, (object,), cls_dict))
