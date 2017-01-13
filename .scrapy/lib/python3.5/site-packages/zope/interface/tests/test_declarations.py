##############################################################################
#
# Copyright (c) 2003 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Test the new API for making and checking interface declarations
"""
import unittest

from zope.interface._compat import _skip_under_py3k


class _Py3ClassAdvice(object):

    def _run_generated_code(self, code, globs, locs,
                            fails_under_py3k=True,
                           ):
        import warnings
        from zope.interface._compat import PYTHON3
        with warnings.catch_warnings(record=True) as log:
            warnings.resetwarnings()
            if not PYTHON3:
                exec(code, globs, locs)
                self.assertEqual(len(log), 0) # no longer warn
                return True
            else:
                try:
                    exec(code, globs, locs)
                except TypeError:
                    return False
                else:
                    if fails_under_py3k:
                        self.fail("Didn't raise TypeError")


class NamedTests(unittest.TestCase):

    def test_class(self):
        from zope.interface.declarations import named

        @named(u'foo')
        class Foo(object):
            pass

        self.assertEqual(Foo.__component_name__, u'foo')

    def test_function(self):
        from zope.interface.declarations import named

        @named(u'foo')
        def doFoo(object):
            pass

        self.assertEqual(doFoo.__component_name__, u'foo')

    def test_instance(self):
        from zope.interface.declarations import named

        class Foo(object):
            pass
        foo = Foo()
        named(u'foo')(foo)

        self.assertEqual(foo.__component_name__, u'foo')


class DeclarationTests(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.declarations import Declaration
        return Declaration

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def test_ctor_no_bases(self):
        decl = self._makeOne()
        self.assertEqual(list(decl.__bases__), [])

    def test_ctor_w_interface_in_bases(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        decl = self._makeOne(IFoo)
        self.assertEqual(list(decl.__bases__), [IFoo])

    def test_ctor_w_implements_in_bases(self):
        from zope.interface.declarations import Implements
        impl = Implements()
        decl = self._makeOne(impl)
        self.assertEqual(list(decl.__bases__), [impl])

    def test_changed_wo_existing__v_attrs(self):
        decl = self._makeOne()
        decl.changed(decl) # doesn't raise
        self.assertFalse('_v_attrs' in decl.__dict__)

    def test_changed_w_existing__v_attrs(self):
        decl = self._makeOne()
        decl._v_attrs = object()
        decl.changed(decl)
        self.assertFalse('_v_attrs' in decl.__dict__)

    def test___contains__w_self(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        decl = self._makeOne()
        self.assertFalse(decl in decl)

    def test___contains__w_unrelated_iface(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        decl = self._makeOne()
        self.assertFalse(IFoo in decl)

    def test___contains__w_base_interface(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        decl = self._makeOne(IFoo)
        self.assertTrue(IFoo in decl)

    def test___iter___empty(self):
        decl = self._makeOne()
        self.assertEqual(list(decl), [])

    def test___iter___single_base(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        decl = self._makeOne(IFoo)
        self.assertEqual(list(decl), [IFoo])

    def test___iter___multiple_bases(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        decl = self._makeOne(IFoo, IBar)
        self.assertEqual(list(decl), [IFoo, IBar])

    def test___iter___inheritance(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar', (IFoo,))
        decl = self._makeOne(IBar)
        self.assertEqual(list(decl), [IBar]) #IBar.interfaces() omits bases

    def test___iter___w_nested_sequence_overlap(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        decl = self._makeOne(IBar, (IFoo, IBar))
        self.assertEqual(list(decl), [IBar, IFoo])

    def test_flattened_empty(self):
        from zope.interface.interface import Interface
        decl = self._makeOne()
        self.assertEqual(list(decl.flattened()), [Interface])

    def test_flattened_single_base(self):
        from zope.interface.interface import Interface
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        decl = self._makeOne(IFoo)
        self.assertEqual(list(decl.flattened()), [IFoo, Interface])

    def test_flattened_multiple_bases(self):
        from zope.interface.interface import Interface
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        decl = self._makeOne(IFoo, IBar)
        self.assertEqual(list(decl.flattened()), [IFoo, IBar, Interface])

    def test_flattened_inheritance(self):
        from zope.interface.interface import Interface
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar', (IFoo,))
        decl = self._makeOne(IBar)
        self.assertEqual(list(decl.flattened()), [IBar, IFoo, Interface])

    def test_flattened_w_nested_sequence_overlap(self):
        from zope.interface.interface import Interface
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        decl = self._makeOne(IBar, (IFoo, IBar))
        # Note that decl.__iro__ has IFoo first.
        self.assertEqual(list(decl.flattened()), [IFoo, IBar, Interface])

    def test___sub___unrelated_interface(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        before = self._makeOne(IFoo)
        after = before - IBar
        self.assertTrue(isinstance(after, self._getTargetClass()))
        self.assertEqual(list(after), [IFoo])

    def test___sub___related_interface(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        before = self._makeOne(IFoo)
        after = before - IFoo
        self.assertEqual(list(after), [])

    def test___sub___related_interface_by_inheritance(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar', (IFoo,))
        before = self._makeOne(IBar)
        after = before - IBar
        self.assertEqual(list(after), [])

    def test___add___unrelated_interface(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        before = self._makeOne(IFoo)
        after = before + IBar
        self.assertTrue(isinstance(after, self._getTargetClass()))
        self.assertEqual(list(after), [IFoo, IBar])

    def test___add___related_interface(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        IBaz = InterfaceClass('IBaz')
        before = self._makeOne(IFoo, IBar)
        other = self._makeOne(IBar, IBaz)
        after = before + other
        self.assertEqual(list(after), [IFoo, IBar, IBaz])


class TestImplements(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.declarations import Implements
        return Implements

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def test_ctor_no_bases(self):
        impl = self._makeOne()
        self.assertEqual(impl.inherit, None)
        self.assertEqual(impl.declared, ())
        self.assertEqual(impl.__name__, '?')
        self.assertEqual(list(impl.__bases__), [])

    def test___repr__(self):
        impl = self._makeOne()
        impl.__name__ = 'Testing'
        self.assertEqual(repr(impl), '<implementedBy Testing>')

    def test___reduce__(self):
        from zope.interface.declarations import implementedBy
        impl = self._makeOne()
        self.assertEqual(impl.__reduce__(), (implementedBy, (None,)))

    def test_sort(self):
        from zope.interface.declarations import implementedBy
        class A(object):
            pass
        class B(object):
            pass
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')

        self.assertEqual(implementedBy(A), implementedBy(A))
        self.assertEqual(hash(implementedBy(A)), hash(implementedBy(A)))
        self.assertTrue(implementedBy(A) < None)
        self.assertTrue(None > implementedBy(A))
        self.assertTrue(implementedBy(A) < implementedBy(B))
        self.assertTrue(implementedBy(A) > IFoo)
        self.assertTrue(implementedBy(A) <= implementedBy(B))
        self.assertTrue(implementedBy(A) >= IFoo)
        self.assertTrue(implementedBy(A) != IFoo)

    def test_proxy_equality(self):
        # https://github.com/zopefoundation/zope.interface/issues/55
        class Proxy(object):
            def __init__(self, wrapped):
                self._wrapped = wrapped

            def __getattr__(self, name):
                return getattr(self._wrapped, name)

            def __eq__(self, other):
                return self._wrapped == other

            def __ne__(self, other):
                return self._wrapped != other

        from zope.interface.declarations import implementedBy
        class A(object):
            pass

        class B(object):
            pass

        implementedByA = implementedBy(A)
        implementedByB = implementedBy(B)
        proxy = Proxy(implementedByA)

        # The order of arguments to the operators matters,
        # test both
        self.assertTrue(implementedByA == implementedByA)
        self.assertTrue(implementedByA != implementedByB)
        self.assertTrue(implementedByB != implementedByA)

        self.assertTrue(proxy == implementedByA)
        self.assertTrue(implementedByA == proxy)
        self.assertFalse(proxy != implementedByA)
        self.assertFalse(implementedByA != proxy)

        self.assertTrue(proxy != implementedByB)
        self.assertTrue(implementedByB != proxy)


class Test_implementedByFallback(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import implementedByFallback
        return implementedByFallback(*args, **kw)

    def test_dictless_wo_existing_Implements_wo_registrations(self):
        class Foo(object):
            __slots__ = ('__implemented__',)
        foo = Foo()
        foo.__implemented__ = None
        self.assertEqual(list(self._callFUT(foo)), [])

    def test_dictless_wo_existing_Implements_cant_assign___implemented__(self):
        class Foo(object):
            def _get_impl(self): return None
            def _set_impl(self, val): raise TypeError
            __implemented__ = property(_get_impl, _set_impl)
            def __call__(self): pass  #act like a factory
        foo = Foo()
        self.assertRaises(TypeError, self._callFUT, foo)

    def test_dictless_wo_existing_Implements_w_registrations(self):
        from zope.interface import declarations
        class Foo(object):
            __slots__ = ('__implemented__',)
        foo = Foo()
        foo.__implemented__ = None
        reg = object()
        with _MonkeyDict(declarations,
                         'BuiltinImplementationSpecifications') as specs:
            specs[foo] = reg
            self.assertTrue(self._callFUT(foo) is reg)

    def test_dictless_w_existing_Implements(self):
        from zope.interface.declarations import Implements
        impl = Implements()
        class Foo(object):
            __slots__ = ('__implemented__',)
        foo = Foo()
        foo.__implemented__ = impl
        self.assertTrue(self._callFUT(foo) is impl)

    def test_dictless_w_existing_not_Implements(self):
        from zope.interface.interface import InterfaceClass
        class Foo(object):
            __slots__ = ('__implemented__',)
        foo = Foo()
        IFoo = InterfaceClass('IFoo')
        foo.__implemented__ = (IFoo,)
        self.assertEqual(list(self._callFUT(foo)), [IFoo])

    def test_w_existing_attr_as_Implements(self):
        from zope.interface.declarations import Implements
        impl = Implements()
        class Foo(object):
            __implemented__ = impl
        self.assertTrue(self._callFUT(Foo) is impl)

    def test_builtins_added_to_cache(self):
        from zope.interface import declarations
        from zope.interface.declarations import Implements
        from zope.interface._compat import _BUILTINS
        with _MonkeyDict(declarations,
                         'BuiltinImplementationSpecifications') as specs:
            self.assertEqual(list(self._callFUT(tuple)), [])
            self.assertEqual(list(self._callFUT(list)), [])
            self.assertEqual(list(self._callFUT(dict)), [])
            for typ in (tuple, list, dict):
                spec = specs[typ]
                self.assertTrue(isinstance(spec, Implements))
                self.assertEqual(repr(spec),
                                '<implementedBy %s.%s>'
                                    % (_BUILTINS, typ.__name__))

    def test_builtins_w_existing_cache(self):
        from zope.interface import declarations
        t_spec, l_spec, d_spec = object(), object(), object()
        with _MonkeyDict(declarations,
                         'BuiltinImplementationSpecifications') as specs:
            specs[tuple] = t_spec
            specs[list] = l_spec
            specs[dict] = d_spec
            self.assertTrue(self._callFUT(tuple) is t_spec)
            self.assertTrue(self._callFUT(list) is l_spec)
            self.assertTrue(self._callFUT(dict) is d_spec)

    def test_oldstyle_class_no_assertions(self):
        # TODO: Figure out P3 story
        class Foo:
            pass
        self.assertEqual(list(self._callFUT(Foo)), [])

    def test_no_assertions(self):
        # TODO: Figure out P3 story
        class Foo(object):
            pass
        self.assertEqual(list(self._callFUT(Foo)), [])

    def test_w_None_no_bases_not_factory(self):
        class Foo(object):
            __implemented__ = None
        foo = Foo()
        self.assertRaises(TypeError, self._callFUT, foo)

    def test_w_None_no_bases_w_factory(self):
        from zope.interface.declarations import objectSpecificationDescriptor
        class Foo(object):
            __implemented__ = None
            def __call__(self):
                pass
        foo = Foo()
        foo.__name__ = 'foo'
        spec = self._callFUT(foo)
        self.assertEqual(spec.__name__,
                         'zope.interface.tests.test_declarations.foo')
        self.assertTrue(spec.inherit is foo)
        self.assertTrue(foo.__implemented__ is spec)
        self.assertTrue(foo.__providedBy__ is objectSpecificationDescriptor)
        self.assertFalse('__provides__' in foo.__dict__)

    def test_w_None_no_bases_w_class(self):
        from zope.interface.declarations import ClassProvides
        class Foo(object):
            __implemented__ = None
        spec = self._callFUT(Foo)
        self.assertEqual(spec.__name__,
                         'zope.interface.tests.test_declarations.Foo')
        self.assertTrue(spec.inherit is Foo)
        self.assertTrue(Foo.__implemented__ is spec)
        self.assertTrue(isinstance(Foo.__providedBy__, ClassProvides))
        self.assertTrue(isinstance(Foo.__provides__, ClassProvides))
        self.assertEqual(Foo.__provides__, Foo.__providedBy__)

    def test_w_existing_Implements(self):
        from zope.interface.declarations import Implements
        impl = Implements()
        class Foo(object):
            __implemented__ = impl
        self.assertTrue(self._callFUT(Foo) is impl)


class Test_implementedBy(Test_implementedByFallback):
    # Repeat tests for C optimizations

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import implementedBy
        return implementedBy(*args, **kw)


class Test_classImplementsOnly(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import classImplementsOnly
        return classImplementsOnly(*args, **kw)

    def test_no_existing(self):
        from zope.interface.declarations import ClassProvides
        from zope.interface.interface import InterfaceClass
        class Foo(object):
            pass
        ifoo = InterfaceClass('IFoo')
        self._callFUT(Foo, ifoo)
        spec = Foo.__implemented__
        self.assertEqual(spec.__name__,
                         'zope.interface.tests.test_declarations.Foo')
        self.assertTrue(spec.inherit is None)
        self.assertTrue(Foo.__implemented__ is spec)
        self.assertTrue(isinstance(Foo.__providedBy__, ClassProvides))
        self.assertTrue(isinstance(Foo.__provides__, ClassProvides))
        self.assertEqual(Foo.__provides__, Foo.__providedBy__)

    def test_w_existing_Implements(self):
        from zope.interface.declarations import Implements
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        impl = Implements(IFoo)
        impl.declared = (IFoo,)
        class Foo(object):
            __implemented__ = impl
        impl.inherit = Foo
        self._callFUT(Foo, IBar)
        # Same spec, now different values
        self.assertTrue(Foo.__implemented__ is impl)
        self.assertEqual(impl.inherit, None)
        self.assertEqual(impl.declared, (IBar,))


class Test_classImplements(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import classImplements
        return classImplements(*args, **kw)

    def test_no_existing(self):
        from zope.interface.declarations import ClassProvides
        from zope.interface.interface import InterfaceClass
        class Foo(object):
            pass
        IFoo = InterfaceClass('IFoo')
        self._callFUT(Foo, IFoo)
        spec = Foo.__implemented__
        self.assertEqual(spec.__name__,
                         'zope.interface.tests.test_declarations.Foo')
        self.assertTrue(spec.inherit is Foo)
        self.assertTrue(Foo.__implemented__ is spec)
        self.assertTrue(isinstance(Foo.__providedBy__, ClassProvides))
        self.assertTrue(isinstance(Foo.__provides__, ClassProvides))
        self.assertEqual(Foo.__provides__, Foo.__providedBy__)

    def test_w_existing_Implements(self):
        from zope.interface.declarations import Implements
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        impl = Implements(IFoo)
        impl.declared = (IFoo,)
        class Foo(object):
            __implemented__ = impl
        impl.inherit = Foo
        self._callFUT(Foo, IBar)
        # Same spec, now different values
        self.assertTrue(Foo.__implemented__ is impl)
        self.assertEqual(impl.inherit, Foo)
        self.assertEqual(impl.declared, (IFoo, IBar,))

    def test_w_existing_Implements_w_bases(self):
        from zope.interface.declarations import Implements
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        IBaz = InterfaceClass('IBaz', IFoo)
        b_impl = Implements(IBaz)
        impl = Implements(IFoo)
        impl.declared = (IFoo,)
        class Base1(object):
            __implemented__ = b_impl
        class Base2(object):
            __implemented__ = b_impl
        class Foo(Base1, Base2):
            __implemented__ = impl
        impl.inherit = Foo
        self._callFUT(Foo, IBar)
        # Same spec, now different values
        self.assertTrue(Foo.__implemented__ is impl)
        self.assertEqual(impl.inherit, Foo)
        self.assertEqual(impl.declared, (IFoo, IBar,))
        self.assertEqual(impl.__bases__, (IFoo, IBar, b_impl))


class Test__implements_advice(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import _implements_advice
        return _implements_advice(*args, **kw)

    def test_no_existing_implements(self):
        from zope.interface.declarations import classImplements
        from zope.interface.declarations import Implements
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        class Foo(object):
            __implements_advice_data__ = ((IFoo,), classImplements)
        self._callFUT(Foo)
        self.assertFalse('__implements_advice_data__' in Foo.__dict__)
        self.assertTrue(isinstance(Foo.__implemented__, Implements))
        self.assertEqual(list(Foo.__implemented__), [IFoo])


class Test_implementer(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.declarations import implementer
        return implementer

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def test_oldstyle_class(self):
        # TODO Py3 story
        from zope.interface.declarations import ClassProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        class Foo:
            pass
        decorator = self._makeOne(IFoo)
        returned = decorator(Foo)
        self.assertTrue(returned is Foo)
        spec = Foo.__implemented__
        self.assertEqual(spec.__name__,
                         'zope.interface.tests.test_declarations.Foo')
        self.assertTrue(spec.inherit is Foo)
        self.assertTrue(Foo.__implemented__ is spec)
        self.assertTrue(isinstance(Foo.__providedBy__, ClassProvides))
        self.assertTrue(isinstance(Foo.__provides__, ClassProvides))
        self.assertEqual(Foo.__provides__, Foo.__providedBy__)

    def test_newstyle_class(self):
        from zope.interface.declarations import ClassProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        class Foo(object):
            pass
        decorator = self._makeOne(IFoo)
        returned = decorator(Foo)
        self.assertTrue(returned is Foo)
        spec = Foo.__implemented__
        self.assertEqual(spec.__name__,
                         'zope.interface.tests.test_declarations.Foo')
        self.assertTrue(spec.inherit is Foo)
        self.assertTrue(Foo.__implemented__ is spec)
        self.assertTrue(isinstance(Foo.__providedBy__, ClassProvides))
        self.assertTrue(isinstance(Foo.__provides__, ClassProvides))
        self.assertEqual(Foo.__provides__, Foo.__providedBy__)

    def test_nonclass_cannot_assign_attr(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        decorator = self._makeOne(IFoo)
        self.assertRaises(TypeError, decorator, object())

    def test_nonclass_can_assign_attr(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        class Foo(object):
            pass
        foo = Foo()
        decorator = self._makeOne(IFoo)
        returned = decorator(foo)
        self.assertTrue(returned is foo)
        spec = foo.__implemented__
        self.assertEqual(spec.__name__, 'zope.interface.tests.test_declarations.?')
        self.assertTrue(spec.inherit is None)
        self.assertTrue(foo.__implemented__ is spec)


class Test_implementer_only(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.declarations import implementer_only
        return implementer_only

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def test_function(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        decorator = self._makeOne(IFoo)
        def _function(): pass
        self.assertRaises(ValueError, decorator, _function)

    def test_method(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        decorator = self._makeOne(IFoo)
        class Bar:
            def _method(): pass
        self.assertRaises(ValueError, decorator, Bar._method)

    def test_oldstyle_class(self):
        # TODO Py3 story
        from zope.interface.declarations import Implements
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        old_spec = Implements(IBar)
        class Foo:
            __implemented__ = old_spec
        decorator = self._makeOne(IFoo)
        returned = decorator(Foo)
        self.assertTrue(returned is Foo)
        spec = Foo.__implemented__
        self.assertEqual(spec.__name__, '?')
        self.assertTrue(spec.inherit is None)
        self.assertTrue(Foo.__implemented__ is spec)

    def test_newstyle_class(self):
        from zope.interface.declarations import Implements
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass('IFoo')
        IBar = InterfaceClass('IBar')
        old_spec = Implements(IBar)
        class Foo(object):
            __implemented__ = old_spec
        decorator = self._makeOne(IFoo)
        returned = decorator(Foo)
        self.assertTrue(returned is Foo)
        spec = Foo.__implemented__
        self.assertEqual(spec.__name__, '?')
        self.assertTrue(spec.inherit is None)
        self.assertTrue(Foo.__implemented__ is spec)


# Test '_implements' by way of 'implements{,Only}', its only callers.

class Test_implementsOnly(unittest.TestCase, _Py3ClassAdvice):

    def _getFUT(self):
        from zope.interface.declarations import implementsOnly
        return implementsOnly

    def test_simple(self):
        import warnings
        from zope.interface.declarations import implementsOnly
        from zope.interface._compat import PYTHON3
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        globs = {'implementsOnly': implementsOnly,
                 'IFoo': IFoo,
                }
        locs = {}
        CODE = "\n".join([
            'class Foo(object):'
            '    implementsOnly(IFoo)',
            ])
        with warnings.catch_warnings(record=True) as log:
            warnings.resetwarnings()
            try:
                exec(CODE, globs, locs)
            except TypeError:
                if not PYTHON3:
                    raise
            else:
                if PYTHON3:
                    self.fail("Didn't raise TypeError")
                Foo = locs['Foo']
                spec = Foo.__implemented__
                self.assertEqual(list(spec), [IFoo])
                self.assertEqual(len(log), 0) # no longer warn

    def test_called_once_from_class_w_bases(self):
        from zope.interface.declarations import implements
        from zope.interface.declarations import implementsOnly
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        IBar = InterfaceClass("IBar")
        globs = {'implements': implements,
                 'implementsOnly': implementsOnly,
                 'IFoo': IFoo,
                 'IBar': IBar,
                }
        locs = {}
        CODE = "\n".join([
            'class Foo(object):',
            '    implements(IFoo)',
            'class Bar(Foo):'
            '    implementsOnly(IBar)',
            ])
        if self._run_generated_code(CODE, globs, locs):
            Bar = locs['Bar']
            spec = Bar.__implemented__
            self.assertEqual(list(spec), [IBar])


class Test_implements(unittest.TestCase, _Py3ClassAdvice):

    def _getFUT(self):
        from zope.interface.declarations import implements
        return implements

    def test_called_from_function(self):
        import warnings
        from zope.interface.declarations import implements
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        globs = {'implements': implements, 'IFoo': IFoo}
        locs = {}
        CODE = "\n".join([
            'def foo():',
            '    implements(IFoo)'
            ])
        if self._run_generated_code(CODE, globs, locs, False):
            foo = locs['foo']
            with warnings.catch_warnings(record=True) as log:
                warnings.resetwarnings()
                self.assertRaises(TypeError, foo)
                self.assertEqual(len(log), 0) # no longer warn

    def test_called_twice_from_class(self):
        import warnings
        from zope.interface.declarations import implements
        from zope.interface.interface import InterfaceClass
        from zope.interface._compat import PYTHON3
        IFoo = InterfaceClass("IFoo")
        IBar = InterfaceClass("IBar")
        globs = {'implements': implements, 'IFoo': IFoo, 'IBar': IBar}
        locs = {}
        CODE = "\n".join([
            'class Foo(object):',
            '    implements(IFoo)',
            '    implements(IBar)',
            ])
        with warnings.catch_warnings(record=True) as log:
            warnings.resetwarnings()
            try:
                exec(CODE, globs, locs)
            except TypeError:
                if not PYTHON3:
                    self.assertEqual(len(log), 0) # no longer warn
            else:
                self.fail("Didn't raise TypeError")

    def test_called_once_from_class(self):
        from zope.interface.declarations import implements
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        globs = {'implements': implements, 'IFoo': IFoo}
        locs = {}
        CODE = "\n".join([
            'class Foo(object):',
            '    implements(IFoo)',
            ])
        if self._run_generated_code(CODE, globs, locs):
            Foo = locs['Foo']
            spec = Foo.__implemented__
            self.assertEqual(list(spec), [IFoo])


class ProvidesClassTests(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.declarations import ProvidesClass
        return ProvidesClass

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def test_simple_class_one_interface(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        spec = self._makeOne(Foo, IFoo)
        self.assertEqual(list(spec), [IFoo])

    def test___reduce__(self):
        from zope.interface.declarations import Provides # the function
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        spec = self._makeOne(Foo, IFoo)
        klass, args = spec.__reduce__()
        self.assertTrue(klass is Provides)
        self.assertEqual(args, (Foo, IFoo))

    def test___get___class(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        spec = self._makeOne(Foo, IFoo)
        Foo.__provides__ = spec
        self.assertTrue(Foo.__provides__ is spec)

    def test___get___instance(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        spec = self._makeOne(Foo, IFoo)
        Foo.__provides__ = spec
        def _test():
            foo = Foo()
            return foo.__provides__
        self.assertRaises(AttributeError, _test)


class Test_Provides(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import Provides
        return Provides(*args, **kw)

    def test_no_cached_spec(self):
        from zope.interface import declarations
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        cache = {}
        class Foo(object):
            pass
        with _Monkey(declarations, InstanceDeclarations=cache):
            spec = self._callFUT(Foo, IFoo)
        self.assertEqual(list(spec), [IFoo])
        self.assertTrue(cache[(Foo, IFoo)] is spec)

    def test_w_cached_spec(self):
        from zope.interface import declarations
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        prior = object()
        class Foo(object):
            pass
        cache = {(Foo, IFoo): prior}
        with _Monkey(declarations, InstanceDeclarations=cache):
            spec = self._callFUT(Foo, IFoo)
        self.assertTrue(spec is prior)


class Test_directlyProvides(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import directlyProvides
        return directlyProvides(*args, **kw)

    def test_w_normal_object(self):
        from zope.interface.declarations import ProvidesClass
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        obj = Foo()
        self._callFUT(obj, IFoo)
        self.assertTrue(isinstance(obj.__provides__, ProvidesClass))
        self.assertEqual(list(obj.__provides__), [IFoo])

    def test_w_class(self):
        from zope.interface.declarations import ClassProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        self._callFUT(Foo, IFoo)
        self.assertTrue(isinstance(Foo.__provides__, ClassProvides))
        self.assertEqual(list(Foo.__provides__), [IFoo])

    @_skip_under_py3k
    def test_w_non_descriptor_aware_metaclass(self):
        # There are no non-descriptor-aware types in Py3k
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class MetaClass(type):
            def __getattribute__(self, name):
                # Emulate metaclass whose base is not the type object.
                if name == '__class__':
                    return self
                return type.__getattribute__(self, name)
        class Foo(object):
            __metaclass__ = MetaClass
        obj = Foo()
        self.assertRaises(TypeError, self._callFUT, obj, IFoo)

    def test_w_classless_object(self):
        from zope.interface.declarations import ProvidesClass
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        the_dict = {}
        class Foo(object):
            def __getattribute__(self, name):
                # Emulate object w/o any class
                if name == '__class__':
                    return None
                try:
                    return the_dict[name]
                except KeyError:
                    raise AttributeError(name)
            def __setattr__(self, name, value):
                the_dict[name] = value
        obj = Foo()
        self._callFUT(obj, IFoo)
        self.assertTrue(isinstance(the_dict['__provides__'], ProvidesClass))
        self.assertEqual(list(the_dict['__provides__']), [IFoo])


class Test_alsoProvides(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import alsoProvides
        return alsoProvides(*args, **kw)

    def test_wo_existing_provides(self):
        from zope.interface.declarations import ProvidesClass
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        obj = Foo()
        self._callFUT(obj, IFoo)
        self.assertTrue(isinstance(obj.__provides__, ProvidesClass))
        self.assertEqual(list(obj.__provides__), [IFoo])

    def test_w_existing_provides(self):
        from zope.interface.declarations import directlyProvides
        from zope.interface.declarations import ProvidesClass
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        IBar = InterfaceClass("IBar")
        class Foo(object):
            pass
        obj = Foo()
        directlyProvides(obj, IFoo)
        self._callFUT(obj, IBar)
        self.assertTrue(isinstance(obj.__provides__, ProvidesClass))
        self.assertEqual(list(obj.__provides__), [IFoo, IBar])


class Test_noLongerProvides(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import noLongerProvides
        return noLongerProvides(*args, **kw)

    def test_wo_existing_provides(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        obj = Foo()
        self._callFUT(obj, IFoo)
        self.assertEqual(list(obj.__provides__), [])

    def test_w_existing_provides_hit(self):
        from zope.interface.declarations import directlyProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        obj = Foo()
        directlyProvides(obj, IFoo)
        self._callFUT(obj, IFoo)
        self.assertEqual(list(obj.__provides__), [])

    def test_w_existing_provides_miss(self):
        from zope.interface.declarations import directlyProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        IBar = InterfaceClass("IBar")
        class Foo(object):
            pass
        obj = Foo()
        directlyProvides(obj, IFoo)
        self._callFUT(obj, IBar)
        self.assertEqual(list(obj.__provides__), [IFoo])

    def test_w_iface_implemented_by_class(self):
        from zope.interface.declarations import implementer
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        @implementer(IFoo)
        class Foo(object):
            pass
        obj = Foo()
        self.assertRaises(ValueError, self._callFUT, obj, IFoo)


class ClassProvidesBaseFallbackTests(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.declarations import ClassProvidesBaseFallback
        return ClassProvidesBaseFallback

    def _makeOne(self, klass, implements):
        # Don't instantiate directly:  the C version can't have attributes
        # assigned.
        class Derived(self._getTargetClass()):
            def __init__(self, k, i):
                self._cls = k
                self._implements = i
        return Derived(klass, implements)

    def test_w_same_class_via_class(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        cpbp = Foo.__provides__ = self._makeOne(Foo, IFoo)
        self.assertTrue(Foo.__provides__ is cpbp)

    def test_w_same_class_via_instance(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        foo = Foo()
        cpbp = Foo.__provides__ = self._makeOne(Foo, IFoo)
        self.assertTrue(foo.__provides__ is IFoo)

    def test_w_different_class(self):
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        class Bar(Foo):
            pass
        bar = Bar()
        cpbp = Foo.__provides__ = self._makeOne(Foo, IFoo)
        self.assertRaises(AttributeError, getattr, Bar, '__provides__')
        self.assertRaises(AttributeError, getattr, bar, '__provides__')


class ClassProvidesBaseTests(ClassProvidesBaseFallbackTests):
    # Repeat tests for C optimizations

    def _getTargetClass(self):
        from zope.interface.declarations import ClassProvidesBase
        return ClassProvidesBase


class ClassProvidesTests(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.declarations import ClassProvides
        return ClassProvides

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def test_w_simple_metaclass(self):
        from zope.interface.declarations import implementer
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        IBar = InterfaceClass("IBar")
        @implementer(IFoo)
        class Foo(object):
            pass
        cp = Foo.__provides__ = self._makeOne(Foo, type(Foo), IBar)
        self.assertTrue(Foo.__provides__ is cp)
        self.assertEqual(list(Foo().__provides__), [IFoo])

    def test___reduce__(self):
        from zope.interface.declarations import implementer
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        IBar = InterfaceClass("IBar")
        @implementer(IFoo)
        class Foo(object):
            pass
        cp = Foo.__provides__ = self._makeOne(Foo, type(Foo), IBar)
        self.assertEqual(cp.__reduce__(),
                         (self._getTargetClass(), (Foo, type(Foo), IBar)))


class Test_directlyProvidedBy(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import directlyProvidedBy
        return directlyProvidedBy(*args, **kw)

    def test_wo_declarations_in_class_or_instance(self):
        class Foo(object):
            pass
        foo = Foo()
        self.assertEqual(list(self._callFUT(foo)), [])

    def test_w_declarations_in_class_but_not_instance(self):
        from zope.interface.declarations import implementer
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        @implementer(IFoo)
        class Foo(object):
            pass
        foo = Foo()
        self.assertEqual(list(self._callFUT(foo)), [])

    def test_w_declarations_in_instance_but_not_class(self):
        from zope.interface.declarations import directlyProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        foo = Foo()
        directlyProvides(foo, IFoo)
        self.assertEqual(list(self._callFUT(foo)), [IFoo])

    def test_w_declarations_in_instance_and_class(self):
        from zope.interface.declarations import directlyProvides
        from zope.interface.declarations import implementer
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        IBar = InterfaceClass("IBar")
        @implementer(IFoo)
        class Foo(object):
            pass
        foo = Foo()
        directlyProvides(foo, IBar)
        self.assertEqual(list(self._callFUT(foo)), [IBar])


class Test_classProvides(unittest.TestCase, _Py3ClassAdvice):

    def _getFUT(self):
        from zope.interface.declarations import classProvides
        return classProvides

    def test_called_from_function(self):
        import warnings
        from zope.interface.declarations import classProvides
        from zope.interface.interface import InterfaceClass
        from zope.interface._compat import PYTHON3
        IFoo = InterfaceClass("IFoo")
        globs = {'classProvides': classProvides, 'IFoo': IFoo}
        locs = {}
        CODE = "\n".join([
            'def foo():',
            '    classProvides(IFoo)'
            ])
        exec(CODE, globs, locs)
        foo = locs['foo']
        with warnings.catch_warnings(record=True) as log:
            warnings.resetwarnings()
            self.assertRaises(TypeError, foo)
            if not PYTHON3:
                self.assertEqual(len(log), 0) # no longer warn

    def test_called_twice_from_class(self):
        import warnings
        from zope.interface.declarations import classProvides
        from zope.interface.interface import InterfaceClass
        from zope.interface._compat import PYTHON3
        IFoo = InterfaceClass("IFoo")
        IBar = InterfaceClass("IBar")
        globs = {'classProvides': classProvides, 'IFoo': IFoo, 'IBar': IBar}
        locs = {}
        CODE = "\n".join([
            'class Foo(object):',
            '    classProvides(IFoo)',
            '    classProvides(IBar)',
            ])
        with warnings.catch_warnings(record=True) as log:
            warnings.resetwarnings()
            try:
                exec(CODE, globs, locs)
            except TypeError:
                if not PYTHON3:
                    self.assertEqual(len(log), 0) # no longer warn
            else:
                self.fail("Didn't raise TypeError")

    def test_called_once_from_class(self):
        from zope.interface.declarations import classProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        globs = {'classProvides': classProvides, 'IFoo': IFoo}
        locs = {}
        CODE = "\n".join([
            'class Foo(object):',
            '    classProvides(IFoo)',
            ])
        if self._run_generated_code(CODE, globs, locs):
            Foo = locs['Foo']
            spec = Foo.__providedBy__
            self.assertEqual(list(spec), [IFoo])

# Test _classProvides_advice through classProvides, its only caller.


class Test_provider(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.declarations import provider
        return provider

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def test_w_class(self):
        from zope.interface.declarations import ClassProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        @self._makeOne(IFoo)
        class Foo(object):
            pass
        self.assertTrue(isinstance(Foo.__provides__, ClassProvides))
        self.assertEqual(list(Foo.__provides__), [IFoo])


class Test_moduleProvides(unittest.TestCase):

    def _getFUT(self):
        from zope.interface.declarations import moduleProvides
        return moduleProvides

    def test_called_from_function(self):
        from zope.interface.declarations import moduleProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        globs = {'__name__': 'zope.interface.tests.foo',
                 'moduleProvides': moduleProvides, 'IFoo': IFoo}
        locs = {}
        CODE = "\n".join([
            'def foo():',
            '    moduleProvides(IFoo)'
            ])
        exec(CODE, globs, locs)
        foo = locs['foo']
        self.assertRaises(TypeError, foo)

    def test_called_from_class(self):
        from zope.interface.declarations import moduleProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        globs = {'__name__': 'zope.interface.tests.foo',
                 'moduleProvides': moduleProvides, 'IFoo': IFoo}
        locs = {}
        CODE = "\n".join([
            'class Foo(object):',
            '    moduleProvides(IFoo)',
            ])
        try:
            exec(CODE, globs, locs)
        except TypeError:
            pass
        else:
            assert False, 'TypeError not raised'

    def test_called_once_from_module_scope(self):
        from zope.interface.declarations import moduleProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        globs = {'__name__': 'zope.interface.tests.foo',
                 'moduleProvides': moduleProvides, 'IFoo': IFoo}
        CODE = "\n".join([
            'moduleProvides(IFoo)',
            ])
        exec(CODE, globs)
        spec = globs['__provides__']
        self.assertEqual(list(spec), [IFoo])

    def test_called_twice_from_module_scope(self):
        from zope.interface.declarations import moduleProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        globs = {'__name__': 'zope.interface.tests.foo',
                 'moduleProvides': moduleProvides, 'IFoo': IFoo}
        locs = {}
        CODE = "\n".join([
            'moduleProvides(IFoo)',
            'moduleProvides(IFoo)',
            ])
        try:
            exec(CODE, globs)
        except TypeError:
            pass
        else:
            assert False, 'TypeError not raised'


class Test_getObjectSpecificationFallback(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import getObjectSpecificationFallback
        return getObjectSpecificationFallback(*args, **kw)

    def test_wo_existing_provides_classless(self):
        the_dict = {}
        class Foo(object):
            def __getattribute__(self, name):
                # Emulate object w/o any class
                if name == '__class__':
                    raise AttributeError(name)
                try:
                    return the_dict[name]
                except KeyError:
                    raise AttributeError(name)
            def __setattr__(self, name, value):
                the_dict[name] = value
        foo = Foo()
        spec = self._callFUT(foo)
        self.assertEqual(list(spec), [])

    def test_existing_provides_is_spec(self):
        from zope.interface.declarations import directlyProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        def foo():
            pass
        directlyProvides(foo, IFoo)
        spec = self._callFUT(foo)
        self.assertTrue(spec is foo.__provides__)

    def test_existing_provides_is_not_spec(self):
        def foo():
            pass
        foo.__provides__ = object() # not a valid spec
        spec = self._callFUT(foo)
        self.assertEqual(list(spec), [])

    def test_existing_provides(self):
        from zope.interface.declarations import directlyProvides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        foo = Foo()
        directlyProvides(foo, IFoo)
        spec = self._callFUT(foo)
        self.assertEqual(list(spec), [IFoo])

    def test_wo_provides_on_class_w_implements(self):
        from zope.interface.declarations import implementer
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        @implementer(IFoo)
        class Foo(object):
            pass
        foo = Foo()
        spec = self._callFUT(foo)
        self.assertEqual(list(spec), [IFoo])

    def test_wo_provides_on_class_wo_implements(self):
        class Foo(object):
            pass
        foo = Foo()
        spec = self._callFUT(foo)
        self.assertEqual(list(spec), [])


class Test_getObjectSpecification(Test_getObjectSpecificationFallback):
    # Repeat tests for C optimizations

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import getObjectSpecification
        return getObjectSpecification(*args, **kw)


class Test_providedByFallback(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import providedByFallback
        return providedByFallback(*args, **kw)

    def test_wo_providedBy_on_class_wo_implements(self):
        class Foo(object):
            pass
        foo = Foo()
        spec = self._callFUT(foo)
        self.assertEqual(list(spec), [])

    def test_w_providedBy_valid_spec(self):
        from zope.interface.declarations import Provides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        foo = Foo()
        foo.__providedBy__ = Provides(Foo, IFoo)
        spec = self._callFUT(foo)
        self.assertEqual(list(spec), [IFoo])

    def test_w_providedBy_invalid_spec(self):
        class Foo(object):
            pass
        foo = Foo()
        foo.__providedBy__ = object()
        spec = self._callFUT(foo)
        self.assertEqual(list(spec), [])

    def test_w_providedBy_invalid_spec_class_w_implements(self):
        from zope.interface.declarations import implementer
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        @implementer(IFoo)
        class Foo(object):
            pass
        foo = Foo()
        foo.__providedBy__ = object()
        spec = self._callFUT(foo)
        self.assertEqual(list(spec), [IFoo])

    def test_w_providedBy_invalid_spec_w_provides_no_provides_on_class(self):
        class Foo(object):
            pass
        foo = Foo()
        foo.__providedBy__ = object()
        expected = foo.__provides__ = object()
        spec = self._callFUT(foo)
        self.assertTrue(spec is expected)

    def test_w_providedBy_invalid_spec_w_provides_diff_provides_on_class(self):
        class Foo(object):
            pass
        foo = Foo()
        foo.__providedBy__ = object()
        expected = foo.__provides__ = object()
        Foo.__provides__ = object()
        spec = self._callFUT(foo)
        self.assertTrue(spec is expected)

    def test_w_providedBy_invalid_spec_w_provides_same_provides_on_class(self):
        from zope.interface.declarations import implementer
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        @implementer(IFoo)
        class Foo(object):
            pass
        foo = Foo()
        foo.__providedBy__ = object()
        foo.__provides__ = Foo.__provides__ = object()
        spec = self._callFUT(foo)
        self.assertEqual(list(spec), [IFoo])


class Test_providedBy(Test_providedByFallback):
    # Repeat tests for C optimizations

    def _callFUT(self, *args, **kw):
        from zope.interface.declarations import providedBy
        return providedBy(*args, **kw)


class ObjectSpecificationDescriptorFallbackTests(unittest.TestCase):

    def _getTargetClass(self):
        from zope.interface.declarations \
            import ObjectSpecificationDescriptorFallback
        return ObjectSpecificationDescriptorFallback

    def _makeOne(self, *args, **kw):
        return self._getTargetClass()(*args, **kw)

    def test_accessed_via_class(self):
        from zope.interface.declarations import Provides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        class Foo(object):
            pass
        Foo.__provides__ = Provides(Foo, IFoo)
        Foo.__providedBy__ = self._makeOne()
        self.assertEqual(list(Foo.__providedBy__), [IFoo])

    def test_accessed_via_inst_wo_provides(self):
        from zope.interface.declarations import implementer
        from zope.interface.declarations import Provides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        IBar = InterfaceClass("IBar")
        @implementer(IFoo)
        class Foo(object):
            pass
        Foo.__provides__ = Provides(Foo, IBar)
        Foo.__providedBy__ = self._makeOne()
        foo = Foo()
        self.assertEqual(list(foo.__providedBy__), [IFoo])

    def test_accessed_via_inst_w_provides(self):
        from zope.interface.declarations import directlyProvides
        from zope.interface.declarations import implementer
        from zope.interface.declarations import Provides
        from zope.interface.interface import InterfaceClass
        IFoo = InterfaceClass("IFoo")
        IBar = InterfaceClass("IBar")
        IBaz = InterfaceClass("IBaz")
        @implementer(IFoo)
        class Foo(object):
            pass
        Foo.__provides__ = Provides(Foo, IBar)
        Foo.__providedBy__ = self._makeOne()
        foo = Foo()
        directlyProvides(foo, IBaz)
        self.assertEqual(list(foo.__providedBy__), [IBaz, IFoo])


class ObjectSpecificationDescriptorTests(
                ObjectSpecificationDescriptorFallbackTests):
    # Repeat tests for C optimizations

    def _getTargetClass(self):
        from zope.interface.declarations import ObjectSpecificationDescriptor
        return ObjectSpecificationDescriptor


# Test _normalizeargs through its callers.


class _Monkey(object):
    # context-manager for replacing module names in the scope of a test.
    def __init__(self, module, **kw):
        self.module = module
        self.to_restore = dict([(key, getattr(module, key)) for key in kw])
        for key, value in kw.items():
            setattr(module, key, value)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for key, value in self.to_restore.items():
            setattr(self.module, key, value)


class _MonkeyDict(object):
    # context-manager for restoring a dict w/in a module in the scope of a test.
    def __init__(self, module, attrname, **kw):
        self.module = module
        self.target = getattr(module, attrname)
        self.to_restore = self.target.copy()
        self.target.clear()
        self.target.update(kw)

    def __enter__(self):
        return self.target

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.target.clear()
        self.target.update(self.to_restore)


def test_suite():
    return unittest.TestSuite((
        unittest.makeSuite(DeclarationTests),
        unittest.makeSuite(TestImplements),
        unittest.makeSuite(Test_implementedByFallback),
        unittest.makeSuite(Test_implementedBy),
        unittest.makeSuite(Test_classImplementsOnly),
        unittest.makeSuite(Test_classImplements),
        unittest.makeSuite(Test__implements_advice),
        unittest.makeSuite(Test_implementer),
        unittest.makeSuite(Test_implementer_only),
        unittest.makeSuite(Test_implements),
        unittest.makeSuite(Test_implementsOnly),
        unittest.makeSuite(ProvidesClassTests),
        unittest.makeSuite(Test_Provides),
        unittest.makeSuite(Test_directlyProvides),
        unittest.makeSuite(Test_alsoProvides),
        unittest.makeSuite(Test_noLongerProvides),
        unittest.makeSuite(ClassProvidesBaseFallbackTests),
        unittest.makeSuite(ClassProvidesTests),
        unittest.makeSuite(Test_directlyProvidedBy),
        unittest.makeSuite(Test_classProvides),
        unittest.makeSuite(Test_provider),
        unittest.makeSuite(Test_moduleProvides),
        unittest.makeSuite(Test_getObjectSpecificationFallback),
        unittest.makeSuite(Test_getObjectSpecification),
        unittest.makeSuite(Test_providedByFallback),
        unittest.makeSuite(Test_providedBy),
        unittest.makeSuite(ObjectSpecificationDescriptorFallbackTests),
        unittest.makeSuite(ObjectSpecificationDescriptorTests),
    ))
