from operator import getitem

from testfixtures import (
    Replacer,
    Replace,
    ShouldRaise,
    TempDirectory,
    replace,
    compare,
    not_there,
    replace_in_environ,
    replace_on_class,
    replace_in_module,
    )
from unittest import TestCase

import os

from testfixtures.mock import Mock
from testfixtures.tests import sample1, sample3
from testfixtures.tests import sample2
from .sample1 import z, X
from .sample3 import SOME_CONSTANT
from ..compat import PY_310_PLUS

from warnings import catch_warnings


class TestReplace(TestCase):

    def test_function(self):

        def test_z():
            return 'replacement z'

        compare(sample1.z(), 'original z')

        @replace('testfixtures.tests.sample1.z', test_z)
        def test_something():
            compare(sample1.z(), 'replacement z')

        compare(sample1.z(), 'original z')

        test_something()

        compare(sample1.z(), 'original z')

    def test_class(self):

        OriginalX = sample1.X

        class ReplacementX(sample1.X):
            pass

        self.assertFalse(OriginalX is ReplacementX)
        self.assertTrue(isinstance(sample1.X(), OriginalX))

        @replace('testfixtures.tests.sample1.X', ReplacementX)
        def test_something():
            self.assertFalse(OriginalX is ReplacementX)
            self.assertTrue(isinstance(sample1.X(), ReplacementX))

        self.assertFalse(OriginalX is ReplacementX)
        self.assertTrue(isinstance(sample1.X(), OriginalX))

        test_something()

        self.assertFalse(OriginalX is ReplacementX)
        self.assertTrue(isinstance(sample1.X(), OriginalX))

    def test_method(self):

        def test_y(self):
            return self

        compare(sample1.X().y(), 'original y')

        @replace('testfixtures.tests.sample1.X.y', test_y)
        def test_something():
            self.assertTrue(isinstance(sample1.X().y(), sample1.X))

        compare(sample1.X().y(), 'original y')

        test_something()

        compare(sample1.X().y(), 'original y')

    def test_class_method(self):

        def rMethod(cls):
            return (cls, 1)

        compare(sample1.X().aMethod(), sample1.X)

        @replace('testfixtures.tests.sample1.X.aMethod', rMethod)
        def test_something(r):
            compare(r, rMethod)
            compare(sample1.X().aMethod(), (sample1.X, 1))

        compare(sample1.X().aMethod(), sample1.X)

        test_something()

        compare(sample1.X().aMethod(), sample1.X)

    def test_multiple_replace(self):

        def test_y(self):
            return 'test y'

        def test_z():
            return 'test z'

        compare(sample1.z(), 'original z')
        compare(sample1.X().y(), 'original y')

        @replace('testfixtures.tests.sample1.z', test_z)
        @replace('testfixtures.tests.sample1.X.y', test_y)
        def test_something(passed_test_y, passed_test_z):
            compare(test_z, passed_test_z)
            compare(test_y, passed_test_y)
            compare(sample1.z(), 'test z')
            compare(sample1.X().y(), 'test y')

        compare(sample1.z(), 'original z')
        compare(sample1.X().y(), 'original y')

        test_something()

        compare(sample1.z(), 'original z')
        compare(sample1.X().y(), 'original y')

    def test_gotcha(self):
        # Just because you replace an object in one context,
        # doesn't meant that it's replaced in all contexts!

        def test_z():
            return 'test z'

        compare(sample1.z(), 'original z')
        compare(sample2.z(), 'original z')

        @replace('testfixtures.tests.sample1.z', test_z)
        def test_something():
            compare(sample1.z(), 'test z')
            compare(sample2.z(), 'original z')

        compare(sample1.z(), 'original z')
        compare(sample2.z(), 'original z')

        test_something()

        compare(sample1.z(), 'original z')
        compare(sample2.z(), 'original z')

    def test_raises(self):

        def test_z():
            return 'replacement z'

        compare(sample1.z(), 'original z')

        @replace('testfixtures.tests.sample1.z', test_z)
        def test_something():
            compare(sample1.z(), 'replacement z')
            raise Exception()

        compare(sample1.z(), 'original z')

        with ShouldRaise():
            test_something()

        compare(sample1.z(), 'original z')

    def test_want_replacement(self):

        o = object()

        @replace('testfixtures.tests.sample1.z', o)
        def test_something(r):
            self.assertTrue(r is o)
            self.assertTrue(sample1.z is o)

        test_something()

    def test_not_there(self):

        o = object()

        @replace('testfixtures.tests.sample1.bad', o)
        def test_something(r):
            pass  # pragma: no cover

        with ShouldRaise(AttributeError("Original 'bad' not found")):
            test_something()

    def test_not_there_ok(self):

        o = object()

        @replace('testfixtures.tests.sample1.bad', o, strict=False)
        def test_something(r):
            self.assertTrue(r is o)
            self.assertTrue(sample1.bad is o)

        test_something()

    def test_replace_dict(self):

        from testfixtures.tests.sample1 import some_dict

        original = some_dict['key']
        replacement = object()

        @replace('testfixtures.tests.sample1.some_dict.key', replacement)
        def test_something(obj):
            self.assertTrue(obj is replacement)
            self.assertTrue(some_dict['key'] is replacement)

        test_something()

        self.assertTrue(some_dict['key'] is original)

    def test_replace_delattr(self):

        from testfixtures.tests import sample1

        @replace('testfixtures.tests.sample1.some_dict', not_there)
        def test_something(obj):
            self.assertFalse(hasattr(sample1, 'some_dict'))

        test_something()

        self.assertEqual(sample1.some_dict,
                         {'complex_key': [1, 2, 3], 'key': 'value'})

    def test_replace_delattr_not_there(self):

        @replace('testfixtures.tests.sample1.foo', not_there)
        def test_something(obj):
            pass  # pragma: no cover

        with ShouldRaise(AttributeError("Original 'foo' not found")):
            test_something()

    def test_replace_delattr_not_there_not_strict(self):

        from testfixtures.tests import sample1

        @replace('testfixtures.tests.sample1.foo',
                 not_there, strict=False)
        def test_something(obj):
            self.assertFalse(hasattr(sample1, 'foo'))

        test_something()

    def test_replace_delattr_not_there_restored(self):

        from testfixtures.tests import sample1

        @replace('testfixtures.tests.sample1.foo',
                 not_there, strict=False)
        def test_something(obj):
            sample1.foo = 'bar'

        test_something()
        self.assertFalse(hasattr(sample1, 'foo'))

    def test_replace_delattr_cant_remove(self):
        if PY_310_PLUS:
            message = "cannot set 'today' attribute of " \
                      "immutable type 'datetime.datetime'"
        else:
            message = "can't set attributes of " \
                      "built-in/extension type 'datetime.datetime'"
        with Replacer() as r:
            with ShouldRaise(TypeError(message)):
                r.replace('datetime.datetime.today', not_there)

    def test_replace_delattr_cant_remove_not_strict(self):
        if PY_310_PLUS:
            message = "cannot set 'today' attribute of " \
                      "immutable type 'datetime.datetime'"
        else:
            message = "can't set attributes of " \
                      "built-in/extension type 'datetime.datetime'"
        with Replacer() as r:
            with ShouldRaise(TypeError(message)):
                r.replace('datetime.datetime.today', not_there, strict=False)

    def test_replace_dict_remove_key(self):

        from testfixtures.tests.sample1 import some_dict

        @replace('testfixtures.tests.sample1.some_dict.key', not_there)
        def test_something(obj):
            self.assertFalse('key' in some_dict)

        test_something()

        self.assertEqual(sorted(some_dict.keys()), ['complex_key', 'key'])

    def test_replace_dict_remove_key_not_there(self):

        from testfixtures.tests.sample1 import some_dict

        @replace('testfixtures.tests.sample1.some_dict.badkey', not_there)
        def test_something(obj):
            self.assertFalse('badkey' in some_dict)  # pragma: no cover

        with ShouldRaise(AttributeError("Original 'badkey' not found")):
            test_something()

        self.assertEqual(sorted(some_dict.keys()), ['complex_key', 'key'])

    def test_replace_dict_remove_key_not_there_not_strict(self):

        from testfixtures.tests.sample1 import some_dict

        @replace('testfixtures.tests.sample1.some_dict.badkey',
                 not_there, strict=False)
        def test_something(obj):
            self.assertFalse('badkey' in some_dict)

        test_something()

        self.assertEqual(sorted(some_dict.keys()), ['complex_key', 'key'])

    def test_replace_dict_ensure_key_not_there_restored(self):

        from testfixtures.tests.sample1 import some_dict

        @replace('testfixtures.tests.sample1.some_dict.badkey',
                 not_there, strict=False)
        def test_something(obj):
            some_dict['badkey'] = 'some test value'

        test_something()

        self.assertEqual(sorted(some_dict.keys()), ['complex_key', 'key'])

    def test_replace_dict_not_there(self):

        from testfixtures.tests.sample1 import some_dict

        replacement = object()

        @replace('testfixtures.tests.sample1.some_dict.key2',
                 replacement,
                 strict=False)
        def test_something(obj):
            self.assertTrue(obj is replacement)
            self.assertTrue(some_dict['key2'] is replacement)

        test_something()

        self.assertEqual(sorted(some_dict.keys()), ['complex_key', 'key'])

    def test_replace_dict_not_there_empty_string(self):

        from testfixtures.tests.sample1 import some_dict

        @replace('testfixtures.tests.sample1.some_dict.key2', '', strict=False)
        def test_something():
            self.assertEqual(some_dict['key2'], '')

        test_something()

        self.assertEqual(sorted(some_dict.keys()), ['complex_key', 'key'])

    def test_replace_complex(self):

        from testfixtures.tests.sample1 import some_dict

        original = some_dict['complex_key'][1]
        replacement = object()

        @replace('testfixtures.tests.sample1.some_dict.complex_key.1',
                 replacement)
        def test_something(obj):
            self.assertTrue(obj is replacement)
            self.assertEqual(some_dict['complex_key'], [1, obj, 3])

        test_something()

        self.assertEqual(some_dict['complex_key'], [1, 2, 3])

        self.assertTrue(original is some_dict['complex_key'][1])

    def test_replacer_del(self):
        r = Replacer()
        r.replace('testfixtures.tests.sample1.left_behind',
                  object(), strict=False)
        with catch_warnings(record=True) as w:
            del r
            self.assertTrue(len(w), 1)
            compare(str(w[0].message),
                    "Replacer deleted without being restored, originals left:"
                    " {'testfixtures.tests.sample1.left_behind': <Resolved: <not_there>>}")

    def test_multiple_replaces(self):
        orig = os.path.sep
        with Replacer() as r:
            r.replace('os.path.sep', '$')
            compare(os.path.sep, '$')
            r.replace('os.path.sep', '=')
            compare(os.path.sep, '=')
        compare(orig, os.path.sep)

    def test_sub_module_import(self):
        with TempDirectory() as dir:
            dir.write('module/__init__.py', b'')
            dir.write('module/submodule.py', b'def foo(): return "foo"')

            with Replacer() as r:
                r.replace('sys.path', [dir.path])

                def bar():
                    return "bar"
                # now test

                r.replace('module.submodule.foo', bar)

                from module.submodule import foo
                compare(foo(), "bar")

    def test_staticmethod(self):
        compare(sample1.X.bMethod(), 2)
        with Replacer() as r:
            r.replace('testfixtures.tests.sample1.X.bMethod', lambda: 1)
            compare(sample1.X.bMethod(), 1)
        compare(sample1.X.bMethod(), 2)

    def test_use_as_cleanup(self):
        def test_z():
            return 'replacement z'

        compare(sample1.z(), 'original z')
        replace = Replacer()
        compare(sample1.z(), 'original z')
        replace('testfixtures.tests.sample1.z', test_z)
        cleanup = replace.restore
        try:
            compare(sample1.z(), 'replacement z')
        finally:
            cleanup()
        compare(sample1.z(), 'original z')

    def test_replace_context_manager(self):
        def test_z():
            return 'replacement z'

        compare(sample1.z(), 'original z')

        with Replace('testfixtures.tests.sample1.z', test_z) as z:
            compare(z(), 'replacement z')
            compare(sample1.z(), 'replacement z')

        compare(sample1.z(), 'original z')

    def test_multiple_context_managers(self):

        def test_y(self):
            return 'test y'

        def test_z():
            return 'test z'

        compare(sample1.z(), 'original z')
        compare(sample1.X().y(), 'original y')

        with Replacer() as replace:
            z = replace('testfixtures.tests.sample1.z', test_z)
            y = replace('testfixtures.tests.sample1.X.y', test_y)
            compare(z(), 'test z')
            compare(y, sample1.X.y)
            compare(sample1.X().y(), 'test y')
            compare(sample1.z(), 'test z')
            compare(sample1.X().y(), 'test y')

        compare(sample1.z(), 'original z')
        compare(sample1.X().y(), 'original y')

    def test_context_manager_not_strict(self):
        def test_z():
            return 'replacement z'

        with Replace('testfixtures.tests.sample1.foo', test_z, strict=False):
            compare(sample1.foo(), 'replacement z')

    def test_context_manager_full_spec(self):
        my_dict = {}

        with Replace(my_dict, name='foo', accessor=getitem, replacement=42, strict=False):
            compare(my_dict, expected={'foo': 42})

        compare(my_dict, expected={})

    def test_decorator_full_spec(self):
        my_dict = {}

        @replace(my_dict, name='foo', accessor=getitem, replacement=42, strict=False)
        def test_something():
            compare(my_dict, expected={'foo': 42})

        test_something()

        compare(my_dict, expected={})

    def test_replace_method_full_spec(self):
        my_dict = {}

        with Replacer() as r:
            r.replace(my_dict, name='foo', accessor=getitem, replacement=42, strict=False)
            compare(my_dict, expected={'foo': 42})

        compare(my_dict, expected={})

    def test_context_manager_specified_method(self):
        class SampleClass:

            def method(self, x):
                return x*2

        sample_obj = SampleClass()

        with Replace(SampleClass.method, lambda self, x: x*3,
                     container=SampleClass, name='method', accessor=getattr):
            compare(sample_obj.method(1), expected=3)

        compare(sample_obj.method(1), expected=2)

    def test_decorator_specified_method(self):
        class SampleClass:

            def method(self, x):
                return x*2

        sample_obj = SampleClass()

        @replace(SampleClass.method, lambda self, x: x*3,
                 container=SampleClass, name='method', accessor=getattr)
        def test_something():
            compare(sample_obj.method(1), expected=3)

        test_something()

        compare(sample_obj.method(1), expected=2)

    def test_fully_specified_method(self):
        class SampleClass:

            def method(self, x):
                return x*2

        sample_obj = SampleClass()

        with Replacer() as r:
            r.replace(SampleClass.method, lambda self, x: x*3,
                      container=SampleClass, name='method', accessor=getattr)
            compare(sample_obj.method(1), expected=3)

        compare(sample_obj.method(1), expected=2)

    def test_fully_specified_method_incorrect_name(self):
        class SampleClass:

            def a(self):
                return 1

            def b(self):
                return 2

        sample_obj = SampleClass()
        a_repr = repr(SampleClass.a)
        b_repr = repr(SampleClass.b)
        replacer = Replacer()
        with ShouldRaise(AssertionError(f"'b' resolved to {b_repr}, expected {a_repr}")):
            replacer(SampleClass.a, lambda self: 3,
                     container=SampleClass, name='b', accessor=getattr)

        compare(sample_obj.a(), expected=1)
        compare(sample_obj.b(), expected=2)

    def test_traverse_from_container(self):
        x = sample1.X()
        with Replace('.X.aMethod', lambda cls: 'FOO', container=sample1):
            compare(x.aMethod(), expected='FOO')
        assert x.aMethod() is sample1.X

    def test_only_relative_traverse_from_container(self):
        x = sample1.X()
        replacer = Replacer()
        with ShouldRaise(AssertionError('Absolute traversal not allowed when container supplied')):
            replacer('foo', object(), container=sample1)

    def test_no_name_and_target_string(self):
        x = sample1.X()
        replacer = Replacer()
        with ShouldRaise(TypeError('name cannot be specified when target is a string')):
            replacer('.X', lambda cls: 'FOO', name='aMethod', container=sample1)
        assert x.aMethod() is sample1.X

    def test_no_accessor_allowed_when_name_not_specified(self):
        my_dict = {}
        replacer = Replacer()
        with ShouldRaise(TypeError('accessor is not used unless name is specified')):
            replacer(container=my_dict, target='.my.key', accessor=getitem, replacement='bar')
        compare(my_dict, expected={})

    def test_dict_and_name(self):
        my_dict = {}

        with Replace(my_dict, name='foo', replacement=42, strict=False):
            compare(my_dict, expected={'foo': 42})

        compare(my_dict, expected={})

    def test_name_and_dict(self):
        environ = {}

        with Replace('.MY_ENV_VAR', 'True', container=environ, strict=False):
            compare(environ, expected={'MY_ENV_VAR': 'True'})

        compare(environ, expected={})

    def test_obj_and_name(self):
        my_obj = Mock()
        foo = my_obj.foo

        with Replace(my_obj, name='foo', replacement=42, strict=False):
            compare(my_obj.foo, expected=42)

        assert my_obj.foo is foo

    def test_non_string_target_and_no_name(self):
        my_dict = {}

        replacer = Replacer()
        with ShouldRaise(TypeError('name must be specified when target is not a string')):
            replacer(my_dict, replacement=42, strict=False)

        compare(my_dict, expected={})

    def test_method_on_instance(self):

        class SampleClass:

            def method(self, x):
                return x*2

        sample = SampleClass()

        with Replacer() as replace:
            replace(sample.method, lambda x: x * 3, container=sample, strict=False)
            compare(sample.method(1), expected=3)

        compare(sample.method(1), expected=2)

    def test_class_attribute(self):

        mock = Mock()
        mock.FOO = set()

        class SampleClass:

            FOO = mock.FOO

        sample = SampleClass()

        with Replace(SampleClass.FOO, {'X'}, container=SampleClass, name='FOO'):
            compare(sample.FOO, expected={'X'})
            compare(mock.FOO, expected=set())

        compare(sample.FOO, expected=set())

    def test_function_and_module(self):
        with Replace(z, lambda: 'all new z', container=sample1):
            from .sample1 import z as sample1_z
            from .sample3 import z as sample3_z
            compare(sample1_z(), expected='all new z')
            compare(sample3_z(), expected='original z')

    def test_constant(self):
        with Replace(SOME_CONSTANT, 43, container=sample3, name='SOME_CONSTANT'):
            from .sample3 import SOME_CONSTANT as sample3_some_constant
            compare(sample3_some_constant, expected=43)


