# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for loading tests by name.
"""

from __future__ import absolute_import, division

import os
import sys

import unittest as pyunit
from hashlib import md5

from twisted.python import util, filepath
from twisted.trial.test import packages
from twisted.trial import runner, reporter, unittest
from twisted.trial.itrial import ITestCase
from twisted.trial._asyncrunner import _iterateTests

from twisted.python.modules import getModule
from twisted.python.compat import _PY3



def testNames(tests):
    """
    Return the id of each test within the given test suite or case.
    """
    names = []
    for test in _iterateTests(tests):
        names.append(test.id())
    return names



class FinderTests(packages.PackageTest):
    """
    Tests for L{runner.TestLoader.findByName}.
    """
    def setUp(self):
        packages.PackageTest.setUp(self)
        self.loader = runner.TestLoader()

    def tearDown(self):
        packages.PackageTest.tearDown(self)

    def test_findPackage(self):
        sample1 = self.loader.findByName('twisted')
        import twisted as sample2
        self.assertEqual(sample1, sample2)

    def test_findModule(self):
        sample1 = self.loader.findByName('twisted.trial.test.sample')
        from twisted.trial.test import sample as sample2
        self.assertEqual(sample1, sample2)

    def test_findFile(self):
        path = util.sibpath(__file__, 'sample.py')
        sample1 = self.loader.findByName(path)
        from twisted.trial.test import sample as sample2
        self.assertEqual(sample1, sample2)

    def test_findObject(self):
        sample1 = self.loader.findByName('twisted.trial.test.sample.FooTest')
        from twisted.trial.test import sample
        self.assertEqual(sample.FooTest, sample1)

    if _PY3:
        # In Python 3, `findByName` returns full TestCases, not the objects
        # inside them. This because on Python 3, unbound methods don't exist,
        # so you can't simply make a TestCase after finding it -- it's easier
        # to just find it and put it in a TestCase immediately.
        _Py3SkipMsg = ("Not relevant on Python 3")
        test_findPackage.skip = _Py3SkipMsg
        test_findModule.skip = _Py3SkipMsg
        test_findFile.skip = _Py3SkipMsg
        test_findObject.skip = _Py3SkipMsg

    def test_findNonModule(self):
        self.assertRaises(AttributeError,
                              self.loader.findByName,
                              'twisted.trial.test.nonexistent')

    def test_findNonPackage(self):
        self.assertRaises(ValueError,
                              self.loader.findByName,
                              'nonextant')

    def test_findNonFile(self):
        path = util.sibpath(__file__, 'nonexistent.py')
        self.assertRaises(ValueError, self.loader.findByName, path)



class FileTests(packages.SysPathManglingTest):
    """
    Tests for L{runner.filenameToModule}.
    """
    def test_notFile(self):
        """
        L{runner.filenameToModule} raises a C{ValueError} when a non-existing
        file is passed.
        """
        err = self.assertRaises(ValueError, runner.filenameToModule, 'it')
        self.assertEqual(str(err), "'it' doesn't exist")


    def test_moduleInPath(self):
        """
        If the file in question is a module on the Python path, then it should
        properly import and return that module.
        """
        sample1 = runner.filenameToModule(util.sibpath(__file__, 'sample.py'))
        from twisted.trial.test import sample as sample2
        self.assertEqual(sample2, sample1)


    def test_moduleNotInPath(self):
        """
        If passed the path to a file containing the implementation of a
        module within a package which is not on the import path,
        L{runner.filenameToModule} returns a module object loosely
        resembling the module defined by that file anyway.
        """
        # "test_sample" isn't actually the name of this module.  However,
        # filenameToModule can't seem to figure that out.  So clean up this
        # misnamed module.  It would be better if this weren't necessary
        # and filenameToModule either didn't exist or added a correctly
        # named module to sys.modules.
        self.addCleanup(sys.modules.pop, 'test_sample', None)

        self.mangleSysPath(self.oldPath)
        sample1 = runner.filenameToModule(
            os.path.join(self.parent, 'goodpackage', 'test_sample.py'))
        self.mangleSysPath(self.newPath)
        from goodpackage import test_sample as sample2
        self.assertEqual(os.path.splitext(sample2.__file__)[0],
                             os.path.splitext(sample1.__file__)[0])


    def test_packageInPath(self):
        """
        If the file in question is a package on the Python path, then it should
        properly import and return that package.
        """
        package1 = runner.filenameToModule(os.path.join(self.parent,
                                                        'goodpackage'))
        import goodpackage
        self.assertEqual(goodpackage, package1)


    def test_packageNotInPath(self):
        """
        If passed the path to a directory which represents a package which
        is not on the import path, L{runner.filenameToModule} returns a
        module object loosely resembling the package defined by that
        directory anyway.
        """
        # "__init__" isn't actually the name of the package!  However,
        # filenameToModule is pretty stupid and decides that is its name
        # after all.  Make sure it gets cleaned up.  See the comment in
        # test_moduleNotInPath for possible courses of action related to
        # this.
        self.addCleanup(sys.modules.pop, "__init__")

        self.mangleSysPath(self.oldPath)
        package1 = runner.filenameToModule(
            os.path.join(self.parent, 'goodpackage'))
        self.mangleSysPath(self.newPath)
        import goodpackage
        self.assertEqual(os.path.splitext(goodpackage.__file__)[0],
                         os.path.splitext(package1.__file__)[0])


    def test_directoryNotPackage(self):
        """
        L{runner.filenameToModule} raises a C{ValueError} when the name of an
        empty directory is passed that isn't considered a valid Python package
        because it doesn't contain a C{__init__.py} file.
        """
        emptyDir = filepath.FilePath(self.parent).child("emptyDirectory")
        emptyDir.createDirectory()

        err = self.assertRaises(ValueError, runner.filenameToModule,
            emptyDir.path)
        self.assertEqual(str(err), "%r is not a package directory" % (
            emptyDir.path,))


    def test_filenameNotPython(self):
        """
        L{runner.filenameToModule} raises a C{SyntaxError} when a non-Python
        file is passed.
        """
        filename = filepath.FilePath(self.parent).child('notpython')
        filename.setContent(b"This isn't python")
        self.assertRaises(
            SyntaxError, runner.filenameToModule, filename.path)


    def test_filenameMatchesPackage(self):
        """
        The C{__file__} attribute of the module should match the package name.
        """
        filename = filepath.FilePath(self.parent).child('goodpackage.py')
        filename.setContent(packages.testModule.encode("utf8"))

        try:
            module = runner.filenameToModule(filename.path)
            self.assertEqual(filename.path, module.__file__)
        finally:
            filename.remove()


    def test_directory(self):
        """
        Test loader against a filesystem directory containing an empty
        C{__init__.py} file. It should handle 'path' and 'path/' the same way.
        """
        goodDir = filepath.FilePath(self.parent).child('goodDirectory')
        goodDir.createDirectory()
        goodDir.child('__init__.py').setContent(b'')

        try:
            module = runner.filenameToModule(goodDir.path)
            self.assertTrue(module.__name__.endswith('goodDirectory'))
            module = runner.filenameToModule(goodDir.path + os.path.sep)
            self.assertTrue(module.__name__.endswith('goodDirectory'))
        finally:
            goodDir.remove()



class LoaderTests(packages.SysPathManglingTest):
    """
    Tests for L{trial.TestLoader}.
    """
    def setUp(self):
        self.loader = runner.TestLoader()
        packages.SysPathManglingTest.setUp(self)


    def test_sortCases(self):
        from twisted.trial.test import sample
        suite = self.loader.loadClass(sample.AlphabetTest)
        self.assertEqual(['test_a', 'test_b', 'test_c'],
                             [test._testMethodName for test in suite._tests])
        newOrder = ['test_b', 'test_c', 'test_a']
        sortDict = dict(zip(newOrder, range(3)))
        self.loader.sorter = lambda x : sortDict.get(x.shortDescription(), -1)
        suite = self.loader.loadClass(sample.AlphabetTest)
        self.assertEqual(newOrder,
                             [test._testMethodName for test in suite._tests])


    def test_loadMethod(self):
        from twisted.trial.test import sample
        suite = self.loader.loadMethod(sample.FooTest.test_foo)
        self.assertEqual(1, suite.countTestCases())
        self.assertEqual('test_foo', suite._testMethodName)


    def test_loadFailingMethod(self):
        # test added for issue1353
        from twisted.trial.test import erroneous
        suite = self.loader.loadMethod(erroneous.TestRegularFail.test_fail)
        result = reporter.TestResult()
        suite.run(result)
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(len(result.failures), 1)


    def test_loadFailure(self):
        """
        Loading a test that fails and getting the result of it ends up with one
        test ran and one failure.
        """
        suite = self.loader.loadByName(
            "twisted.trial.test.erroneous.TestRegularFail.test_fail")
        result = reporter.TestResult()
        suite.run(result)
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(len(result.failures), 1)


    def test_loadNonMethod(self):
        from twisted.trial.test import sample
        self.assertRaises(TypeError, self.loader.loadMethod, sample)
        self.assertRaises(TypeError,
                              self.loader.loadMethod, sample.FooTest)
        self.assertRaises(TypeError, self.loader.loadMethod, "string")
        self.assertRaises(TypeError,
                              self.loader.loadMethod, ('foo', 'bar'))


    def test_loadBadDecorator(self):
        """
        A decorated test method for which the decorator has failed to set the
        method's __name__ correctly is loaded and its name in the class scope
        discovered.
        """
        from twisted.trial.test import sample
        suite = self.loader.loadAnything(
            sample.DecorationTest.test_badDecorator,
            parent=sample.DecorationTest,
            qualName=["sample", "DecorationTest", "test_badDecorator"])
        self.assertEqual(1, suite.countTestCases())
        self.assertEqual('test_badDecorator', suite._testMethodName)


    def test_loadGoodDecorator(self):
        """
        A decorated test method for which the decorator has set the method's
        __name__ correctly is loaded and the only name by which it goes is used.
        """
        from twisted.trial.test import sample
        suite = self.loader.loadAnything(
            sample.DecorationTest.test_goodDecorator,
            parent=sample.DecorationTest,
            qualName=["sample", "DecorationTest", "test_goodDecorator"])
        self.assertEqual(1, suite.countTestCases())
        self.assertEqual('test_goodDecorator', suite._testMethodName)


    def test_loadRenamedDecorator(self):
        """
        Load a decorated method which has been copied to a new name inside the
        class.  Thus its __name__ and its key in the class's __dict__ no
        longer match.
        """
        from twisted.trial.test import sample
        suite = self.loader.loadAnything(
            sample.DecorationTest.test_renamedDecorator,
            parent=sample.DecorationTest,
            qualName=["sample", "DecorationTest", "test_renamedDecorator"])
        self.assertEqual(1, suite.countTestCases())
        self.assertEqual('test_renamedDecorator', suite._testMethodName)


    def test_loadClass(self):
        from twisted.trial.test import sample
        suite = self.loader.loadClass(sample.FooTest)
        self.assertEqual(2, suite.countTestCases())
        self.assertEqual(['test_bar', 'test_foo'],
                             [test._testMethodName for test in suite._tests])


    def test_loadNonClass(self):
        from twisted.trial.test import sample
        self.assertRaises(TypeError, self.loader.loadClass, sample)
        self.assertRaises(TypeError,
                              self.loader.loadClass, sample.FooTest.test_foo)
        self.assertRaises(TypeError, self.loader.loadClass, "string")
        self.assertRaises(TypeError,
                              self.loader.loadClass, ('foo', 'bar'))


    def test_loadNonTestCase(self):
        from twisted.trial.test import sample
        self.assertRaises(ValueError, self.loader.loadClass,
                              sample.NotATest)


    def test_loadModule(self):
        from twisted.trial.test import sample
        suite = self.loader.loadModule(sample)
        self.assertEqual(10, suite.countTestCases())


    def test_loadNonModule(self):
        from twisted.trial.test import sample
        self.assertRaises(TypeError,
                              self.loader.loadModule, sample.FooTest)
        self.assertRaises(TypeError,
                              self.loader.loadModule, sample.FooTest.test_foo)
        self.assertRaises(TypeError, self.loader.loadModule, "string")
        self.assertRaises(TypeError,
                              self.loader.loadModule, ('foo', 'bar'))


    def test_loadPackage(self):
        import goodpackage
        suite = self.loader.loadPackage(goodpackage)
        self.assertEqual(7, suite.countTestCases())


    def test_loadNonPackage(self):
        from twisted.trial.test import sample
        self.assertRaises(TypeError,
                              self.loader.loadPackage, sample.FooTest)
        self.assertRaises(TypeError,
                              self.loader.loadPackage, sample.FooTest.test_foo)
        self.assertRaises(TypeError, self.loader.loadPackage, "string")
        self.assertRaises(TypeError,
                              self.loader.loadPackage, ('foo', 'bar'))


    def test_loadModuleAsPackage(self):
        from twisted.trial.test import sample
        ## XXX -- should this instead raise a ValueError? -- jml
        self.assertRaises(TypeError, self.loader.loadPackage, sample)


    def test_loadPackageRecursive(self):
        import goodpackage
        suite = self.loader.loadPackage(goodpackage, recurse=True)
        self.assertEqual(14, suite.countTestCases())


    def test_loadAnythingOnModule(self):
        from twisted.trial.test import sample
        suite = self.loader.loadAnything(sample)
        self.assertEqual(sample.__name__,
                             suite._tests[0]._tests[0].__class__.__module__)


    def test_loadAnythingOnClass(self):
        from twisted.trial.test import sample
        suite = self.loader.loadAnything(sample.FooTest)
        self.assertEqual(2, suite.countTestCases())


    def test_loadAnythingOnMethod(self):
        from twisted.trial.test import sample
        suite = self.loader.loadAnything(sample.FooTest.test_foo)
        self.assertEqual(1, suite.countTestCases())


    def test_loadAnythingOnPackage(self):
        import goodpackage
        suite = self.loader.loadAnything(goodpackage)
        self.assertTrue(isinstance(suite, self.loader.suiteFactory))
        self.assertEqual(7, suite.countTestCases())


    def test_loadAnythingOnPackageRecursive(self):
        import goodpackage
        suite = self.loader.loadAnything(goodpackage, recurse=True)
        self.assertTrue(isinstance(suite, self.loader.suiteFactory))
        self.assertEqual(14, suite.countTestCases())


    def test_loadAnythingOnString(self):
        # the important thing about this test is not the string-iness
        # but the non-handledness.
        self.assertRaises(TypeError,
                              self.loader.loadAnything, "goodpackage")


    def test_importErrors(self):
        import package
        suite = self.loader.loadPackage(package, recurse=True)
        result = reporter.Reporter()
        suite.run(result)
        self.assertEqual(False, result.wasSuccessful())
        self.assertEqual(2, len(result.errors))
        errors = [test.id() for test, error in result.errors]
        errors.sort()
        self.assertEqual(errors, ['package.test_bad_module',
                                  'package.test_import_module'])


    def test_differentInstances(self):
        """
        L{TestLoader.loadClass} returns a suite with each test method
        represented by a different instances of the L{TestCase} they are
        defined on.
        """
        class DistinctInstances(pyunit.TestCase):
            def test_1(self):
                self.first = 'test1Run'

            def test_2(self):
                self.assertFalse(hasattr(self, 'first'))

        suite = self.loader.loadClass(DistinctInstances)
        result = reporter.Reporter()
        suite.run(result)
        self.assertTrue(result.wasSuccessful())


    def test_loadModuleWith_test_suite(self):
        """
        Check that C{test_suite} is used when present and other L{TestCase}s are
        not included.
        """
        from twisted.trial.test import mockcustomsuite
        suite = self.loader.loadModule(mockcustomsuite)
        self.assertEqual(0, suite.countTestCases())
        self.assertEqual("MyCustomSuite", getattr(suite, 'name', None))


    def test_loadModuleWith_testSuite(self):
        """
        Check that C{testSuite} is used when present and other L{TestCase}s are
        not included.
        """
        from twisted.trial.test import mockcustomsuite2
        suite = self.loader.loadModule(mockcustomsuite2)
        self.assertEqual(0, suite.countTestCases())
        self.assertEqual("MyCustomSuite", getattr(suite, 'name', None))


    def test_loadModuleWithBothCustom(self):
        """
        Check that if C{testSuite} and C{test_suite} are both present in a
        module then C{testSuite} gets priority.
        """
        from twisted.trial.test import mockcustomsuite3
        suite = self.loader.loadModule(mockcustomsuite3)
        self.assertEqual('testSuite', getattr(suite, 'name', None))


    def test_customLoadRaisesAttributeError(self):
        """
        Make sure that any C{AttributeError}s raised by C{testSuite} are not
        swallowed by L{TestLoader}.
        """
        def testSuite():
            raise AttributeError('should be reraised')
        from twisted.trial.test import mockcustomsuite2
        mockcustomsuite2.testSuite, original = (testSuite,
                                                mockcustomsuite2.testSuite)
        try:
            self.assertRaises(AttributeError, self.loader.loadModule,
                              mockcustomsuite2)
        finally:
            mockcustomsuite2.testSuite = original


    # XXX - duplicated and modified from test_script
    def assertSuitesEqual(self, test1, test2):
        names1 = testNames(test1)
        names2 = testNames(test2)
        names1.sort()
        names2.sort()
        self.assertEqual(names1, names2)


    def test_loadByNamesDuplicate(self):
        """
        Check that loadByNames ignores duplicate names
        """
        module = 'twisted.trial.test.test_log'
        suite1 = self.loader.loadByNames([module, module], True)
        suite2 = self.loader.loadByName(module, True)
        self.assertSuitesEqual(suite1, suite2)


    def test_loadByNamesPreservesOrder(self):
        """
        L{TestLoader.loadByNames} preserves the order of tests provided to it.
        """
        modules = [
            "inheritancepackage.test_x.A.test_foo",
            "twisted.trial.test.sample",
            "goodpackage",
            "twisted.trial.test.test_log",
            "twisted.trial.test.sample.FooTest",
            "package.test_module"]
        suite1 = self.loader.loadByNames(modules)
        suite2 = runner.TestSuite(map(self.loader.loadByName, modules))
        self.assertEqual(testNames(suite1), testNames(suite2))


    def test_loadDifferentNames(self):
        """
        Check that loadByNames loads all the names that it is given
        """
        modules = ['goodpackage', 'package.test_module']
        suite1 = self.loader.loadByNames(modules)
        suite2 = runner.TestSuite(map(self.loader.loadByName, modules))
        self.assertSuitesEqual(suite1, suite2)

    def test_loadInheritedMethods(self):
        """
        Check that test methods names which are inherited from are all
        loaded rather than just one.
        """
        methods = ['inheritancepackage.test_x.A.test_foo',
                   'inheritancepackage.test_x.B.test_foo']
        suite1 = self.loader.loadByNames(methods)
        suite2 = runner.TestSuite(map(self.loader.loadByName, methods))
        self.assertSuitesEqual(suite1, suite2)


    if _PY3:
        """
        These tests are unable to work on Python 3, as Python 3 has no concept
        of "unbound methods".
        """
        _msg = "Not possible on Python 3."
        test_loadMethod.skip = _msg
        test_loadNonMethod.skip = _msg
        test_loadFailingMethod.skip = _msg
        test_loadAnythingOnMethod.skip = _msg
        del _msg



class ZipLoadingTests(LoaderTests):
    def setUp(self):
        from twisted.python.test.test_zippath import zipit
        LoaderTests.setUp(self)
        zipit(self.parent, self.parent+'.zip')
        self.parent += '.zip'
        self.mangleSysPath(self.oldPath+[self.parent])



class PackageOrderingTests(packages.SysPathManglingTest):

    def setUp(self):
        self.loader = runner.TestLoader()
        self.topDir = self.mktemp()
        parent = os.path.join(self.topDir, "uberpackage")
        os.makedirs(parent)
        open(os.path.join(parent, "__init__.py"), "wb").close()
        packages.SysPathManglingTest.setUp(self, parent)
        self.mangleSysPath(self.oldPath + [self.topDir])

    def _trialSortAlgorithm(self, sorter):
        """
        Right now, halfway by accident, trial sorts like this:

            1. all modules are grouped together in one list and sorted.

            2. within each module, the classes are grouped together in one list
               and sorted.

            3. finally within each class, each test method is grouped together
               in a list and sorted.

        This attempts to return a sorted list of testable thingies following
        those rules, so that we can compare the behavior of loadPackage.

        The things that show as 'cases' are errors from modules which failed to
        import, and test methods.  Let's gather all those together.
        """
        pkg = getModule('uberpackage')
        testModules = []
        for testModule in pkg.walkModules():
            if testModule.name.split(".")[-1].startswith("test_"):
                testModules.append(testModule)
        sortedModules = sorted(testModules, key=sorter) # ONE
        for modinfo in sortedModules:
            # Now let's find all the classes.
            module = modinfo.load(None)
            if module is None:
                yield modinfo
            else:
                testClasses = []
                for attrib in modinfo.iterAttributes():
                    if runner.isTestCase(attrib.load()):
                        testClasses.append(attrib)
                sortedClasses = sorted(testClasses, key=sorter) # TWO
                for clsinfo in sortedClasses:
                    testMethods = []
                    for attr in clsinfo.iterAttributes():
                        if attr.name.split(".")[-1].startswith('test'):
                            testMethods.append(attr)
                    sortedMethods = sorted(testMethods, key=sorter) # THREE
                    for methinfo in sortedMethods:
                        yield methinfo


    def loadSortedPackages(self, sorter=runner.name):
        """
        Verify that packages are loaded in the correct order.
        """
        import uberpackage
        self.loader.sorter = sorter
        suite = self.loader.loadPackage(uberpackage, recurse=True)
        # XXX: Work around strange, unexplained Zope crap.
        # jml, 2007-11-15.
        suite = unittest.decorate(suite, ITestCase)
        resultingTests = list(_iterateTests(suite))
        manifest = list(self._trialSortAlgorithm(sorter))
        for number, (manifestTest, actualTest) in enumerate(
            zip(manifest, resultingTests)):
            self.assertEqual(
                 manifestTest.name, actualTest.id(),
                 "#%d: %s != %s" %
                 (number, manifestTest.name, actualTest.id()))
        self.assertEqual(len(manifest), len(resultingTests))


    def test_sortPackagesDefaultOrder(self):
        self.loadSortedPackages()


    def test_sortPackagesSillyOrder(self):
        def sillySorter(s):
            # This has to work on fully-qualified class names and class
            # objects, which is silly, but it's the "spec", such as it is.
#             if isinstance(s, type) or isinstance(s, types.ClassType):
#                 return s.__module__+'.'+s.__name__
            n = runner.name(s)
            d = md5(n.encode('utf8')).hexdigest()
            return d
        self.loadSortedPackages(sillySorter)
