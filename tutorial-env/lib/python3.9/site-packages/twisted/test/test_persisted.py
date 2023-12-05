# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


# System Imports
import copyreg
import io
import pickle
import sys

# Twisted Imports
from twisted.persisted import aot, crefutil, styles
from twisted.trial import unittest
from twisted.trial.unittest import TestCase


class VersionTests(TestCase):
    def test_nullVersionUpgrade(self):
        global NullVersioned

        class NullVersioned:
            def __init__(self):
                self.ok = 0

        pkcl = pickle.dumps(NullVersioned())

        class NullVersioned(styles.Versioned):
            persistenceVersion = 1

            def upgradeToVersion1(self):
                self.ok = 1

        mnv = pickle.loads(pkcl)
        styles.doUpgrade()
        assert mnv.ok, "initial upgrade not run!"

    def test_versionUpgrade(self):
        global MyVersioned

        class MyVersioned(styles.Versioned):
            persistenceVersion = 2
            persistenceForgets = ["garbagedata"]
            v3 = 0
            v4 = 0

            def __init__(self):
                self.somedata = "xxx"
                self.garbagedata = lambda q: "cant persist"

            def upgradeToVersion3(self):
                self.v3 += 1

            def upgradeToVersion4(self):
                self.v4 += 1

        mv = MyVersioned()
        assert not (mv.v3 or mv.v4), "hasn't been upgraded yet"
        pickl = pickle.dumps(mv)
        MyVersioned.persistenceVersion = 4
        obj = pickle.loads(pickl)
        styles.doUpgrade()
        assert obj.v3, "didn't do version 3 upgrade"
        assert obj.v4, "didn't do version 4 upgrade"
        pickl = pickle.dumps(obj)
        obj = pickle.loads(pickl)
        styles.doUpgrade()
        assert obj.v3 == 1, "upgraded unnecessarily"
        assert obj.v4 == 1, "upgraded unnecessarily"

    def test_nonIdentityHash(self):
        global ClassWithCustomHash

        class ClassWithCustomHash(styles.Versioned):
            def __init__(self, unique, hash):
                self.unique = unique
                self.hash = hash

            def __hash__(self):
                return self.hash

        v1 = ClassWithCustomHash("v1", 0)
        v2 = ClassWithCustomHash("v2", 0)

        pkl = pickle.dumps((v1, v2))
        del v1, v2
        ClassWithCustomHash.persistenceVersion = 1
        ClassWithCustomHash.upgradeToVersion1 = lambda self: setattr(
            self, "upgraded", True
        )
        v1, v2 = pickle.loads(pkl)
        styles.doUpgrade()
        self.assertEqual(v1.unique, "v1")
        self.assertEqual(v2.unique, "v2")
        self.assertTrue(v1.upgraded)
        self.assertTrue(v2.upgraded)

    def test_upgradeDeserializesObjectsRequiringUpgrade(self):
        global ToyClassA, ToyClassB

        class ToyClassA(styles.Versioned):
            pass

        class ToyClassB(styles.Versioned):
            pass

        x = ToyClassA()
        y = ToyClassB()
        pklA, pklB = pickle.dumps(x), pickle.dumps(y)
        del x, y
        ToyClassA.persistenceVersion = 1

        def upgradeToVersion1(self):
            self.y = pickle.loads(pklB)
            styles.doUpgrade()

        ToyClassA.upgradeToVersion1 = upgradeToVersion1
        ToyClassB.persistenceVersion = 1

        def setUpgraded(self):
            setattr(self, "upgraded", True)

        ToyClassB.upgradeToVersion1 = setUpgraded

        x = pickle.loads(pklA)
        styles.doUpgrade()
        self.assertTrue(x.y.upgraded)


class VersionedSubClass(styles.Versioned):
    pass


class SecondVersionedSubClass(styles.Versioned):
    pass


class VersionedSubSubClass(VersionedSubClass):
    pass


class VersionedDiamondSubClass(VersionedSubSubClass, SecondVersionedSubClass):
    pass