class TestEnviron:

    def test_key_present(self):
        os.environ['TESTFIXTURES_SAMPLE_KEY_PRESENT'] = 'ORIGINAL'
        with Replacer() as replace:
            replace.in_environ('TESTFIXTURES_SAMPLE_KEY_PRESENT', 'NEW')
            compare(os.environ['TESTFIXTURES_SAMPLE_KEY_PRESENT'], expected='NEW')
        compare(os.environ['TESTFIXTURES_SAMPLE_KEY_PRESENT'], expected='ORIGINAL')

    def test_key_not_present(self):
        assert 'TESTFIXTURES_SAMPLE_KEY_MISSING' not in os.environ
        with Replacer() as replace:
            replace.in_environ('TESTFIXTURES_SAMPLE_KEY_MISSING', 'NEW')
            compare(os.environ['TESTFIXTURES_SAMPLE_KEY_MISSING'], expected='NEW')
        assert 'TESTFIXTURES_SAMPLE_KEY_MISSING' not in os.environ

    def test_non_string_replacement(self):
        with Replacer() as replace:
            replace.in_environ('PORT', 1)
            compare(os.environ['PORT'], expected='1')

    def test_ensure_not_present(self):
        os.environ['TESTFIXTURES_SAMPLE_KEY_PRESENT'] = 'ORIGINAL'
        with Replacer() as replace:
            replace.in_environ('TESTFIXTURES_SAMPLE_KEY_PRESENT', not_there)
            assert 'TESTFIXTURES_SAMPLE_KEY_PRESENT' not in os.environ


