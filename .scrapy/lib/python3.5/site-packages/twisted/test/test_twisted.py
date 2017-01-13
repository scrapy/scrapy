# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for miscellaneous behaviors of the top-level L{twisted} package (ie, for
the code in C{twisted/__init__.py}.
"""

from __future__ import division, absolute_import

import sys
import twisted

from types import ModuleType, FunctionType

from twisted import _checkRequirements
from twisted.python.compat import _PY3
from twisted.python import reflect
from twisted.trial.unittest import TestCase, SkipTest


# This is somewhat generally useful and should probably be part of a public API
# somewhere.  See #5977.
class SetAsideModule(object):
    """
    L{SetAsideModule} is a context manager for temporarily removing a module
    from C{sys.modules}.

    @ivar name: The name of the module to remove.
    """
    def __init__(self, name):
        self.name = name


    def _unimport(self, name):
        """
        Find the given module and all of its hierarchically inferior modules in
        C{sys.modules}, remove them from it, and return whatever was found.
        """
        modules = dict([
                (moduleName, module)
                for (moduleName, module)
                in list(sys.modules.items())
                if (moduleName == self.name or
                    moduleName.startswith(self.name + "."))])
        for name in modules:
            del sys.modules[name]
        return modules


    def __enter__(self):
        self.modules = self._unimport(self.name)


    def __exit__(self, excType, excValue, traceback):
        self._unimport(self.name)
        sys.modules.update(self.modules)



def _install(modules):
    """
    Take a mapping defining a package and turn it into real C{ModuleType}
    instances in C{sys.modules}.

    Consider these example::

        a = {"foo": "bar"}
        b = {"twisted": {"__version__": "42.6"}}
        c = {"twisted": {"plugin": {"getPlugins": stub}}}

    C{_install(a)} will place an item into C{sys.modules} with C{"foo"} as the
    key and C{"bar" as the value.

    C{_install(b)} will place an item into C{sys.modules} with C{"twisted"} as
    the key.  The value will be a new module object.  The module will have a
    C{"__version__"} attribute with C{"42.6"} as the value.

    C{_install(c)} will place an item into C{sys.modules} with C{"twisted"} as
    the key.  The value will be a new module object with a C{"plugin"}
    attribute.  An item will also be placed into C{sys.modules} with the key
    C{"twisted.plugin"} which refers to that module object.  That module will
    have an attribute C{"getPlugins"} with a value of C{stub}.

    @param modules: A mapping from names to definitions of modules.  The names
        are native strings like C{"twisted"} or C{"unittest"}.  Values may be
        arbitrary objects.  Any value which is not a dictionary will be added to
        C{sys.modules} unmodified.  Any dictionary value indicates the value is
        a new module and its items define the attributes of that module.  The
        definition of this structure is recursive, so a value in the dictionary
        may be a dictionary to trigger another level of processing.

    @return: L{None}
    """
    result = {}
    _makePackages(None, modules, result)
    sys.modules.update(result)



def _makePackages(parent, attributes, result):
    """
    Construct module objects (for either modules or packages).

    @param parent: L{None} or a module object which is the Python package
        containing all of the modules being created by this function call.  Its
        name will be prepended to the name of all created modules.

    @param attributes: A mapping giving the attributes of the particular module
        object this call is creating.

    @param result: A mapping which is populated with all created module names.
        This is suitable for use in updating C{sys.modules}.

    @return: A mapping of all of the attributes created by this call.  This is
        suitable for populating the dictionary of C{parent}.

    @see: L{_install}.
    """
    attrs = {}
    for (name, value) in list(attributes.items()):
        if parent is None:
            if isinstance(value, dict):
                module = ModuleType(name)
                module.__dict__.update(_makePackages(module, value, result))
                result[name] = module
            else:
                result[name] = value
        else:
            if isinstance(value, dict):
                module = ModuleType(parent.__name__ + '.' + name)
                module.__dict__.update(_makePackages(module, value, result))
                result[parent.__name__ + '.' + name] = module
                attrs[name] = module
            else:
                attrs[name] = value
    return attrs



class RequirementsTests(TestCase):
    """
    Tests for the import-time requirements checking.

    @ivar unsupportedPythonVersion: The newest version of Python 2.x which is
        not supported by Twisted.
    @type unsupportedPythonVersion: C{tuple}

    @ivar supportedPythonVersion: The oldest version of Python 2.x which is
        supported by Twisted.
    @type supportedPythonVersion: C{tuple}

    @ivar Py3unsupportedPythonVersion: The newest version of Python 3.x which
        is not supported by Twisted.
    @type Py3unsupportedPythonVersion: C{tuple}

    @ivar Py3supportedPythonVersion: The oldest version of Python 3.x which is
        supported by Twisted.
    @type supportedPythonVersion: C{tuple}

    @ivar Py3supportedZopeInterfaceVersion: The oldest version of
        C{zope.interface} which is supported by Twisted.
    @type supportedZopeInterfaceVersion: C{tuple}
    """
    unsupportedPythonVersion = (2, 6)
    supportedPythonVersion = (2, 7)
    Py3unsupportedPythonVersion = (3, 2)
    Py3supportedPythonVersion = (3, 3)

    if _PY3:
        supportedZopeInterfaceVersion = (4, 0, 0)
    else:
        supportedZopeInterfaceVersion = (3, 6, 0)


    def setUp(self):
        """
        Save the original value of C{sys.version_info} so it can be restored
        after the tests mess with it.
        """
        self.version = sys.version_info


    def tearDown(self):
        """
        Restore the original values saved in L{setUp}.
        """
        sys.version_info = self.version


    def test_oldPython(self):
        """
        L{_checkRequirements} raises L{ImportError} when run on a version of
        Python that is too old.
        """
        sys.version_info = self.unsupportedPythonVersion
        with self.assertRaises(ImportError) as raised:
            _checkRequirements()
        self.assertEqual("Twisted requires Python %d.%d or later."
                         % self.supportedPythonVersion,
                         str(raised.exception))


    def test_newPython(self):
        """
        L{_checkRequirements} returns L{None} when run on a version of Python
        that is sufficiently new.
        """
        sys.version_info = self.supportedPythonVersion
        self.assertIsNone(_checkRequirements())


    def test_oldPythonPy3(self):
        """
        L{_checkRequirements} raises L{ImportError} when run on a version of
        Python that is too old.
        """
        sys.version_info = self.Py3unsupportedPythonVersion
        with self.assertRaises(ImportError) as raised:
            _checkRequirements()
        self.assertEqual("Twisted on Python 3 requires Python %d.%d or later."
                         % self.Py3supportedPythonVersion,
                         str(raised.exception))


    def test_newPythonPy3(self):
        """
        L{_checkRequirements} returns L{None} when run on a version of Python
        that is sufficiently new.
        """
        sys.version_info = self.Py3supportedPythonVersion
        self.assertIsNone(_checkRequirements())


    def test_missingZopeNamespace(self):
        """
        L{_checkRequirements} raises L{ImportError} when the C{zope} namespace
        package is not installed.
        """
        with SetAsideModule("zope"):
            # After an import for a module fails, it gets a None value in
            # sys.modules as a cache of that negative result.  Future import
            # attempts see it and fail fast without checking the system again.
            sys.modules["zope"] = None
            with self.assertRaises(ImportError) as raised:
                _checkRequirements()
            self.assertEqual(
                "Twisted requires zope.interface %d.%d.%d or later: no module "
                "named zope.interface." % self.supportedZopeInterfaceVersion,
                str(raised.exception))


    def test_missingZopeInterface(self):
        """
        L{_checkRequirements} raises L{ImportError} when the C{zope.interface}
        package is not installed.
        """
        with SetAsideModule("zope"):
            # Create a minimal module to represent the zope namespace package,
            # but don't give it an "interface" attribute.
            sys.modules["zope"] = ModuleType("zope")
            with self.assertRaises(ImportError) as raised:
                _checkRequirements()
            self.assertEqual(
                "Twisted requires zope.interface %d.%d.%d or later: no module "
                "named zope.interface." % self.supportedZopeInterfaceVersion,
                str(raised.exception))


    def test_setupNoCheckRequirements(self):
        """
        L{_checkRequirements} doesn't check for C{zope.interface} compliance
        when C{setuptools._TWISTED_NO_CHECK_REQUIREMENTS} is set.
        """
        with SetAsideModule("setuptools"):
            setuptools = ModuleType("setuptools")
            setuptools._TWISTED_NO_CHECK_REQUIREMENTS = True
            sys.modules["setuptools"] = setuptools
            with SetAsideModule("zope"):
                sys.modules["zope"] = None
                _checkRequirements()


    def test_setupCheckRequirements(self):
        """
        L{_checkRequirements} checks for C{zope.interface} compliance when
        C{setuptools} is imported but the C{_TWISTED_NO_CHECK_REQUIREMENTS} is
        not set.
        """
        with SetAsideModule("setuptools"):
            sys.modules["setuptools"] = ModuleType("setuptools")
            with SetAsideModule("zope"):
                sys.modules["zope"] = None
                self.assertRaises(ImportError, _checkRequirements)


    def test_noSetupCheckRequirements(self):
        """
        L{_checkRequirements} checks for C{zope.interface} compliance when
        C{setuptools} is not imported.
        """
        with SetAsideModule("setuptools"):
            sys.modules["setuptools"] = None
            with SetAsideModule("zope"):
                sys.modules["zope"] = None
                self.assertRaises(ImportError, _checkRequirements)


    if _PY3:
        # Python 3 requires a version that isn't tripped up by the __qualname__
        # special attribute.

        def test_oldZopeInterface(self):
            """
            If the installed version of C{zope.interface} does not support the
            C{implementer} class decorator, L{_checkRequirements} raises
            L{ImportError} with a message explaining a newer version is
            required.
            """
            with SetAsideModule("zope"):
                _install(_zope38)
                with self.assertRaises(ImportError) as raised:
                    _checkRequirements()
            self.assertEqual(
                "Twisted requires zope.interface 4.0.0 or later.",
                str(raised.exception))


        def test_newZopeInterface(self):
            """
            If the installed version of C{zope.interface} does support the
            C{implementer} class decorator, L{_checkRequirements} returns
            L{None}.
            """
            with SetAsideModule("zope"):
                _install(_zope40)
                self.assertIsNone(_checkRequirements())

    else:
        # Python 2 only requires a version that supports the class decorator
        # version of declarations.

        def test_oldZopeInterface(self):
            """
            L{_checkRequirements} raises L{ImportError} when the C{zope.interface}
            package installed is old enough that C{implementer_only} is not included
            (added in zope.interface 3.6).
            """
            with SetAsideModule("zope"):
                _install(_zope35)
                with self.assertRaises(ImportError) as raised:
                    _checkRequirements()
                self.assertEqual(
                    "Twisted requires zope.interface 3.6.0 or later.",
                    str(raised.exception))


        def test_newZopeInterface(self):
            """
            L{_checkRequirements} returns L{None} when C{zope.interface} is
            installed and new enough.
            """
            with SetAsideModule("zope"):
                _install(_zope36)
                self.assertIsNone(_checkRequirements())



class MakePackagesTests(TestCase):
    """
    Tests for L{_makePackages}, a helper for populating C{sys.modules} with
    fictional modules.
    """
    def test_nonModule(self):
        """
        A non-C{dict} value in the attributes dictionary passed to L{_makePackages}
        is preserved unchanged in the return value.
        """
        modules = {}
        _makePackages(None, dict(reactor='reactor'), modules)
        self.assertEqual(modules, dict(reactor='reactor'))


    def test_moduleWithAttribute(self):
        """
        A C{dict} value in the attributes dictionary passed to L{_makePackages}
        is turned into a L{ModuleType} instance with attributes populated from
        the items of that C{dict} value.
        """
        modules = {}
        _makePackages(None, dict(twisted=dict(version='123')), modules)
        self.assertIsInstance(modules, dict)
        self.assertIsInstance(modules['twisted'], ModuleType)
        self.assertEqual('twisted', modules['twisted'].__name__)
        self.assertEqual('123', modules['twisted'].version)


    def test_packageWithModule(self):
        """
        Processing of the attributes dictionary is recursive, so a C{dict} value
        it contains may itself contain a C{dict} value to the same effect.
        """
        modules = {}
        _makePackages(None, dict(twisted=dict(web=dict(version='321'))), modules)
        self.assertIsInstance(modules, dict)
        self.assertIsInstance(modules['twisted'], ModuleType)
        self.assertEqual('twisted', modules['twisted'].__name__)
        self.assertIsInstance(modules['twisted'].web, ModuleType)
        self.assertEqual('twisted.web', modules['twisted'].web.__name__)
        self.assertEqual('321', modules['twisted'].web.version)



def _functionOnlyImplementer(*interfaces):
    """
    A fake implementation of L{zope.interface.implementer} which always behaves
    like the version of that function provided by zope.interface 3.5 and older.
    """
    def check(obj):
        """
        If the decorated object is not a function, raise an exception.
        """
        if not isinstance(obj, FunctionType):
            raise TypeError(
                "Can't use implementer with classes.  "
                "Use one of the class-declaration functions instead.")
    return check



def _classSupportingImplementer(*interfaces):
    """
    A fake implementation of L{zope.interface.implementer} which always
    succeeds.  For the use it is put to, this is like the version of that
    function provided by zope.interface 3.6 and newer.
    """
    def check(obj):
        """
        Do nothing at all.
        """
    return check



class _SuccessInterface(object):
    """
    A fake implementation of L{zope.interface.Interface} with no behavior.  For
    the use it is put to, this is equivalent to the behavior of the C{Interface}
    provided by all versions of zope.interface.
    """


# Definition of a module somewhat like zope.interface 3.5.
_zope35 = {
    'zope': {
        'interface': {
            'Interface': _SuccessInterface,
            'implementer': _functionOnlyImplementer,
            },
        },
    }


# Definition of a module somewhat like zope.interface 3.6.
_zope36 = {
    'zope': {
        'interface': {
            'Interface': _SuccessInterface,
            'implementer': _classSupportingImplementer,
            },
        },
    }


class _Zope38OnPython3Module(object):
    """
    A pseudo-module which raises an exception when its C{interface} attribute is
    accessed.  This is like the behavior of zope.interface 3.8 and earlier when
    used with Python 3.3.
    """
    __path__ = []
    __name__ = 'zope'

    @property
    def interface(self):
        raise Exception(
            "zope.interface.exceptions.InvalidInterface: "
            "Concrete attribute, __qualname__")

# Definition of a module somewhat like zope.interface 3.8 when it is used on Python 3.
_zope38 = {
    'zope': _Zope38OnPython3Module(),
    }

# Definition of a module somewhat like zope.interface 4.0.
_zope40 = {
    'zope': {
        'interface': {
            'Interface': _SuccessInterface,
            'implementer': _classSupportingImplementer,
            },
        },
    }


class ZopeInterfaceTestsMixin(object):
    """
    Verify the C{zope.interface} fakes, only possible when a specific version of
    the real C{zope.interface} package is installed on the system.

    Subclass this and override C{install} to properly install and then remove
    the given version of C{zope.interface}.
    """
    def test_zope35(self):
        """
        Version 3.5 of L{zope.interface} has a C{implementer} method which
        cannot be used as a class decorator.
        """
        with SetAsideModule("zope"):
            self.install((3, 5))
            from zope.interface import Interface, implementer
            class IDummy(Interface):
                pass
            try:
                @implementer(IDummy)
                class Dummy(object):
                    pass
            except TypeError as exc:
                self.assertEqual(
                    "Can't use implementer with classes.  "
                    "Use one of the class-declaration functions instead.",
                    str(exc))


    def test_zope36(self):
        """
        Version 3.6 of L{zope.interface} has a C{implementer} method which can
        be used as a class decorator.
        """
        with SetAsideModule("zope"):
            self.install((3, 6))
            from zope.interface import Interface, implementer
            class IDummy(Interface):
                pass
            @implementer(IDummy)
            class Dummy(object):
                pass

    if _PY3:
        def test_zope38(self):
            """
            Version 3.8 of L{zope.interface} does not even import on Python 3.
            """
            with SetAsideModule("zope"):
                self.install((3, 8))
                try:
                    from zope import interface
                    # It is imported just to check errors at import so we
                    # silence the linter.
                    interface
                except Exception as exc:
                    self.assertEqual(
                        "zope.interface.exceptions.InvalidInterface: "
                        "Concrete attribute, __qualname__",
                        str(exc))
                else:
                    self.fail(
                        "InvalidInterface was not raised by zope.interface import")


        def test_zope40(self):
            """
            Version 4.0 of L{zope.interface} can import on Python 3 and, also on
            Python 3, has an C{Interface} class which can be subclassed.
            """
            with SetAsideModule("zope"):
                self.install((4, 0))
                from zope.interface import Interface
                class IDummy(Interface):
                    pass


class FakeZopeInterfaceTests(TestCase, ZopeInterfaceTestsMixin):
    """
    Apply the zope.interface tests to the fakes implemented in this module.
    """
    versions = {
        (3, 5): _zope35,
        (3, 6): _zope36,
        (3, 8): _zope38,
        (4, 0): _zope40,
        }

    def install(self, version):
        """
        Grab one of the fake module implementations and install it into
        C{sys.modules} for use by the test.
        """
        _install(self.versions[version])



class RealZopeInterfaceTests(TestCase, ZopeInterfaceTestsMixin):
    """
    Apply whichever tests from L{ZopeInterfaceTestsMixin} are applicable to the
    system-installed version of zope.interface.
    """
    def install(self, version):
        """
        Check to see if the system-installed version of zope.interface matches
        the version requested.  If so, do nothing.  If not, skip the test (if
        the desired version is not installed, there is no way to test its
        behavior).  If the version of zope.interface cannot be determined
        (because pkg_resources is not installed), skip the test.
        """
        # Use an unrelated, but unreliable, route to try to determine what
        # version of zope.interface is installed on the system.  It's sort of
        # okay to use this unreliable scheme here, since if it fails it only
        # means we won't be able to run the tests.  Hopefully someone else
        # managed to run the tests somewhere else.
        try:
            import pkg_resources
        except ImportError as e:
            raise SkipTest(
                "Cannot determine system version of zope.interface: %s" % (e,))
        else:
            try:
                pkg = pkg_resources.get_distribution("zope.interface")
            except pkg_resources.DistributionNotFound as e:
                raise SkipTest(
                    "Cannot determine system version of zope.interface: %s" % (
                        e,))
            installed = pkg.version
            versionTuple = tuple(
                int(part) for part in installed.split('.')[:len(version)])
            if versionTuple == version:
                pass
            else:
                raise SkipTest("Mismatched system version of zope.interface")



class OldSubprojectDeprecationBase(TestCase):
    """
    Base L{TestCase} for verifying each former subproject has a deprecated
    C{__version__} and a removed C{_version.py}.
    """
    subproject = None

    def test_deprecated(self):
        """
        The C{__version__} attribute of former subprojects is deprecated.
        """
        module = reflect.namedAny("twisted.{}".format(self.subproject))
        self.assertEqual(module.__version__, twisted.__version__)

        warningsShown = self.flushWarnings()
        self.assertEqual(1, len(warningsShown))
        self.assertEqual(
            "twisted.{}.__version__ was deprecated in Twisted 16.0.0: "
            "Use twisted.__version__ instead.".format(self.subproject),
            warningsShown[0]['message'])


    def test_noversionpy(self):
        """
        Former subprojects no longer have an importable C{_version.py}.
        """
        with self.assertRaises(AttributeError):
            reflect.namedAny(
                "twisted.{}._version".format(self.subproject))


if _PY3:
    subprojects = ["conch", "web", "names"]
else:
    subprojects = ["mail", "conch", "runner", "web", "words", "names", "news",
                   "pair"]

for subproject in subprojects:

    class SubprojectTestCase(OldSubprojectDeprecationBase):
        """
        See L{OldSubprojectDeprecationBase}.
        """
        subproject = subproject

    newName = subproject.title() + "VersionDeprecationTests"

    SubprojectTestCase.__name__ = newName
    if _PY3:
        SubprojectTestCase.__qualname__= ".".join(
            OldSubprojectDeprecationBase.__qualname__.split()[0:-1] +
            [newName])

    globals().update({subproject.title() +
                      "VersionDeprecationTests": SubprojectTestCase})

    del SubprojectTestCase
    del newName

del OldSubprojectDeprecationBase
