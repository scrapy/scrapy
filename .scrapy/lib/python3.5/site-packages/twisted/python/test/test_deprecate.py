# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for Twisted's deprecation framework, L{twisted.python.deprecate}.
"""

from __future__ import division, absolute_import

import sys, types, warnings, inspect
from os.path import normcase
from warnings import simplefilter, catch_warnings
try:
    from importlib import invalidate_caches
except ImportError:
    invalidate_caches = None

from twisted.python import deprecate
from twisted.python.deprecate import _getDeprecationWarningString
from twisted.python.deprecate import DEPRECATION_WARNING_FORMAT
from twisted.python.deprecate import (
    getDeprecationWarningString,
    deprecated, _appendToDocstring, _getDeprecationDocstring,
    _fullyQualifiedName as fullyQualifiedName,
    _passed, _mutuallyExclusiveArguments,
    deprecatedProperty,
)

from twisted.python.versions import Version
from twisted.python.filepath import FilePath

from twisted.python.test import deprecatedattributes
from twisted.python.test.modules_helpers import TwistedModulesMixin

from twisted.trial.unittest import SynchronousTestCase

# Note that various tests in this module require manual encoding of paths to
# utf-8. This can be fixed once FilePath supports Unicode; see #2366, #4736,
# #5203.


class _MockDeprecatedAttribute(object):
    """
    Mock of L{twisted.python.deprecate._DeprecatedAttribute}.

    @ivar value: The value of the attribute.
    """
    def __init__(self, value):
        self.value = value


    def get(self):
        """
        Get a known value.
        """
        return self.value



class ModuleProxyTests(SynchronousTestCase):
    """
    Tests for L{twisted.python.deprecate._ModuleProxy}, which proxies
    access to module-level attributes, intercepting access to deprecated
    attributes and passing through access to normal attributes.
    """
    def _makeProxy(self, **attrs):
        """
        Create a temporary module proxy object.

        @param **kw: Attributes to initialise on the temporary module object

        @rtype: L{twistd.python.deprecate._ModuleProxy}
        """
        mod = types.ModuleType('foo')
        for key, value in attrs.items():
            setattr(mod, key, value)
        return deprecate._ModuleProxy(mod)


    def test_getattrPassthrough(self):
        """
        Getting a normal attribute on a L{twisted.python.deprecate._ModuleProxy}
        retrieves the underlying attribute's value, and raises C{AttributeError}
        if a non-existent attribute is accessed.
        """
        proxy = self._makeProxy(SOME_ATTRIBUTE='hello')
        self.assertIs(proxy.SOME_ATTRIBUTE, 'hello')
        self.assertRaises(AttributeError, getattr, proxy, 'DOES_NOT_EXIST')


    def test_getattrIntercept(self):
        """
        Getting an attribute marked as being deprecated on
        L{twisted.python.deprecate._ModuleProxy} results in calling the
        deprecated wrapper's C{get} method.
        """
        proxy = self._makeProxy()
        _deprecatedAttributes = object.__getattribute__(
            proxy, '_deprecatedAttributes')
        _deprecatedAttributes['foo'] = _MockDeprecatedAttribute(42)
        self.assertEqual(proxy.foo, 42)


    def test_privateAttributes(self):
        """
        Private attributes of L{twisted.python.deprecate._ModuleProxy} are
        inaccessible when regular attribute access is used.
        """
        proxy = self._makeProxy()
        self.assertRaises(AttributeError, getattr, proxy, '_module')
        self.assertRaises(
            AttributeError, getattr, proxy, '_deprecatedAttributes')


    def test_setattr(self):
        """
        Setting attributes on L{twisted.python.deprecate._ModuleProxy} proxies
        them through to the wrapped module.
        """
        proxy = self._makeProxy()
        proxy._module = 1
        self.assertNotEqual(object.__getattribute__(proxy, '_module'), 1)
        self.assertEqual(proxy._module, 1)


    def test_repr(self):
        """
        L{twisted.python.deprecated._ModuleProxy.__repr__} produces a string
        containing the proxy type and a representation of the wrapped module
        object.
        """
        proxy = self._makeProxy()
        realModule = object.__getattribute__(proxy, '_module')
        self.assertEqual(
            repr(proxy), '<%s module=%r>' % (type(proxy).__name__, realModule))



class DeprecatedAttributeTests(SynchronousTestCase):
    """
    Tests for L{twisted.python.deprecate._DeprecatedAttribute} and
    L{twisted.python.deprecate.deprecatedModuleAttribute}, which issue
    warnings for deprecated module-level attributes.
    """
    def setUp(self):
        self.version = deprecatedattributes.version
        self.message = deprecatedattributes.message
        self._testModuleName = __name__ + '.foo'


    def _getWarningString(self, attr):
        """
        Create the warning string used by deprecated attributes.
        """
        return _getDeprecationWarningString(
            deprecatedattributes.__name__ + '.' + attr,
            deprecatedattributes.version,
            DEPRECATION_WARNING_FORMAT + ': ' + deprecatedattributes.message)


    def test_deprecatedAttributeHelper(self):
        """
        L{twisted.python.deprecate._DeprecatedAttribute} correctly sets its
        __name__ to match that of the deprecated attribute and emits a warning
        when the original attribute value is accessed.
        """
        name = 'ANOTHER_DEPRECATED_ATTRIBUTE'
        setattr(deprecatedattributes, name, 42)
        attr = deprecate._DeprecatedAttribute(
            deprecatedattributes, name, self.version, self.message)

        self.assertEqual(attr.__name__, name)

        # Since we're accessing the value getter directly, as opposed to via
        # the module proxy, we need to match the warning's stack level.
        def addStackLevel():
            attr.get()

        # Access the deprecated attribute.
        addStackLevel()
        warningsShown = self.flushWarnings([
            self.test_deprecatedAttributeHelper])
        self.assertIs(warningsShown[0]['category'], DeprecationWarning)
        self.assertEqual(
            warningsShown[0]['message'],
            self._getWarningString(name))
        self.assertEqual(len(warningsShown), 1)


    def test_deprecatedAttribute(self):
        """
        L{twisted.python.deprecate.deprecatedModuleAttribute} wraps a
        module-level attribute in an object that emits a deprecation warning
        when it is accessed the first time only, while leaving other unrelated
        attributes alone.
        """
        # Accessing non-deprecated attributes does not issue a warning.
        deprecatedattributes.ANOTHER_ATTRIBUTE
        warningsShown = self.flushWarnings([self.test_deprecatedAttribute])
        self.assertEqual(len(warningsShown), 0)

        name = 'DEPRECATED_ATTRIBUTE'

        # Access the deprecated attribute. This uses getattr to avoid repeating
        # the attribute name.
        getattr(deprecatedattributes, name)

        warningsShown = self.flushWarnings([self.test_deprecatedAttribute])
        self.assertEqual(len(warningsShown), 1)
        self.assertIs(warningsShown[0]['category'], DeprecationWarning)
        self.assertEqual(
            warningsShown[0]['message'],
            self._getWarningString(name))


    def test_wrappedModule(self):
        """
        Deprecating an attribute in a module replaces and wraps that module
        instance, in C{sys.modules}, with a
        L{twisted.python.deprecate._ModuleProxy} instance but only if it hasn't
        already been wrapped.
        """
        sys.modules[self._testModuleName] = mod = types.ModuleType('foo')
        self.addCleanup(sys.modules.pop, self._testModuleName)

        setattr(mod, 'first', 1)
        setattr(mod, 'second', 2)

        deprecate.deprecatedModuleAttribute(
            Version('Twisted', 8, 0, 0),
            'message',
            self._testModuleName,
            'first')

        proxy = sys.modules[self._testModuleName]
        self.assertNotEqual(proxy, mod)

        deprecate.deprecatedModuleAttribute(
            Version('Twisted', 8, 0, 0),
            'message',
            self._testModuleName,
            'second')

        self.assertIs(proxy, sys.modules[self._testModuleName])



class ImportedModuleAttributeTests(TwistedModulesMixin, SynchronousTestCase):
    """
    Tests for L{deprecatedModuleAttribute} which involve loading a module via
    'import'.
    """

    _packageInit = """\