class TestOnClass:

    def test_method_on_class(self):

        class SampleClass:

            def method(self, x):
                return x*2

        original = SampleClass.__dict__['method']
        sample = SampleClass()

        with Replacer() as replace:
            replace.on_class(SampleClass.method, lambda self, x: x*3)
            compare(sample.method(1), expected=3)

        compare(sample.method(1), expected=2)
        assert SampleClass.__dict__['method'] is original

    def test_method_on_instance(self):

        class SampleClass:

            def method(self, x):
                return x*2

        original = SampleClass.__dict__['method']
        sample = SampleClass()

        with Replacer() as replace:
            with ShouldRaise(AttributeError):
                replace.on_class(sample.method, lambda self, x: x*3)

            # ...so use explicit and non-strict:
            replace(sample.method, lambda x: x * 3, container=sample, strict=False)

            compare(sample.method(1), expected=3)

        compare(sample.method(1), expected=2)
        assert SampleClass.__dict__['method'] is original

    def test_badly_decorated_method(self):

        def bad(f):
            def inner(self, x):
                return f(self, x)
            return inner

        class SampleClass:

            @bad
            def method(self, x):
                return x*2

        original = SampleClass.__dict__['method']
        sample = SampleClass()

        with Replacer() as replace:

            # without the name, we get a useful error:
            with ShouldRaise(AttributeError(
                    f"could not find container of {SampleClass.method} using name 'inner'"
            )):
                replace.on_class(SampleClass.method, lambda self_, x: x*3)

            assert SampleClass.__dict__['method'] is original
            replace.on_class(SampleClass.method, lambda self_, x: x*3, name='method')
            compare(sample.method(1), expected=3)

        compare(sample.method(1), expected=2)
        assert SampleClass.__dict__['method'] is original

    def test_classmethod(self):

        class SampleClass:

            @classmethod
            def method(cls, x):
                return x*2

        original = SampleClass.__dict__['method']

        with Replacer() as replace:
            replace.on_class(SampleClass.method, classmethod(lambda cls, x: x*3))
            compare(SampleClass.method(1), expected=3)

        compare(SampleClass.method(1), expected=2)
        assert SampleClass.__dict__['method'] is original

    def test_staticmethod(self):

        class SampleClass:

            @staticmethod
            def method(x):
                return x*2

        original = SampleClass.__dict__['method']

        with Replacer() as replace:
            replace.on_class(SampleClass.method, lambda x: x*3)
            compare(SampleClass.method(1), expected=3)

        compare(SampleClass.method(1), expected=2)
        assert SampleClass.__dict__['method'] is original

    def test_not_callable(self):

        class SampleClass:

            FOO = 1

        sample = SampleClass()

        replace = Replacer()
        with ShouldRaise(TypeError('attribute must be callable')):
            replace.on_class(SampleClass.FOO, 2)
        compare(sample.FOO, expected=1)

    def test_method_on_class_in_module(self):
        sample = X()
        original = X.__dict__['y']

        with Replacer() as replace:
            replace.on_class(X.y, lambda self_: 'replacement y')
            compare(sample.y(), expected='replacement y')

        compare(sample.y(), expected='original y')
        assert X.__dict__['y'] is original

    def test_method_on_instance_in_module(self):

        sample = X()
        original = X.__dict__['y']

        with Replacer() as replace:
            replace(sample.y, lambda: 'replacement y', container=sample, strict=False)
            compare(sample.y(), expected='replacement y')

        compare(sample.y(), expected='original y')
        assert X.__dict__['y'] is original

    def test_classmethod_on_class_in_module(self):

        original = X.__dict__['aMethod']

        with Replacer() as replace:
            replace.on_class(X.aMethod, classmethod(lambda cls: (cls, cls)))
            compare(X.aMethod(), expected=(X, X))

        compare(X.aMethod(), expected=X)
        assert X.__dict__['aMethod'] is original

    def test_classmethod_on_instance_in_module(self):

        sample = X()
        original = X.__dict__['aMethod']

        with Replacer() as replace:
            replace.on_class(sample.aMethod, classmethod(lambda cls: (cls, cls)))
            compare(sample.aMethod(), expected=(X, X))

        compare(sample.aMethod(), expected=X)
        assert X.__dict__['aMethod'] is original

    def test_staticmethod_on_class_in_module(self):

        original = X.__dict__['bMethod']

        with Replacer() as replace:
            replace.on_class(X.bMethod, lambda: 3)
            compare(X.bMethod(), expected=3)

        compare(X.bMethod(), expected=2)
        assert X.__dict__['bMethod'] is original

    def test_staticmethod_on_instance_in_module(self):

        original = X.__dict__['bMethod']
        sample = X()

        with Replacer() as replace:
            replace(sample.bMethod, lambda: 3, container=sample, strict=False)
            compare(sample.bMethod(), expected=3)

        compare(X.bMethod(), expected=2)
        assert X.__dict__['bMethod'] is original