class AybabtuTests(TestCase):
    """
    L{styles._aybabtu} gets all of classes in the inheritance hierarchy of its
    argument that are strictly between L{Versioned} and the class itself.
    """

    def test_aybabtuStrictEmpty(self):
        """
        L{styles._aybabtu} of L{Versioned} itself is an empty list.
        """
        self.assertEqual(styles._aybabtu(styles.Versioned), [])

    def test_aybabtuStrictSubclass(self):
        """
        There are no classes I{between} L{VersionedSubClass} and L{Versioned},
        so L{styles._aybabtu} returns an empty list.
        """
        self.assertEqual(styles._aybabtu(VersionedSubClass), [])

    def test_aybabtuSubsubclass(self):
        """
        With a sub-sub-class of L{Versioned}, L{styles._aybabtu} returns a list
        containing the intervening subclass.
        """
        self.assertEqual(styles._aybabtu(VersionedSubSubClass), [VersionedSubClass])

    def test_aybabtuStrict(self):
        """
        For a diamond-shaped inheritance graph, L{styles._aybabtu} returns a
        list containing I{both} intermediate subclasses.
        """
        self.assertEqual(
            styles._aybabtu(VersionedDiamondSubClass),
            [VersionedSubSubClass, VersionedSubClass, SecondVersionedSubClass],
        )


class MyEphemeral(styles.Ephemeral):
    def __init__(self, x):
        self.x = x


class EphemeralTests(TestCase):
    def test_ephemeral(self):
        o = MyEphemeral(3)
        self.assertEqual(o.__class__, MyEphemeral)
        self.assertEqual(o.x, 3)

        pickl = pickle.dumps(o)
        o = pickle.loads(pickl)

        self.assertEqual(o.__class__, styles.Ephemeral)
        self.assertFalse(hasattr(o, "x"))


class Pickleable:
    def __init__(self, x):
        self.x = x

    def getX(self):
        return self.x


class NotPickleable:
    """
    A class that is not pickleable.
    """

    def __reduce__(self):
        """
        Raise an exception instead of pickling.
        """
        raise TypeError("Not serializable.")


class CopyRegistered:
    """
    A class that is pickleable only because it is registered with the
    C{copyreg} module.
    """

    def __init__(self):
        """
        Ensure that this object is normally not pickleable.
        """
        self.notPickleable = NotPickleable()


class CopyRegisteredLoaded:
    """
    L{CopyRegistered} after unserialization.
    """


def reduceCopyRegistered(cr):
    """
    Externally implement C{__reduce__} for L{CopyRegistered}.

    @param cr: The L{CopyRegistered} instance.

    @return: a 2-tuple of callable and argument list, in this case
        L{CopyRegisteredLoaded} and no arguments.
    """
    return CopyRegisteredLoaded, ()


copyreg.pickle(CopyRegistered, reduceCopyRegistered)


class A:
    """
    dummy class
    """

    def amethod(self):
        pass


class B:
    """
    dummy class
    """

    def bmethod(self):
        pass


def funktion():
    pass


class PicklingTests(TestCase):
    """Test pickling of extra object types."""

    def test_module(self):
        pickl = pickle.dumps(styles)
        o = pickle.loads(pickl)
        self.assertEqual(o, styles)

    def test_instanceMethod(self):
        obj = Pickleable(4)
        pickl = pickle.dumps(obj.getX)
        o = pickle.loads(pickl)
        self.assertEqual(o(), 4)
        self.assertEqual(type(o), type(obj.getX))


class StringIOTransitionTests(TestCase):
    """
    When pickling a cStringIO in Python 2, it should unpickle as a BytesIO or a
    StringIO in Python 3, depending on the type of its contents.
    """

    def test_unpickleBytesIO(self):
        """
        A cStringIO pickled with bytes in it will yield an L{io.BytesIO} on
        python 3.
        """
        pickledStringIWithText = (
            b"ctwisted.persisted.styles\nunpickleStringI\np0\n"
            b"(S'test'\np1\nI0\ntp2\nRp3\n."
        )
        loaded = pickle.loads(pickledStringIWithText)
        self.assertIsInstance(loaded, io.StringIO)
        self.assertEqual(loaded.getvalue(), "test")


class EvilSourceror:
    def __init__(self, x):
        self.a = self
        self.a.b = self
        self.a.b.c = x


class NonDictState:
    def __getstate__(self):
        return self.state

    def __setstate__(self, state):
        self.state = state


