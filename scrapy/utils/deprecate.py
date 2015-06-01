"""Some helpers for deprecation messages"""

import warnings
import inspect
from scrapy.exceptions import ScrapyDeprecationWarning


def attribute(obj, oldattr, newattr, version='0.12'):
    cname = obj.__class__.__name__
    warnings.warn("%s.%s attribute is deprecated and will be no longer supported "
        "in Scrapy %s, use %s.%s attribute instead" % \
        (cname, oldattr, version, cname, newattr), ScrapyDeprecationWarning, stacklevel=3)


def create_deprecated_class(name, new_class, clsdict=None,
                            warn_category=ScrapyDeprecationWarning,
                            warn_once=True,
                            old_class_path=None,
                            new_class_path=None,
                            subclass_warn_message="{cls} inherits from "\
                                    "deprecated class {old}, please inherit "\
                                    "from {new}.",
                            instance_warn_message="{cls} is deprecated, "\
                                    "instantiate {new} instead."):
    """
    Return a "deprecated" class that causes its subclasses to issue a warning.
    Subclasses of ``new_class`` are considered subclasses of this class.
    It also warns when the deprecated class is instantiated, but do not when
    its subclasses are instantiated.

    It can be used to rename a base class in a library. For example, if we
    have

        class OldName(SomeClass):
            # ...

    and we want to rename it to NewName, we can do the following::

        class NewName(SomeClass):
            # ...

        OldName = create_deprecated_class('OldName', NewName)

    Then, if user class inherits from OldName, warning is issued. Also, if
    some code uses ``issubclass(sub, OldName)`` or ``isinstance(sub(), OldName)``
    checks they'll still return True if sub is a subclass of NewName instead of
    OldName.
    """

    class DeprecatedClass(new_class.__class__):

        deprecated_class = None
        warned_on_subclass = False

        def __new__(metacls, name, bases, clsdict_):
            cls = super(DeprecatedClass, metacls).__new__(metacls, name, bases, clsdict_)
            if metacls.deprecated_class is None:
                metacls.deprecated_class = cls
            return cls

        def __init__(cls, name, bases, clsdict_):
            meta = cls.__class__
            old = meta.deprecated_class
            if old in bases and not (warn_once and meta.warned_on_subclass):
                meta.warned_on_subclass = True
                msg = subclass_warn_message.format(cls=_clspath(cls),
                                                   old=_clspath(old, old_class_path),
                                                   new=_clspath(new_class, new_class_path))
                if warn_once:
                    msg += ' (warning only on first subclass, there may be others)'
                warnings.warn(msg, warn_category, stacklevel=2)
            super(DeprecatedClass, cls).__init__(name, bases, clsdict_)

        # see http://www.python.org/dev/peps/pep-3119/#overloading-isinstance-and-issubclass
        # and http://docs.python.org/2/reference/datamodel.html#customizing-instance-and-subclass-checks
        # for implementation details
        def __instancecheck__(cls, inst):
            return any(cls.__subclasscheck__(c)
                       for c in {type(inst), inst.__class__})

        def __subclasscheck__(cls, sub):
            if cls is not DeprecatedClass.deprecated_class:
                # we should do the magic only if second `issubclass` argument
                # is the deprecated class itself - subclasses of the
                # deprecated class should not use custom `__subclasscheck__`
                # method.
                return super(DeprecatedClass, cls).__subclasscheck__(sub)

            if not inspect.isclass(sub):
                raise TypeError("issubclass() arg 1 must be a class")

            mro = getattr(sub, '__mro__', ())
            return any(c in {cls, new_class} for c in mro)

        def __call__(cls, *args, **kwargs):
            old = DeprecatedClass.deprecated_class
            if cls is old:
                msg = instance_warn_message.format(cls=_clspath(cls, old_class_path),
                                                   new=_clspath(new_class, new_class_path))
                warnings.warn(msg, warn_category, stacklevel=2)
            return super(DeprecatedClass, cls).__call__(*args, **kwargs)

    deprecated_cls = DeprecatedClass(name, (new_class,), clsdict or {})

    try:
        frm = inspect.stack()[1]
        parent_module = inspect.getmodule(frm[0])
        if parent_module is not None:
            deprecated_cls.__module__ = parent_module.__name__
    except Exception as e:
        # Sometimes inspect.stack() fails (e.g. when the first import of
        # deprecated class is in jinja2 template). __module__ attribute is not
        # important enough to raise an exception as users may be unable
        # to fix inspect.stack() errors.
        warnings.warn("Error detecting parent module: %r" % e)

    return deprecated_cls


def _clspath(cls, forced=None):
    if forced is not None:
        return forced
    return '{}.{}'.format(cls.__module__, cls.__name__)


DEPRECATION_RULES = [
    ('scrapy.contrib_exp.downloadermiddleware.decompression.', 'scrapy.downloadermiddlewares.decompression.'),
    ('scrapy.contrib_exp.iterators.', 'scrapy.utils.iterators.'),
    ('scrapy.contrib.downloadermiddleware.', 'scrapy.downloadermiddlewares.'),
    ('scrapy.contrib.exporter.', 'scrapy.exporters.'),
    ('scrapy.contrib.linkextractors.', 'scrapy.linkextractors.'),
    ('scrapy.contrib.loader.processor.', 'scrapy.loader.processors.'),
    ('scrapy.contrib.loader.', 'scrapy.loader.'),
    ('scrapy.contrib.pipeline.', 'scrapy.pipelines.'),
    ('scrapy.contrib.spidermiddleware.', 'scrapy.spidermiddlewares.'),
    ('scrapy.contrib.spiders.', 'scrapy.spiders.'),
    ('scrapy.contrib.', 'scrapy.extensions.'),
    ('scrapy.command.', 'scrapy.commands.'),
    ('scrapy.dupefilter.', 'scrapy.dupefilters.'),
    ('scrapy.linkextractor.', 'scrapy.linkextractors.'),
    ('scrapy.spider.', 'scrapy.spiders.'),
    ('scrapy.squeue.', 'scrapy.squeues.'),
    ('scrapy.statscol.', 'scrapy.statscollectors.'),
    ('scrapy.utils.decorator.', 'scrapy.utils.decorators.'),
    ('scrapy.spidermanager.SpiderManager', 'scrapy.spiderloader.SpiderLoader'),
]


def update_classpath(path):
    """Update a deprecated path from an object with its new location"""
    for prefix, replacement in DEPRECATION_RULES:
        if path.startswith(prefix):
            new_path = path.replace(prefix, replacement, 1)
            warnings.warn("`{}` class is deprecated, use `{}` instead".format(path, new_path),
                          ScrapyDeprecationWarning)
            return new_path
    return path