class TestInModule:

    def test_function_guess_module(self):
        with Replacer() as replace:
            replace.in_module(z, lambda: 'all new z')
            from .sample1 import z as sample1_z
            from .sample3 import z as sample3_z
            compare(sample1_z(), expected='all new z')
            compare(sample3_z(), expected='original z')
        from .sample1 import z as sample1_z
        from .sample3 import z as sample3_z
        compare(sample1_z(), expected='original z')
        compare(sample3_z(), expected='original z')

    def test_function_explict_module(self):
        with Replacer() as replace:
            replace.in_module(z, lambda: 'all new z', module=sample3)
            from .sample1 import z as sample1_z
            from .sample3 import z as sample3_z
            compare(sample1_z(), expected='original z')
            compare(sample3_z(), expected='all new z')
        from .sample1 import z as sample1_z
        from .sample3 import z as sample3_z
        compare(sample1_z(), expected='original z')
        compare(sample3_z(), expected='original z')

    def test_constant(self):
        replace = Replacer()
        with ShouldRaise(AttributeError("'int' object has no attribute '__module__'")):
            replace.in_module(SOME_CONSTANT, 43)
        from .sample3 import SOME_CONSTANT as sample3_some_constant
        compare(sample3_some_constant, expected=42)


class TestConvenience:

    def test_environ(self):
        os.environ['TESTFIXTURES_SAMPLE_KEY_PRESENT'] = 'ORIGINAL'
        with replace_in_environ('TESTFIXTURES_SAMPLE_KEY_PRESENT', 'NEW'):
            compare(os.environ['TESTFIXTURES_SAMPLE_KEY_PRESENT'], expected='NEW')
        compare(os.environ['TESTFIXTURES_SAMPLE_KEY_PRESENT'], expected='ORIGINAL')

    def test_on_class(self):

        class SampleClass:

            def method(self, x):
                return x*2

        sample = SampleClass()

        with replace_on_class(SampleClass.method, lambda self, x: x*3, name='method'):
            compare(sample.method(1), expected=3)

        compare(sample.method(1), expected=2)

    def test_in_module(self):
        with replace_in_module(z, lambda: 'all new z', module=sample3):
            from .sample1 import z as sample1_z
            from .sample3 import z as sample3_z
            compare(sample1_z(), expected='original z')
            compare(sample3_z(), expected='all new z')
        from .sample1 import z as sample1_z
        from .sample3 import z as sample3_z
        compare(sample1_z(), expected='original z')
        compare(sample3_z(), expected='original z')