from twisted.python.deprecate import deprecatedModuleAttribute
from twisted.python.versions import Version

deprecatedModuleAttribute(
    Version('Package', 1, 2, 3), 'message', __name__, 'module')
"""


    def pathEntryTree(self, tree):
        """
        Create some files in a hierarchy, based on a dictionary describing those
        files.  The resulting hierarchy will be placed onto sys.path for the
        duration of the test.

        @param tree: A dictionary representing a directory structure.  Keys are
            strings, representing filenames, dictionary values represent
            directories, string values represent file contents.

        @return: another dictionary similar to the input, with file content
            strings replaced with L{FilePath} objects pointing at where those
            contents are now stored.
        """
        def makeSomeFiles(pathobj, dirdict):
            pathdict = {}
            for (key, value) in dirdict.items():
                child = pathobj.child(key)
                if isinstance(value, bytes):
                    pathdict[key] = child
                    child.setContent(value)
                elif isinstance(value, dict):
                    child.createDirectory()
                    pathdict[key] = makeSomeFiles(child, value)
                else:
                    raise ValueError("only strings and dicts allowed as values")
            return pathdict
        base = FilePath(self.mktemp().encode("utf-8"))
        base.makedirs()

        result = makeSomeFiles(base, tree)
        # On Python 3, sys.path cannot include byte paths:
        self.replaceSysPath([base.path.decode("utf-8")] + sys.path)
        self.replaceSysModules(sys.modules.copy())
        return result


    def simpleModuleEntry(self):
        """
        Add a sample module and package to the path, returning a L{FilePath}
        pointing at the module which will be loadable as C{package.module}.
        """
        paths = self.pathEntryTree(
            {b"package": {b"__init__.py": self._packageInit.encode("utf-8"),
                         b"module.py": b""}})
        return paths[b'package'][b'module.py']


    def checkOneWarning(self, modulePath):
        """
        Verification logic for L{test_deprecatedModule}.
        """
        from package import module
        self.assertEqual(FilePath(module.__file__.encode("utf-8")),
                         modulePath)
        emitted = self.flushWarnings([self.checkOneWarning])
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]['message'],
                          'package.module was deprecated in Package 1.2.3: '
                          'message')
        self.assertEqual(emitted[0]['category'], DeprecationWarning)


    def test_deprecatedModule(self):
        """
        If L{deprecatedModuleAttribute} is used to deprecate a module attribute
        of a package, only one deprecation warning is emitted when the
        deprecated module is imported.
        """
        self.checkOneWarning(self.simpleModuleEntry())


    def test_deprecatedModuleMultipleTimes(self):
        """
        If L{deprecatedModuleAttribute} is used to deprecate a module attribute
        of a package, only one deprecation warning is emitted when the
        deprecated module is subsequently imported.
        """
        mp = self.simpleModuleEntry()
        # The first time, the code needs to be loaded.
        self.checkOneWarning(mp)
        # The second time, things are slightly different; the object's already
        # in the namespace.
        self.checkOneWarning(mp)
        # The third and fourth times, things things should all be exactly the
        # same, but this is a sanity check to make sure the implementation isn't
        # special casing the second time.  Also, putting these cases into a loop
        # means that the stack will be identical, to make sure that the
        # implementation doesn't rely too much on stack-crawling.
        for x in range(2):
            self.checkOneWarning(mp)



class WarnAboutFunctionTests(SynchronousTestCase):
    """
    Tests for L{twisted.python.deprecate.warnAboutFunction} which allows the
    callers of a function to issue a C{DeprecationWarning} about that function.
    """
    def setUp(self):
        """
        Create a file that will have known line numbers when emitting warnings.
        """
        self.package = FilePath(self.mktemp().encode("utf-8")
                                ).child(b'twisted_private_helper')
        self.package.makedirs()
        self.package.child(b'__init__.py').setContent(b'')
        self.package.child(b'module.py').setContent(b'''
"A module string"

from twisted.python import deprecate

def testFunction():
    "A doc string"
    a = 1 + 2
    return a

def callTestFunction():
    b = testFunction()
    if b == 3:
        deprecate.warnAboutFunction(testFunction, "A Warning String")
''')
        # Python 3 doesn't accept bytes in sys.path:
        packagePath = self.package.parent().path.decode("utf-8")
        sys.path.insert(0, packagePath)
        self.addCleanup(sys.path.remove, packagePath)

        modules = sys.modules.copy()
        self.addCleanup(
            lambda: (sys.modules.clear(), sys.modules.update(modules)))


    def test_warning(self):
        """
        L{deprecate.warnAboutFunction} emits a warning the file and line number
        of which point to the beginning of the implementation of the function
        passed to it.
        """
        def aFunc():
            pass
        deprecate.warnAboutFunction(aFunc, 'A Warning Message')
        warningsShown = self.flushWarnings()
        filename = __file__
        if filename.lower().endswith('.pyc'):
            filename = filename[:-1]
        self.assertSamePath(
            FilePath(warningsShown[0]["filename"]), FilePath(filename))
        self.assertEqual(warningsShown[0]["message"], "A Warning Message")


    def test_warningLineNumber(self):
        """
        L{deprecate.warnAboutFunction} emits a C{DeprecationWarning} with the
        number of a line within the implementation of the function passed to it.
        """
        from twisted_private_helper import module
        module.callTestFunction()
        warningsShown = self.flushWarnings()
        self.assertSamePath(
            FilePath(warningsShown[0]["filename"].encode("utf-8")),
            self.package.sibling(b'twisted_private_helper').child(b'module.py'))
        # Line number 9 is the last line in the testFunction in the helper
        # module.
        self.assertEqual(warningsShown[0]["lineno"], 9)
        self.assertEqual(warningsShown[0]["message"], "A Warning String")
        self.assertEqual(len(warningsShown), 1)


    def assertSamePath(self, first, second):
        """
        Assert that the two paths are the same, considering case normalization
        appropriate for the current platform.

        @type first: L{FilePath}
        @type second: L{FilePath}

        @raise C{self.failureType}: If the paths are not the same.
        """
        self.assertTrue(
            normcase(first.path) == normcase(second.path),
            "%r != %r" % (first, second))


    def test_renamedFile(self):
        """
        Even if the implementation of a deprecated function is moved around on
        the filesystem, the line number in the warning emitted by
        L{deprecate.warnAboutFunction} points to a line in the implementation of
        the deprecated function.
        """
        from twisted_private_helper import module
        # Clean up the state resulting from that import; we're not going to use
        # this module, so it should go away.
        del sys.modules['twisted_private_helper']
        del sys.modules[module.__name__]

        # Rename the source directory
        self.package.moveTo(self.package.sibling(b'twisted_renamed_helper'))

        # Make sure importlib notices we've changed importable packages:
        if invalidate_caches:
            invalidate_caches()

        # Import the newly renamed version
        from twisted_renamed_helper import module
        self.addCleanup(sys.modules.pop, 'twisted_renamed_helper')
        self.addCleanup(sys.modules.pop, module.__name__)

        module.callTestFunction()
        warningsShown = self.flushWarnings()
        warnedPath = FilePath(warningsShown[0]["filename"].encode("utf-8"))
        expectedPath = self.package.sibling(
            b'twisted_renamed_helper').child(b'module.py')
        self.assertSamePath(warnedPath, expectedPath)
        self.assertEqual(warningsShown[0]["lineno"], 9)
        self.assertEqual(warningsShown[0]["message"], "A Warning String")
        self.assertEqual(len(warningsShown), 1)


    def test_filteredWarning(self):
        """
        L{deprecate.warnAboutFunction} emits a warning that will be filtered if
        L{warnings.filterwarning} is called with the module name of the
        deprecated function.
        """
        # Clean up anything *else* that might spuriously filter out the warning,
        # such as the "always" simplefilter set up by unittest._collectWarnings.
        # We'll also rely on trial to restore the original filters afterwards.
        del warnings.filters[:]

        warnings.filterwarnings(
            action="ignore", module="twisted_private_helper")

        from twisted_private_helper import module
        module.callTestFunction()

        warningsShown = self.flushWarnings()
        self.assertEqual(len(warningsShown), 0)


    def test_filteredOnceWarning(self):
        """
        L{deprecate.warnAboutFunction} emits a warning that will be filtered
        once if L{warnings.filterwarning} is called with the module name of the
        deprecated function and an action of once.
        """
        # Clean up anything *else* that might spuriously filter out the warning,
        # such as the "always" simplefilter set up by unittest._collectWarnings.
        # We'll also rely on trial to restore the original filters afterwards.
        del warnings.filters[:]

        warnings.filterwarnings(
            action="module", module="twisted_private_helper")

        from twisted_private_helper import module
        module.callTestFunction()
        module.callTestFunction()

        warningsShown = self.flushWarnings()
        self.assertEqual(len(warningsShown), 1)
        message = warningsShown[0]['message']
        category = warningsShown[0]['category']
        filename = warningsShown[0]['filename']
        lineno = warningsShown[0]['lineno']
        msg = warnings.formatwarning(message, category, filename, lineno)
        self.assertTrue(
            msg.endswith("module.py:9: DeprecationWarning: A Warning String\n"
                         "  return a\n"),
            "Unexpected warning string: %r" % (msg,))



def dummyCallable():
    """
    Do nothing.

    This is used to test the deprecation decorators.
    """



def dummyReplacementMethod():
    """
    Do nothing.

    This is used to test the replacement parameter to L{deprecated}.
    """



class DeprecationWarningsTests(SynchronousTestCase):
    def test_getDeprecationWarningString(self):
        """
        L{getDeprecationWarningString} returns a string that tells us that a
        callable was deprecated at a certain released version of Twisted.
        """
        version = Version('Twisted', 8, 0, 0)
        self.assertEqual(
            getDeprecationWarningString(self.test_getDeprecationWarningString,
                                        version),
            "%s.DeprecationWarningsTests.test_getDeprecationWarningString "
            "was deprecated in Twisted 8.0.0" % (__name__,))


    def test_getDeprecationWarningStringWithFormat(self):
        """
        L{getDeprecationWarningString} returns a string that tells us that a
        callable was deprecated at a certain released version of Twisted, with
        a message containing additional information about the deprecation.
        """
        version = Version('Twisted', 8, 0, 0)
        format = DEPRECATION_WARNING_FORMAT + ': This is a message'
        self.assertEqual(
            getDeprecationWarningString(self.test_getDeprecationWarningString,
                                        version, format),
            '%s.DeprecationWarningsTests.test_getDeprecationWarningString was '
            'deprecated in Twisted 8.0.0: This is a message' % (__name__,))


    def test_deprecateEmitsWarning(self):
        """
        Decorating a callable with L{deprecated} emits a warning.
        """
        version = Version('Twisted', 8, 0, 0)
        dummy = deprecated(version)(dummyCallable)
        def addStackLevel():
            dummy()
        with catch_warnings(record=True) as caught:
            simplefilter("always")
            addStackLevel()
            self.assertEqual(caught[0].category, DeprecationWarning)
            self.assertEqual(str(caught[0].message), getDeprecationWarningString(dummyCallable, version))
            # rstrip in case .pyc/.pyo
            self.assertEqual(caught[0].filename.rstrip('co'), __file__.rstrip('co'))


    def test_deprecatedPreservesName(self):
        """
        The decorated function has the same name as the original.
        """
        version = Version('Twisted', 8, 0, 0)
        dummy = deprecated(version)(dummyCallable)
        self.assertEqual(dummyCallable.__name__, dummy.__name__)
        self.assertEqual(fullyQualifiedName(dummyCallable),
                         fullyQualifiedName(dummy))


    def test_getDeprecationDocstring(self):
        """
        L{_getDeprecationDocstring} returns a note about the deprecation to go
        into a docstring.
        """
        version = Version('Twisted', 8, 0, 0)
        self.assertEqual(
            "Deprecated in Twisted 8.0.0.",
            _getDeprecationDocstring(version, ''))


    def test_deprecatedUpdatesDocstring(self):
        """
        The docstring of the deprecated function is appended with information
        about the deprecation.
        """

        def localDummyCallable():
            """
            Do nothing.

            This is used to test the deprecation decorators.
            """

        version = Version('Twisted', 8, 0, 0)
        dummy = deprecated(version)(localDummyCallable)

        _appendToDocstring(
            localDummyCallable,
            _getDeprecationDocstring(version, ''))

        self.assertEqual(localDummyCallable.__doc__, dummy.__doc__)


    def test_versionMetadata(self):
        """
        Deprecating a function adds version information to the decorated
        version of that function.
        """
        version = Version('Twisted', 8, 0, 0)
        dummy = deprecated(version)(dummyCallable)
        self.assertEqual(version, dummy.deprecatedVersion)


    def test_getDeprecationWarningStringReplacement(self):
        """
        L{getDeprecationWarningString} takes an additional replacement parameter
        that can be used to add information to the deprecation.  If the
        replacement parameter is a string, it will be interpolated directly into
        the result.
        """
        version = Version('Twisted', 8, 0, 0)
        warningString = getDeprecationWarningString(
            self.test_getDeprecationWarningString, version,
            replacement="something.foobar")
        self.assertEqual(
            warningString,
            "%s was deprecated in Twisted 8.0.0; please use something.foobar "
            "instead" % (
                fullyQualifiedName(self.test_getDeprecationWarningString),))


    def test_getDeprecationWarningStringReplacementWithCallable(self):
        """
        L{getDeprecationWarningString} takes an additional replacement parameter
        that can be used to add information to the deprecation. If the
        replacement parameter is a callable, its fully qualified name will be
        interpolated into the result.
        """
        version = Version('Twisted', 8, 0, 0)
        warningString = getDeprecationWarningString(
            self.test_getDeprecationWarningString, version,
            replacement=dummyReplacementMethod)
        self.assertEqual(
            warningString,
            "%s was deprecated in Twisted 8.0.0; please use "
            "%s.dummyReplacementMethod instead" % (
                fullyQualifiedName(self.test_getDeprecationWarningString),
                __name__))



@deprecated(Version('Twisted', 1, 2, 3))
class DeprecatedClass(object):
    """
    Class which is entirely deprecated without having a replacement.
    """



class ClassWithDeprecatedProperty(object):
    """
    Class with a single deprecated property.
    """

    _someProtectedValue = None

    @deprecatedProperty(Version('Twisted', 1, 2, 3))
    def someProperty(self):
        """
        Getter docstring.

        @return: The property.
        """
        return self._someProtectedValue


    @someProperty.setter
    def someProperty(self, value):
        """
        Setter docstring.
        """
        self._someProtectedValue = value



class DeprecatedDecoratorTests(SynchronousTestCase):
    """
    Tests for deprecated decorators.
    """

    def assertDocstring(self, target, expected):
        """
        Check that C{target} object has the C{expected} docstring lines.

        @param target: Object which is checked.
        @type target: C{anything}

        @param expected: List of lines, ignoring empty lines or leading or
            trailing spaces.
        @type expected: L{list} or L{str}
        """
        self.assertEqual(
            expected,
            [x.strip() for x in target.__doc__.splitlines() if x.strip()]
            )


    def test_propertyGetter(self):
        """
        When L{deprecatedProperty} is used on a C{property}, accesses raise a
        L{DeprecationWarning} and getter docstring is updated to inform the
        version in which it was deprecated. C{deprecatedVersion} attribute is
        also set to inform the deprecation version.
        """
        obj = ClassWithDeprecatedProperty()

        obj.someProperty

        self.assertDocstring(
            ClassWithDeprecatedProperty.someProperty,
            [
                'Getter docstring.',
                '@return: The property.',
                'Deprecated in Twisted 1.2.3.',
                ],
            )
        ClassWithDeprecatedProperty.someProperty.deprecatedVersion = Version(
            'Twisted', 1, 2, 3)

        message = (
            'twisted.python.test.test_deprecate.ClassWithDeprecatedProperty.'
            'someProperty was deprecated in Twisted 1.2.3'
            )
        warnings = self.flushWarnings([self.test_propertyGetter])
        self.assertEqual(1, len(warnings))
        self.assertEqual(DeprecationWarning, warnings[0]['category'])
        self.assertEqual(message, warnings[0]['message'])


    def test_propertySetter(self):
        """
        When L{deprecatedProperty} is used on a C{property}, setter accesses
        raise a L{DeprecationWarning}.
        """
        newValue = object()
        obj = ClassWithDeprecatedProperty()

        obj.someProperty = newValue

        self.assertIs(newValue, obj._someProtectedValue)
        message = (
            'twisted.python.test.test_deprecate.ClassWithDeprecatedProperty.'
            'someProperty was deprecated in Twisted 1.2.3'
        )
        warnings = self.flushWarnings([self.test_propertySetter])
        self.assertEqual(1, len(warnings))
        self.assertEqual(DeprecationWarning, warnings[0]['category'])
        self.assertEqual(message, warnings[0]['message'])


    def test_class(self):
        """
        When L{deprecated} is used on a class, instantiations raise a
        L{DeprecationWarning} and class's docstring is updated to inform the
        version in which it was deprecated. C{deprecatedVersion} attribute is
        also set to inform the deprecation version.
        """
        DeprecatedClass()

        self.assertDocstring(
            DeprecatedClass,
            [('Class which is entirely deprecated without having a '
              'replacement.'),
            'Deprecated in Twisted 1.2.3.'],
            )
        DeprecatedClass.deprecatedVersion = Version('Twisted', 1, 2, 3)

        message = (
            'twisted.python.test.test_deprecate.DeprecatedClass '
            'was deprecated in Twisted 1.2.3'
            )
        warnings = self.flushWarnings([self.test_class])
        self.assertEqual(1, len(warnings))
        self.assertEqual(DeprecationWarning, warnings[0]['category'])
        self.assertEqual(message, warnings[0]['message'])


    def test_deprecatedReplacement(self):
        """
        L{deprecated} takes an additional replacement parameter that can be used
        to indicate the new, non-deprecated method developers should use.  If
        the replacement parameter is a string, it will be interpolated directly
        into the warning message.
        """
        version = Version('Twisted', 8, 0, 0)
        dummy = deprecated(version, "something.foobar")(dummyCallable)
        self.assertEqual(dummy.__doc__,
            "\n"
            "    Do nothing.\n\n"
            "    This is used to test the deprecation decorators.\n\n"
            "    Deprecated in Twisted 8.0.0; please use "
            "something.foobar"
            " instead.\n"
            "    ")


    def test_deprecatedReplacementWithCallable(self):
        """
        L{deprecated} takes an additional replacement parameter that can be used
        to indicate the new, non-deprecated method developers should use.  If
        the replacement parameter is a callable, its fully qualified name will
        be interpolated into the warning message.
        """
        version = Version('Twisted', 8, 0, 0)
        decorator = deprecated(version, replacement=dummyReplacementMethod)
        dummy = decorator(dummyCallable)
        self.assertEqual(dummy.__doc__,
            "\n"
            "    Do nothing.\n\n"
            "    This is used to test the deprecation decorators.\n\n"
            "    Deprecated in Twisted 8.0.0; please use "
            "%s.dummyReplacementMethod instead.\n"
            "    " % (__name__,))



class AppendToDocstringTests(SynchronousTestCase):
    """
    Test the _appendToDocstring function.

    _appendToDocstring is used to add text to a docstring.
    """

    def test_appendToEmptyDocstring(self):
        """
        Appending to an empty docstring simply replaces the docstring.
        """

        def noDocstring():
            pass

        _appendToDocstring(noDocstring, "Appended text.")
        self.assertEqual("Appended text.", noDocstring.__doc__)


    def test_appendToSingleLineDocstring(self):
        """
        Appending to a single line docstring places the message on a new line,
        with a blank line separating it from the rest of the docstring.

        The docstring ends with a newline, conforming to Twisted and PEP 8
        standards. Unfortunately, the indentation is incorrect, since the
        existing docstring doesn't have enough info to help us indent
        properly.
        """

        def singleLineDocstring():
            """This doesn't comply with standards, but is here for a test."""

        _appendToDocstring(singleLineDocstring, "Appended text.")
        self.assertEqual(
            ["This doesn't comply with standards, but is here for a test.",
             "",
             "Appended text."],
            singleLineDocstring.__doc__.splitlines())
        self.assertTrue(singleLineDocstring.__doc__.endswith('\n'))


    def test_appendToMultilineDocstring(self):
        """
        Appending to a multi-line docstring places the messade on a new line,
        with a blank line separating it from the rest of the docstring.

        Because we have multiple lines, we have enough information to do
        indentation.
        """

        def multiLineDocstring():
            """
            This is a multi-line docstring.
            """

        def expectedDocstring():
            """
            This is a multi-line docstring.

            Appended text.
            """

        _appendToDocstring(multiLineDocstring, "Appended text.")
        self.assertEqual(
            expectedDocstring.__doc__, multiLineDocstring.__doc__)



