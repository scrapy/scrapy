import sys
from unittest import TestCase

from testfixtures import Comparison as C, TempDirectory, diff, Comparison
from testfixtures.tests.sample1 import SampleClassA, a_function


class AClass:

    def __init__(self, x, y=None):
        self.x = x
        if y:
            self.y = y

    def __repr__(self):
        return '<'+self.__class__.__name__+'>'


class BClass(AClass):
    pass


class WeirdException(Exception):
    def __init__(self, x, y):
        self.x = x
        self.y = y


class X(object):
    __slots__ = ['x']


class FussyDefineComparison(object):

    def __init__(self, attr):
        self.attr = attr

    def __eq__(self, other):
        if not isinstance(other, self.__class__):  # pragma: no cover
            raise TypeError()
        return False  # pragma: no cover

    def __ne__(self, other):
        return not self == other  # pragma: no cover


def compare_repr(obj, expected):
    actual = diff(expected, repr(obj))
    if actual:  # pragma: no cover
        raise AssertionError(actual)


class TestC(TestCase):

    def test_example(self):
        # In this pattern, we want to check a sequence is
        # of the correct type and order.
        r = a_function()
        self.assertEqual(r, (
            C('testfixtures.tests.sample1.SampleClassA'),
            C('testfixtures.tests.sample1.SampleClassB'),
            C('testfixtures.tests.sample1.SampleClassA'),
            ))
        # We also want to check specific parts of some
        # of the returned objects' attributes
        self.assertEqual(r[0].args[0], 1)
        self.assertEqual(r[1].args[0], 2)
        self.assertEqual(r[2].args[0], 3)

    def test_example_with_object(self):
        # Here we see compare an object with a Comparison
        # based on an object of the same type and with the
        # same attributes:
        self.assertEqual(
            C(AClass(1, 2)),
            AClass(1, 2),
            )
        # ...even though the original class doesn't support
        # meaningful comparison:
        self.assertNotEqual(
            AClass(1, 2),
            AClass(1, 2),
            )

    def test_example_with_vars(self):
        # Here we use a Comparison to make sure both the
        # type and attributes of an object are correct.
        self.assertEqual(
            C('testfixtures.tests.test_comparison.AClass',
              x=1, y=2),
            AClass(1, 2),
            )

    def test_example_with_odd_vars(self):
        # If the variable names class with parameters to the
        # Comparison constructor, they can be specified in a
        # dict:
        self.assertEqual(
            C('testfixtures.tests.test_comparison.AClass',
              {'x': 1, 'y': 2}),
            AClass(1, 2),
            )

    def test_example_partial(self):
        self.assertEqual(
            C('testfixtures.tests.test_comparison.AClass',
              x=1,
              partial=True),
            AClass(1, 2),
            )

    def test_example_dont_use_c_wrappers_on_both_sides(self):
        # NB: don't use C wrappers on both sides!
        e = ValueError('some message')
        x, y = C(e), C(e)
        assert x != y
        compare_repr(x, "<C:builtins.ValueError(failed)>wrong type</>")
        compare_repr(y, "<C:builtins.ValueError>args: ('some message',)</>")

    def test_repr_module(self):
        compare_repr(C('datetime'), '<C:datetime>')

    def test_repr_class(self):
        compare_repr(C('testfixtures.tests.sample1.SampleClassA'),
                     '<C:testfixtures.tests.sample1.SampleClassA>')

    def test_repr_function(self):
        compare_repr(C('testfixtures.tests.sample1.z'),
                     '<C:testfixtures.tests.sample1.z>')

    def test_repr_instance(self):
        compare_repr(C(SampleClassA('something')),
                     "<C:testfixtures.tests.sample1.SampleClassA>"
                     "args: ('something',)"
                     "</>"
                     )

    def test_repr_exception(self):
        compare_repr(C(ValueError('something')), "<C:builtins.ValueError>args: ('something',)</>")

    def test_repr_exception_not_args(self):
        compare_repr(
            C(WeirdException(1, 2)),
            "\n<C:testfixtures.tests.test_comparison.WeirdException>\n"
            "args: (1, 2)\n"
            "x: 1\n"
            "y: 2\n"
            "</C:testfixtures.tests.test_comparison.WeirdException>"
        )

    def test_repr_class_and_vars(self):
        compare_repr(
            C(SampleClassA, {'args': (1,)}),
            "<C:testfixtures.tests.sample1.SampleClassA>args: (1,)</>"
        )

    def test_repr_nested(self):
        compare_repr(
            C(SampleClassA, y=C(AClass), z=C(BClass(1, 2))),
            "\n"
            "<C:testfixtures.tests.sample1.SampleClassA>\n"
            "y: <C:testfixtures.tests.test_comparison.AClass>\n"
            "z: \n"
            "  <C:testfixtures.tests.test_comparison.BClass>\n"
            "  x: 1\n"
            "  y: 2\n"
            "  </C:testfixtures.tests.test_comparison.BClass>\n"
            "</C:testfixtures.tests.sample1.SampleClassA>"
            )

    def test_repr_failed_wrong_class(self):
        c = C('testfixtures.tests.test_comparison.AClass', x=1, y=2)
        assert c != BClass(1, 2)
        compare_repr(c,
                     "<C:testfixtures.tests.test_comparison.AClass(failed)>"
                     "wrong type</>"
                     )

    def test_repr_failed_all_reasons_in_one(self):
        c = C('testfixtures.tests.test_comparison.AClass',
              y=5, z='missing')
        assert c != AClass(1, 2)
        compare_repr(c,
                     "\n"
                     "<C:testfixtures.tests.test_comparison.AClass(failed)>\n"
                     "attributes in Comparison but not actual:\n"
                     "'z': 'missing'\n\n"
                     "attributes in actual but not Comparison:\n"
                     "'x': 1\n\n"
                     "attributes differ:\n"
                     "'y': 5 (Comparison) != 2 (actual)\n"
                     "</C:testfixtures.tests.test_comparison.AClass>",
                     )

    def test_repr_failed_not_in_other(self):
        c = C('testfixtures.tests.test_comparison.AClass',
              x=1, y=2, z=(3, ))
        assert c != AClass(1, 2)
        compare_repr(c ,
                     "\n"
                     "<C:testfixtures.tests.test_comparison.AClass(failed)>\n"
                     "attributes same:\n"
                     "['x', 'y']\n\n"
                     "attributes in Comparison but not actual:\n"
                     "'z': (3,)\n"
                     "</C:testfixtures.tests.test_comparison.AClass>",
                     )

    def test_repr_failed_not_in_self(self):
        c = C('testfixtures.tests.test_comparison.AClass', y=2)
        assert c != AClass(x=(1, ), y=2)
        compare_repr(c,
                     "\n"
                     "<C:testfixtures.tests.test_comparison.AClass(failed)>\n"
                     "attributes same:\n"
                     "['y']\n\n"
                     "attributes in actual but not Comparison:\n"
                     "'x': (1,)\n"
                     "</C:testfixtures.tests.test_comparison.AClass>",
                     )

    def test_repr_failed_not_in_self_partial(self):
        c = C('testfixtures.tests.test_comparison.AClass', x=1, y=2, z=(3, ), partial=True)
        assert c != AClass(x=1, y=2)
        compare_repr(c,
                     "\n"
                     "<C:testfixtures.tests.test_comparison.AClass(failed)>\n"
                     "attributes same:\n"
                     "['x', 'y']\n\n"
                     "attributes in Comparison but not actual:\n"
                     "'z': (3,)\n"
                     "</C:testfixtures.tests.test_comparison.AClass>",
                     )

    def test_repr_failed_one_attribute_not_equal(self):
        c = C('testfixtures.tests.test_comparison.AClass', x=1, y=(2, ))
        assert c != AClass(1, (3, ))
        compare_repr(c,
                     "\n"
                     "<C:testfixtures.tests.test_comparison.AClass(failed)>\n"
                     "attributes same:\n"
                     "['x']\n\n"
                     "attributes differ:\n"
                     "'y': (2,) (Comparison) != (3,) (actual)\n"
                     "</C:testfixtures.tests.test_comparison.AClass>",
                     )

    def test_repr_failed_nested(self):
        left_side = [C(AClass, x=1, y=2),
                     C(BClass, x=C(AClass, x=1, y=2), y=C(AClass))]
        right_side = [AClass(1, 3), AClass(1, 3)]

        # do the comparison
        left_side == right_side

        compare_repr(
            left_side,
            "[\n"
            "<C:testfixtures.tests.test_comparison.AClass(failed)>\n"
            "attributes same:\n"
            "['x']\n\n"
            "attributes differ:\n"
            "'y': 2 (Comparison) != 3 (actual)\n"
            "</C:testfixtures.tests.test_comparison.AClass>, \n"
            "<C:testfixtures.tests.test_comparison.BClass>\n"
            "x: \n"
            "  <C:testfixtures.tests.test_comparison.AClass>\n"
            "  x: 1\n"
            "  y: 2\n"
            "  </C:testfixtures.tests.test_comparison.AClass>\n"
            "y: <C:testfixtures.tests.test_comparison.AClass>\n"
            "</C:testfixtures.tests.test_comparison.BClass>]"
        )

        compare_repr(right_side, "[<AClass>, <AClass>]")

    def test_repr_failed_nested_failed(self):
        left_side = [C(AClass, x=1, y=2),
                     C(BClass,
                       x=C(AClass, x=1, partial=True),
                       y=C(AClass, z=2))]
        right_side = [AClass(1, 2),
                      BClass(AClass(1, 2), AClass(1, 2))]

        # do the comparison
        left_side == right_side

        compare_repr(
            left_side,
            "[\n"
            "<C:testfixtures.tests.test_comparison.AClass>\n"
            "x: 1\n"
            "y: 2\n"
            "</C:testfixtures.tests.test_comparison.AClass>, \n"
            "<C:testfixtures.tests.test_comparison.BClass(failed)>\n"
            "attributes same:\n"
            "['x']\n\n"
            "attributes differ:\n"
            "'y': \n"
            "<C:testfixtures.tests.test_comparison.AClass(failed)>\n"
            "attributes in Comparison but not actual:\n"
            "'z': 2\n\n"
            "attributes in actual but not Comparison:\n"
            "'x': 1\n"
            "'y': 2\n"
            "</C:testfixtures.tests.test_comparison.AClass> (Comparison) != <AClass> (actual)\n"
            "</C:testfixtures.tests.test_comparison.BClass>]",
        )

        compare_repr(right_side, '[<AClass>, <BClass>]')

    def test_repr_failed_passed_failed(self):
        c = C('testfixtures.tests.test_comparison.AClass', x=1, y=2)
        assert c != AClass(1, 3)
        compare_repr(c,
                     "\n"
                     "<C:testfixtures.tests.test_comparison.AClass(failed)>\n"
                     "attributes same:\n"
                     "['x']\n\n"
                     "attributes differ:\n"
                     "'y': 2 (Comparison) != 3 (actual)\n"
                     "</C:testfixtures.tests.test_comparison.AClass>",
                     )

        assert c == AClass(1, 2)

        assert c != AClass(3, 2)
        compare_repr(c,
                     "\n"
                     "<C:testfixtures.tests.test_comparison.AClass(failed)>\n"
                     "attributes same:\n"
                     "['y']\n\n"
                     "attributes differ:\n"
                     "'x': 1 (Comparison) != 3 (actual)\n"
                     "</C:testfixtures.tests.test_comparison.AClass>",
                     )

    def test_first(self):
        self.assertEqual(
            C('testfixtures.tests.sample1.SampleClassA'),
            SampleClassA()
            )

    def test_second(self):
        self.assertEqual(
            SampleClassA(),
            C('testfixtures.tests.sample1.SampleClassA'),
            )

    def test_not_same_first(self):
        self.assertNotEqual(
            C('datetime'),
            SampleClassA()
            )

    def test_not_same_second(self):
        self.assertNotEqual(
            SampleClassA(),
            C('datetime')
            )

    def test_object_supplied(self):
        self.assertEqual(
            SampleClassA(1),
            C(SampleClassA(1))
            )

    def test_class_and_vars(self):
        self.assertEqual(
            SampleClassA(1),
            C(SampleClassA, {'args': (1,)})
            )

    def test_class_and_kw(self):
        self.assertEqual(
            SampleClassA(1),
            C(SampleClassA, args=(1,))
            )

    def test_class_and_vars_and_kw(self):
        self.assertEqual(
            AClass(1, 2),
            C(AClass, {'x': 1}, y=2)
            )

    def test_object_and_vars(self):
        # vars passed are used instead of the object's
        self.assertEqual(
            SampleClassA(1),
            C(SampleClassA(), {'args': (1,)})
            )

    def test_object_and_kw(self):
        # kws passed are used instead of the object's
        self.assertEqual(
            SampleClassA(1),
            C(SampleClassA(), args=(1,))
            )

    def test_object_partial(self):
        # only attributes on comparison object
        # are used
        self.assertEqual(
            C(AClass(1), partial=True),
            AClass(1, 2),
            )

    def run_property_equal_test(self, partial):
        class SomeClass(object):
            @property
            def prop(self):
                return 1

        self.assertEqual(
            C(SomeClass, prop=1, partial=partial),
            SomeClass()
        )

    def test_property_equal(self):
        self.run_property_equal_test(partial=False)

    def test_property_equal_partial(self):
        self.run_property_equal_test(partial=True)

    def run_property_not_equal_test(self, partial):
        class SomeClass(object):
            @property
            def prop(self):
                return 1

        c = C(SomeClass, prop=2, partial=partial)
        self.assertNotEqual(c, SomeClass())
        compare_repr(
            c,
            "\n"
            "<C:testfixtures.tests.test_comparison.SomeClass(failed)>\n"
            "attributes differ:\n"
            "'prop': 2 (Comparison) != 1 (actual)\n"
            "</C:testfixtures.tests.test_comparison.SomeClass>")

    def test_property_not_equal(self):
        self.run_property_not_equal_test(partial=False)

    def test_property_not_equal_partial(self):
        self.run_property_not_equal_test(partial=True)

    def run_method_equal_test(self, partial):
        class SomeClass(object):
            def method(self):
                pass  # pragma: no cover

        instance = SomeClass()
        self.assertEqual(
            C(SomeClass, method=instance.method, partial=partial),
            instance
        )

    def test_method_equal(self):
        self.run_method_equal_test(partial=False)

    def test_method_equal_partial(self):
        self.run_method_equal_test(partial=True)

    def run_method_not_equal_test(self, partial):
        class SomeClass(object): pass
        instance = SomeClass()
        instance.method = min

        c = C(SomeClass, method=max, partial=partial)
        self.assertNotEqual(c, instance)
        compare_repr(
            c,
            "\n"
            "<C:testfixtures.tests.test_comparison.SomeClass(failed)>\n"
            "attributes differ:\n"
            "'method': <built-in function max> (Comparison)"
            " != <built-in function min> (actual)\n"
            "</C:testfixtures.tests.test_comparison.SomeClass>"
        )

    def test_method_not_equal(self):
        self.run_method_not_equal_test(partial=False)

    def test_method_not_equal_partial(self):
        self.run_method_not_equal_test(partial=True)

    def test_exception(self):
        self.assertEqual(
            ValueError('foo'),
            C(ValueError('foo'))
            )

    def test_exception_class_and_args(self):
        self.assertEqual(
            ValueError('foo'),
            C(ValueError, args=('foo', ))
            )

    def test_exception_instance_and_args(self):
        self.assertEqual(
            ValueError('foo'),
            C(ValueError('bar'), args=('foo', ))
            )

    def test_exception_not_same(self):
        self.assertNotEqual(
            ValueError('foo'),
            C(ValueError('bar'))
            )

    def test_exception_no_args_different(self):
        self.assertNotEqual(
            WeirdException(1, 2),
            C(WeirdException(1, 3))
            )

    def test_exception_no_args_same(self):
        self.assertEqual(
            C(WeirdException(1, 2)),
            WeirdException(1, 2)
            )

    def test_repr_file_different(self):
        with TempDirectory() as d:
            path = d.write('file', b'stuff')
            f = open(path)
            f.close()
        c = C('io.TextIOWrapper', name=path, mode='r', closed=False,
              partial=True)
        assert f != c
        compare_repr(c,
                     "\n"
                     "<C:_io.TextIOWrapper(failed)>\n"
                     "attributes same:\n"
                     "['mode', 'name']\n\n"
                     "attributes differ:\n"
                     "'closed': False (Comparison) != True (actual)\n"
                     "</C:_io.TextIOWrapper>",
                     )

    def test_file_same(self):
        with TempDirectory() as d:
            path = d.write('file', b'stuff')
            f = open(path)
            f.close()
        self.assertEqual(
            f,
            C('io.TextIOWrapper', name=path, mode='r', closed=True,
              partial=True)
            )

    def test_no___dict___strict(self):
        c = C(X, x=1)
        assert c != X()
        compare_repr(c, "\n"
                        "<C:testfixtures.tests.test_comparison.X(failed)>\n"
                        "attributes in Comparison but not actual:\n"
                        "'x': 1\n"
                        "</C:testfixtures.tests.test_comparison.X>")

    def test_no___dict___partial_same(self):
        x = X()
        x.x = 1
        self.assertEqual(C(X, x=1, partial=True), x)

    def test_no___dict___partial_missing_attr(self):
        c = C(X, x=1, partial=True)
        assert c != X()
        compare_repr(c,
                     "\n"
                     "<C:testfixtures.tests.test_comparison.X(failed)>\n"
                     "attributes in Comparison but not actual:\n"
                     "'x': 1\n"
                     "</C:testfixtures.tests.test_comparison.X>",
                     )

    def test_no___dict___partial_different(self):
        x = X()
        x.x = 2
        c = C(X, x=1, y=2, partial=True)
        assert c != x
        compare_repr(c,
                     "\n"
                     "<C:testfixtures.tests.test_comparison.X(failed)>\n"
                     "attributes in Comparison but not actual:\n"
                     "'y': 2\n\n"
                     "attributes differ:\n"
                     "'x': 1 (Comparison) != 2 (actual)\n"
                     "</C:testfixtures.tests.test_comparison.X>",
                     )

    def test_compared_object_defines_eq(self):
        # If an object defines eq, such as Django instances,
        # things become tricky

        class Annoying:
            def __init__(self):
                self.eq_called = 0

            def __eq__(self, other):
                self.eq_called += 1
                if isinstance(other, Annoying):
                    return True
                return False

        self.assertEqual(Annoying(), Annoying())

        # Suddenly, order matters.

        # This order is wrong, as it uses the class's __eq__:
        self.assertFalse(Annoying() == C(Annoying))
        # but on __eq__ is used as a fallback:
        self.assertTrue(Annoying() != C(Annoying))

        # This is the right ordering:
        self.assertTrue(C(Annoying) == Annoying())
        self.assertFalse(C(Annoying) != Annoying())

        # When the ordering is right, you still get the useful
        # comparison representation afterwards
        c = C(Annoying, eq_called=1)
        c == Annoying()
        compare_repr(
            c,
            '\n<C:testfixtures.tests.test_comparison.Annoying(failed)>\n'
            'attributes differ:\n'
            "'eq_called': 1 (Comparison) != 0 (actual)\n"
            '</C:testfixtures.tests.test_comparison.Annoying>'
        )

    def test_importerror(self):
        assert C(ImportError('x')) == ImportError('x')

    def test_class_defines_comparison_strictly(self):
        self.assertEqual(
            C('testfixtures.tests.test_comparison.FussyDefineComparison',
              attr=1),
            FussyDefineComparison(1)
            )

    def test_cant_resolve(self):
        try:
            C('testfixtures.bonkers')
        except Exception as e:
            self.assertTrue(isinstance(e, AttributeError))
            self.assertEqual(
                e.args,
                ("'testfixtures.bonkers' could not be resolved", )
                )
        else:
            self.fail('No exception raised!')

    def test_no_name(self):
        class NoName(object):
            pass
        NoName.__name__ = ''
        NoName.__module__ = ''
        c = C(NoName)
        self.assertEqual(repr(c), "<C:<class '.TestC.test_no_name.<locals>.NoName'>>")

    def test_missing_expected_attribute_not_partial(self):

        class MyClass(object):
            def __init__(self, **attrs):
                self.__dict__.update(attrs)

        c = Comparison(MyClass, b=2, c=3, partial=False)
        assert c != MyClass(a=1, b=2)

    def test_missing_expected_attribute_partial(self):

        class MyClass(object):
            def __init__(self, **attrs):
                self.__dict__.update(attrs)

        c = Comparison(MyClass, b=2, c=3, partial=True)
        assert c != MyClass(a=1, b=2)

    def test_extra_expected_attribute_not_partial(self):

        class MyClass(object):
            def __init__(self, **attrs):
                self.__dict__.update(attrs)

        c = Comparison(MyClass, a=1, partial=False)
        assert c != MyClass(a=1, b=2)

    def test_extra_expected_attribute_partial(self):

        class MyClass(object):
            def __init__(self, **attrs):
                self.__dict__.update(attrs)

        c = Comparison(MyClass, a=1, partial=True)
        assert c == MyClass(a=1, b=2)
