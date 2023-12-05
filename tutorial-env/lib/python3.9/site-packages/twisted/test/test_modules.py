# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for twisted.python.modules, abstract access to imported or importable
objects.
"""


import compileall
import itertools
import sys
import zipfile

import twisted
from twisted.python import modules
from twisted.python.compat import networkString
from twisted.python.filepath import FilePath
from twisted.python.reflect import namedAny
from twisted.python.test.modules_helpers import TwistedModulesMixin
from twisted.python.test.test_zippath import zipit
from twisted.trial.unittest import TestCase


class TwistedModulesTestCase(TwistedModulesMixin, TestCase):
    """
    Base class for L{modules} test cases.
    """

    def findByIteration(self, modname, where=modules, importPackages=False):
        """
        You don't ever actually want to do this, so it's not in the public
        API, but sometimes we want to compare the result of an iterative call
        with a lookup call and make sure they're the same for test purposes.
        """
        for modinfo in where.walkModules(importPackages=importPackages):
            if modinfo.name == modname:
                return modinfo
        self.fail(f"Unable to find module {modname!r} through iteration.")


class BasicTests(TwistedModulesTestCase):
    def test_namespacedPackages(self):
        """
        Duplicate packages are not yielded when iterating over namespace
        packages.
        """
        # Force pkgutil to be loaded already, since the probe package being
        # created depends on it, and the replaceSysPath call below will make
        # pretty much everything unimportable.
        __import__("pkgutil")

        namespaceBoilerplate = (
            b"import pkgutil; " b"__path__ = pkgutil.extend_path(__path__, __name__)"
        )

        # Create two temporary directories with packages:
        #
        #   entry:
        #       test_package/
        #           __init__.py
        #           nested_package/
        #               __init__.py
        #               module.py
        #
        #   anotherEntry:
        #       test_package/
        #           __init__.py
        #           nested_package/
        #               __init__.py
        #               module2.py
        #
        # test_package and test_package.nested_package are namespace packages,
        # and when both of these are in sys.path, test_package.nested_package
        # should become a virtual package containing both "module" and
        # "module2"

        entry = self.pathEntryWithOnePackage()
        testPackagePath = entry.child("test_package")
        testPackagePath.child("__init__.py").setContent(namespaceBoilerplate)

        nestedEntry = testPackagePath.child("nested_package")
        nestedEntry.makedirs()
        nestedEntry.child("__init__.py").setContent(namespaceBoilerplate)
        nestedEntry.child("module.py").setContent(b"")

        anotherEntry = self.pathEntryWithOnePackage()
        anotherPackagePath = anotherEntry.child("test_package")
        anotherPackagePath.child("__init__.py").setContent(namespaceBoilerplate)

        anotherNestedEntry = anotherPackagePath.child("nested_package")
        anotherNestedEntry.makedirs()
        anotherNestedEntry.child("__init__.py").setContent(namespaceBoilerplate)
        anotherNestedEntry.child("module2.py").setContent(b"")

        self.replaceSysPath([entry.path, anotherEntry.path])

        module = modules.getModule("test_package")

        # We have to use importPackages=True in order to resolve the namespace
        # packages, so we remove the imported packages from sys.modules after
        # walking
        try:
            walkedNames = [mod.name for mod in module.walkModules(importPackages=True)]
        finally:
            for module in list(sys.modules.keys()):
                if module.startswith("test_package"):
                    del sys.modules[module]

        expected = [
            "test_package",
            "test_package.nested_package",
            "test_package.nested_package.module",
            "test_package.nested_package.module2",
        ]

        self.assertEqual(walkedNames, expected)

    def test_unimportablePackageGetItem(self):
        """
        If a package has been explicitly forbidden from importing by setting a
        L{None} key in sys.modules under its name,
        L{modules.PythonPath.__getitem__} should still be able to retrieve an
        unloaded L{modules.PythonModule} for that package.
        """
        shouldNotLoad = []
        path = modules.PythonPath(
            sysPath=[self.pathEntryWithOnePackage().path],
            moduleLoader=shouldNotLoad.append,
            importerCache={},
            sysPathHooks={},
            moduleDict={"test_package": None},
        )
        self.assertEqual(shouldNotLoad, [])
        self.assertFalse(path["test_package"].isLoaded())

    def test_unimportablePackageWalkModules(self):
        """
        If a package has been explicitly forbidden from importing by setting a
        L{None} key in sys.modules under its name, L{modules.walkModules} should
        still be able to retrieve an unloaded L{modules.PythonModule} for that
        package.
        """
        existentPath = self.pathEntryWithOnePackage()
        self.replaceSysPath([existentPath.path])
        self.replaceSysModules({"test_package": None})

        walked = list(modules.walkModules())
        self.assertEqual([m.name for m in walked], ["test_package"])
        self.assertFalse(walked[0].isLoaded())

    def test_nonexistentPaths(self):
        """
        Verify that L{modules.walkModules} ignores entries in sys.path which
        do not exist in the filesystem.
        """
        existentPath = self.pathEntryWithOnePackage()

        nonexistentPath = FilePath(self.mktemp())
        self.assertFalse(nonexistentPath.exists())

        self.replaceSysPath([existentPath.path])

        expected = [modules.getModule("test_package")]

        beforeModules = list(modules.walkModules())
        sys.path.append(nonexistentPath.path)
        afterModules = list(modules.walkModules())

        self.assertEqual(beforeModules, expected)
        self.assertEqual(afterModules, expected)

    def test_nonDirectoryPaths(self):
        """
        Verify that L{modules.walkModules} ignores entries in sys.path which
        refer to regular files in the filesystem.
        """
        existentPath = self.pathEntryWithOnePackage()

        nonDirectoryPath = FilePath(self.mktemp())
        self.assertFalse(nonDirectoryPath.exists())
        nonDirectoryPath.setContent(b"zip file or whatever\n")

        self.replaceSysPath([existentPath.path])

        beforeModules = list(modules.walkModules())
        sys.path.append(nonDirectoryPath.path)
        afterModules = list(modules.walkModules())

        self.assertEqual(beforeModules, afterModules)

    def test_twistedShowsUp(self):
        """
        Scrounge around in the top-level module namespace and make sure that
        Twisted shows up, and that the module thusly obtained is the same as
        the module that we find when we look for it explicitly by name.
        """
        self.assertEqual(modules.getModule("twisted"), self.findByIteration("twisted"))

    def test_dottedNames(self):
        """
        Verify that the walkModules APIs will give us back subpackages, not just
        subpackages.
        """
        self.assertEqual(
            modules.getModule("twisted.python"),
            self.findByIteration("twisted.python", where=modules.getModule("twisted")),
        )

    def test_onlyTopModules(self):
        """
        Verify that the iterModules API will only return top-level modules and
        packages, not submodules or subpackages.
        """
        for module in modules.iterModules():
            self.assertFalse(
                "." in module.name,
                "no nested modules should be returned from iterModules: %r"
                % (module.filePath),
            )

    def test_loadPackagesAndModules(self):
        """
        Verify that we can locate and load packages, modules, submodules, and
        subpackages.
        """
        for n in ["os", "twisted", "twisted.python", "twisted.python.reflect"]:
            m = namedAny(n)
            self.failUnlessIdentical(modules.getModule(n).load(), m)
            self.failUnlessIdentical(self.findByIteration(n).load(), m)

    def test_pathEntriesOnPath(self):
        """
        Verify that path entries discovered via module loading are, in fact, on
        sys.path somewhere.
        """
        for n in ["os", "twisted", "twisted.python", "twisted.python.reflect"]:
            self.failUnlessIn(modules.getModule(n).pathEntry.filePath.path, sys.path)

    def test_alwaysPreferPy(self):
        """
        Verify that .py files will always be preferred to .pyc files, regardless of
        directory listing order.
        """
        mypath = FilePath(self.mktemp())
        mypath.createDirectory()
        pp = modules.PythonPath(sysPath=[mypath.path])
        originalSmartPath = pp._smartPath

        def _evilSmartPath(pathName):
            o = originalSmartPath(pathName)
            originalChildren = o.children

            def evilChildren():
                # normally this order is random; let's make sure it always
                # comes up .pyc-first.
                x = list(originalChildren())
                x.sort()
                x.reverse()
                return x

            o.children = evilChildren
            return o

        mypath.child("abcd.py").setContent(b"\n")
        compileall.compile_dir(mypath.path, quiet=True)
        # sanity check
        self.assertEqual(len(list(mypath.children())), 2)
        pp._smartPath = _evilSmartPath
        self.assertEqual(pp["abcd"].filePath, mypath.child("abcd.py"))

    def test_packageMissingPath(self):
        """
        A package can delete its __path__ for some reasons,
        C{modules.PythonPath} should be able to deal with it.
        """
        mypath = FilePath(self.mktemp())
        mypath.createDirectory()
        pp = modules.PythonPath(sysPath=[mypath.path])
        subpath = mypath.child("abcd")
        subpath.createDirectory()
        subpath.child("__init__.py").setContent(b"del __path__\n")
        sys.path.append(mypath.path)
        __import__("abcd")
        try:
            l = list(pp.walkModules())
            self.assertEqual(len(l), 1)
            self.assertEqual(l[0].name, "abcd")
        finally:
            del sys.modules["abcd"]
            sys.path.remove(mypath.path)


class PathModificationTests(TwistedModulesTestCase):
    """
    These tests share setup/cleanup behavior of creating a dummy package and
    stuffing some code in it.
    """

    _serialnum = itertools.count()  # used to generate serial numbers for
    # package names.

    def setUp(self):
        self.pathExtensionName = self.mktemp()
        self.pathExtension = FilePath(self.pathExtensionName)
        self.pathExtension.createDirectory()
        self.packageName = "pyspacetests%d" % (next(self._serialnum),)
        self.packagePath = self.pathExtension.child(self.packageName)
        self.packagePath.createDirectory()
        self.packagePath.child("__init__.py").setContent(b"")
        self.packagePath.child("a.py").setContent(b"")
        self.packagePath.child("b.py").setContent(b"")
        self.packagePath.child("c__init__.py").setContent(b"")
        self.pathSetUp = False

    def _setupSysPath(self):
        assert not self.pathSetUp
        self.pathSetUp = True
        sys.path.append(self.pathExtensionName)

    def _underUnderPathTest(self, doImport=True):
        moddir2 = self.mktemp()
        fpmd = FilePath(moddir2)
        fpmd.createDirectory()
        fpmd.child("foozle.py").setContent(b"x = 123\n")
        self.packagePath.child("__init__.py").setContent(
            networkString(f"__path__.append({repr(moddir2)})\n")
        )
        # Cut here
        self._setupSysPath()
        modinfo = modules.getModule(self.packageName)
        self.assertEqual(
            self.findByIteration(
                self.packageName + ".foozle", modinfo, importPackages=doImport
            ),
            modinfo["foozle"],
        )
        self.assertEqual(modinfo["foozle"].load().x, 123)

    def test_underUnderPathAlreadyImported(self):
        """
        Verify that iterModules will honor the __path__ of already-loaded packages.
        """
        self._underUnderPathTest()

    def _listModules(self):
        pkginfo = modules.getModule(self.packageName)
        nfni = [modinfo.name.split(".")[-1] for modinfo in pkginfo.iterModules()]
        nfni.sort()
        self.assertEqual(nfni, ["a", "b", "c__init__"])

    def test_listingModules(self):
        """
        Make sure the module list comes back as we expect from iterModules on a
        package, whether zipped or not.
        """
        self._setupSysPath()
        self._listModules()

    def test_listingModulesAlreadyImported(self):
        """
        Make sure the module list comes back as we expect from iterModules on a
        package, whether zipped or not, even if the package has already been
        imported.
        """
        self._setupSysPath()
        namedAny(self.packageName)
        self._listModules()

    def tearDown(self):
        # Intentionally using 'assert' here, this is not a test assertion, this
        # is just an "oh fuck what is going ON" assertion. -glyph
        if self.pathSetUp:
            HORK = "path cleanup failed: don't be surprised if other tests break"
            assert sys.path.pop() is self.pathExtensionName, HORK + ", 1"
            assert self.pathExtensionName not in sys.path, HORK + ", 2"


class RebindingTests(PathModificationTests):
    """
    These tests verify that the default path interrogation API works properly
    even when sys.path has been rebound to a different object.
    """

    def _setupSysPath(self):
        assert not self.pathSetUp
        self.pathSetUp = True
        self.savedSysPath = sys.path
        sys.path = sys.path[:]
        sys.path.append(self.pathExtensionName)

    def tearDown(self):
        """
        Clean up sys.path by re-binding our original object.
        """
        if self.pathSetUp:
            sys.path = self.savedSysPath


class ZipPathModificationTests(PathModificationTests):
    def _setupSysPath(self):
        assert not self.pathSetUp
        zipit(self.pathExtensionName, self.pathExtensionName + ".zip")
        self.pathExtensionName += ".zip"
        assert zipfile.is_zipfile(self.pathExtensionName)
        PathModificationTests._setupSysPath(self)


class PythonPathTests(TestCase):
    """
    Tests for the class which provides the implementation for all of the
    public API of L{twisted.python.modules}, L{PythonPath}.
    """

    def test_unhandledImporter(self):
        """
        Make sure that the behavior when encountering an unknown importer
        type is not catastrophic failure.
        """

        class SecretImporter:
            pass

        def hook(name):
            return SecretImporter()

        syspath = ["example/path"]
        sysmodules = {}
        syshooks = [hook]
        syscache = {}

        def sysloader(name):
            return None

        space = modules.PythonPath(syspath, sysmodules, syshooks, syscache, sysloader)
        entries = list(space.iterEntries())
        self.assertEqual(len(entries), 1)
        self.assertRaises(KeyError, lambda: entries[0]["module"])

    def test_inconsistentImporterCache(self):
        """
        If the path a module loaded with L{PythonPath.__getitem__} is not
        present in the path importer cache, a warning is emitted, but the
        L{PythonModule} is returned as usual.
        """
        space = modules.PythonPath([], sys.modules, [], {})
        thisModule = space[__name__]
        warnings = self.flushWarnings([self.test_inconsistentImporterCache])
        self.assertEqual(warnings[0]["category"], UserWarning)
        self.assertEqual(
            warnings[0]["message"],
            FilePath(twisted.__file__).parent().dirname()
            + " (for module "
            + __name__
            + ") not in path importer cache "
            "(PEP 302 violation - check your local configuration).",
        )
        self.assertEqual(len(warnings), 1)
        self.assertEqual(thisModule.name, __name__)

    def test_containsModule(self):
        """
        L{PythonPath} implements the C{in} operator so that when it is the
        right-hand argument and the name of a module which exists on that
        L{PythonPath} is the left-hand argument, the result is C{True}.
        """
        thePath = modules.PythonPath()
        self.assertIn("os", thePath)

    def test_doesntContainModule(self):
        """
        L{PythonPath} implements the C{in} operator so that when it is the
        right-hand argument and the name of a module which does not exist on
        that L{PythonPath} is the left-hand argument, the result is C{False}.
        """
        thePath = modules.PythonPath()
        self.assertNotIn("bogusModule", thePath)


__all__ = [
    "BasicTests",
    "PathModificationTests",
    "RebindingTests",
    "ZipPathModificationTests",
    "PythonPathTests",
]