class MutualArgumentExclusionTests(SynchronousTestCase):
    """
    Tests for L{mutuallyExclusiveArguments}.
    """

    def checkPassed(self, func, *args, **kw):
        """
        Test an invocation of L{passed} with the given function, arguments, and
        keyword arguments.

        @param func: A function whose argspec to pass to L{_passed}.
        @type func: A callable.

        @param args: The arguments which could be passed to L{func}.

        @param kw: The keyword arguments which could be passed to L{func}.

        @return: L{_passed}'s return value
        @rtype: L{dict}
        """
        return _passed(inspect.getargspec(func), args, kw)


    def test_passed_simplePositional(self):
        """
        L{passed} identifies the arguments passed by a simple
        positional test.
        """
        def func(a, b):
            pass
        self.assertEqual(self.checkPassed(func, 1, 2), dict(a=1, b=2))


    def test_passed_tooManyArgs(self):
        """
        L{passed} raises a L{TypeError} if too many arguments are
        passed.
        """
        def func(a, b):
            pass
        self.assertRaises(TypeError, self.checkPassed, func, 1, 2, 3)


    def test_passed_doublePassKeyword(self):
        """
        L{passed} raises a L{TypeError} if a argument is passed both
        positionally and by keyword.
        """
        def func(a):
            pass
        self.assertRaises(TypeError, self.checkPassed, func, 1, a=2)


    def test_passed_unspecifiedKeyword(self):
        """
        L{passed} raises a L{TypeError} if a keyword argument not
        present in the function's declaration is passed.
        """
        def func(a):
            pass
        self.assertRaises(TypeError, self.checkPassed, func, 1, z=2)


    def test_passed_star(self):
        """
        L{passed} places additional positional arguments into a tuple
        under the name of the star argument.
        """
        def func(a, *b):
            pass
        self.assertEqual(self.checkPassed(func, 1, 2, 3),
                         dict(a=1, b=(2, 3)))


    def test_passed_starStar(self):
        """
        Additional keyword arguments are passed as a dict to the star star
        keyword argument.
        """
        def func(a, **b):
            pass
        self.assertEqual(self.checkPassed(func, 1, x=2, y=3, z=4),
                         dict(a=1, b=dict(x=2, y=3, z=4)))


    def test_passed_noDefaultValues(self):
        """
        The results of L{passed} only include arguments explicitly
        passed, not default values.
        """
        def func(a, b, c=1, d=2, e=3):
            pass
        self.assertEqual(self.checkPassed(func, 1, 2, e=7),
                         dict(a=1, b=2, e=7))


    def test_mutualExclusionPrimeDirective(self):
        """
        L{mutuallyExclusiveArguments} does not interfere in its
        decoratee's operation, either its receipt of arguments or its return
        value.
        """
        @_mutuallyExclusiveArguments([('a', 'b')])
        def func(x, y, a=3, b=4):
            return x + y + a + b

        self.assertEqual(func(1, 2), 10)
        self.assertEqual(func(1, 2, 7), 14)
        self.assertEqual(func(1, 2, b=7), 13)


    def test_mutualExclusionExcludesByKeyword(self):
        """
        L{mutuallyExclusiveArguments} raises a L{TypeError}n if its
        decoratee is passed a pair of mutually exclusive arguments.
        """
        @_mutuallyExclusiveArguments([['a', 'b']])
        def func(a=3, b=4):
            return a + b

        self.assertRaises(TypeError, func, a=3, b=4)