class AOTTests(TestCase):
    def test_simpleTypes(self):
        obj = (
            1,
            2.0,
            3j,
            True,
            slice(1, 2, 3),
            "hello",
            "world",
            sys.maxsize + 1,
            None,
            Ellipsis,
        )
        rtObj = aot.unjellyFromSource(aot.jellyToSource(obj))
        self.assertEqual(obj, rtObj)

    def test_methodSelfIdentity(self):
        a = A()
        b = B()
        a.bmethod = b.bmethod
        b.a = a
        im_ = aot.unjellyFromSource(aot.jellyToSource(b)).a.bmethod
        self.assertEqual(aot._selfOfMethod(im_).__class__, aot._classOfMethod(im_))

    def test_methodNotSelfIdentity(self):
        """
        If a class change after an instance has been created,
        L{aot.unjellyFromSource} shoud raise a C{TypeError} when trying to
        unjelly the instance.
        """
        a = A()
        b = B()
        a.bmethod = b.bmethod
        b.a = a
        savedbmethod = B.bmethod
        del B.bmethod
        try:
            self.assertRaises(TypeError, aot.unjellyFromSource, aot.jellyToSource(b))
        finally:
            B.bmethod = savedbmethod

    def test_unsupportedType(self):
        """
        L{aot.jellyToSource} should raise a C{TypeError} when trying to jelly
        an unknown type without a C{__dict__} property or C{__getstate__}
        method.
        """

        class UnknownType:
            @property
            def __dict__(self):
                raise AttributeError()

        self.assertRaises(TypeError, aot.jellyToSource, UnknownType())

    def test_basicIdentity(self):
        # Anyone wanting to make this datastructure more complex, and thus this
        # test more comprehensive, is welcome to do so.
        aj = aot.AOTJellier().jellyToAO
        d = {"hello": "world", "method": aj}
        l = [
            1,
            2,
            3,
            'he\tllo\n\n"x world!',
            "goodbye \n\t\u1010 world!",
            1,
            1.0,
            100 ** 100,
            unittest,
            aot.AOTJellier,
            d,
            funktion,
        ]
        t = tuple(l)
        l.append(l)
        l.append(t)
        l.append(t)
        uj = aot.unjellyFromSource(aot.jellyToSource([l, l]))
        assert uj[0] is uj[1]
        assert uj[1][0:5] == l[0:5]

    def test_nonDictState(self):
        a = NonDictState()
        a.state = "meringue!"
        assert aot.unjellyFromSource(aot.jellyToSource(a)).state == a.state

    def test_copyReg(self):
        """
        L{aot.jellyToSource} and L{aot.unjellyFromSource} honor functions
        registered in the pickle copy registry.
        """
        uj = aot.unjellyFromSource(aot.jellyToSource(CopyRegistered()))
        self.assertIsInstance(uj, CopyRegisteredLoaded)

    def test_funkyReferences(self):
        o = EvilSourceror(EvilSourceror([]))
        j1 = aot.jellyToAOT(o)
        oj = aot.unjellyFromAOT(j1)

        assert oj.a is oj
        assert oj.a.b is oj.b
        assert oj.c is not oj.c.c

    def test_circularTuple(self):
        """
        L{aot.jellyToAOT} can persist circular references through tuples.
        """
        l = []
        t = (l, 4321)
        l.append(t)
        j1 = aot.jellyToAOT(l)
        oj = aot.unjellyFromAOT(j1)
        self.assertIsInstance(oj[0], tuple)
        self.assertIs(oj[0][0], oj)
        self.assertEqual(oj[0][1], 4321)


class CrefUtilTests(TestCase):
    """
    Tests for L{crefutil}.
    """

    def test_dictUnknownKey(self):
        """
        L{crefutil._DictKeyAndValue} only support keys C{0} and C{1}.
        """
        d = crefutil._DictKeyAndValue({})
        self.assertRaises(RuntimeError, d.__setitem__, 2, 3)

    def test_deferSetMultipleTimes(self):
        """
        L{crefutil._Defer} can be assigned a key only one time.
        """
        d = crefutil._Defer()
        d[0] = 1
        self.assertRaises(RuntimeError, d.__setitem__, 0, 1)

    def test_containerWhereAllElementsAreKnown(self):
        """
        A L{crefutil._Container} where all of its elements are known at
        construction time is nonsensical and will result in errors in any call
        to addDependant.
        """
        container = crefutil._Container([1, 2, 3], list)
        self.assertRaises(AssertionError, container.addDependant, {}, "ignore-me")

    def test_dontPutCircularReferencesInDictionaryKeys(self):
        """
        If a dictionary key contains a circular reference (which is probably a
        bad practice anyway) it will be resolved by a
        L{crefutil._DictKeyAndValue}, not by placing a L{crefutil.NotKnown}
        into a dictionary key.
        """
        self.assertRaises(
            AssertionError, dict().__setitem__, crefutil.NotKnown(), "value"
        )

    def test_dontCallInstanceMethodsThatArentReady(self):
        """
        L{crefutil._InstanceMethod} raises L{AssertionError} to indicate it
        should not be called.  This should not be possible with any of its API
        clients, but is provided for helping to debug.
        """
        self.assertRaises(
            AssertionError,
            crefutil._InstanceMethod("no_name", crefutil.NotKnown(), type),
        )


testCases = [VersionTests, EphemeralTests, PicklingTests]
