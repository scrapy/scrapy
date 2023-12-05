from collections import OrderedDict
from textwrap import dedent

from testfixtures import MappingComparison, ShouldRaise, compare


def check_repr(obj, expected):
    compare(repr(obj), expected=dedent(expected).rstrip('\n'))


class TestMappingComparison(object):

    def test_repr(self):
        m = MappingComparison({'a': 1}, b=2)
        check_repr(m, "<MappingComparison(ordered=False, partial=False)>'a': 1, 'b': 2</>")

    def test_repr_ordered(self):
        m = MappingComparison((('b', 3), ('a', 1)), ordered=True)
        check_repr(m, "<MappingComparison(ordered=True, partial=False)>'b': 3, 'a': 1</>")

    def test_repr_long(self):
        m = MappingComparison({1: 'a', 2: 'b'*60})
        compare(repr(m)[:65],
                expected="\n<MappingComparison(ordered=False, partial=False)>\n1: 'a',\n2: 'bb")

    def test_repr_after_equal(self):
        m = MappingComparison({'a': 1})
        assert m == {'a': 1}
        check_repr(m, "<MappingComparison(ordered=False, partial=False)>'a': 1</>")

    def test_equal_mapping(self):
        m = MappingComparison({'a': 1})
        assert m == {'a': 1}

    def test_equal_sequence(self):
        m = MappingComparison(('a', 1), ('b', 2))
        assert m == {'a': 1, 'b': 2}

    def test_equal_items(self):
        m = MappingComparison(a=1)
        assert m == {'a': 1}

    def test_equal_both(self):
        m = MappingComparison({'a': 1, 'b': 2}, b=3)
        assert m == {'a': 1, 'b': 3}

    def test_equal_items_ordered(self):
        m = MappingComparison(b=3, a=1, ordered=True)
        assert m == {'b': 3, 'a': 1}

    def test_equal_ordered_and_dict_supplied(self):
        m = MappingComparison({'b': 3, 'a': 1}, ordered=True)
        assert m == {'b': 3, 'a': 1}

    def test_equal_ordered_dict_sequence_expected(self):
        m = MappingComparison((('a', 1), ('b', 3)), ordered=True)
        assert m == OrderedDict((('a', 1), ('b', 3)))

    def test_equal_ordered_dict_ordered_dict_expected(self):
        m = MappingComparison(OrderedDict((('a', 1), ('b', 3))), ordered=True)
        assert m == OrderedDict((('a', 1), ('b', 3)))

    def test_equal_partial(self):
        m = MappingComparison({'a': 1}, partial=True)
        assert m == {'a': 1, 'b': 2}

    def test_equal_partial_ordered(self):
        m = MappingComparison((('a', 1), ('b', 3)), ordered=True, partial=True)
        assert m == OrderedDict((('a', 1), ('c', 2), ('b', 3)))

    def test_unequal_wrong_type(self):
        m = MappingComparison({'a': 1})
        assert m != []
        compare(repr(m),
                expected="<MappingComparison(ordered=False, partial=False)(failed)>bad type</>")

    def test_unequal_not_partial(self):
        m = MappingComparison({'a': 1, 'b': 2})
        assert m != {'a': 1, 'b': 2, 'c': 3}
        check_repr(m, expected='''
            <MappingComparison(ordered=False, partial=False)(failed)>
            same:
            ['a', 'b']
            
            in actual but not expected:
            'c': 3
            </MappingComparison(ordered=False, partial=False)>
        ''')

    def test_unequal_keys_and_values(self):
        m = MappingComparison({'a': 1, 'b': 2, 'c': 3})
        assert m != {'a': 1, 'c': 4, 'd': 5}
        check_repr(m, expected='''
            <MappingComparison(ordered=False, partial=False)(failed)>
            same:
            ['a']
            
            in expected but not actual:
            'b': 2
            
            in actual but not expected:
            'd': 5
            
            values differ:
            'c': 3 (expected) != 4 (actual)
            </MappingComparison(ordered=False, partial=False)>
        ''')

    def test_unequal_order(self):
        m = MappingComparison((('b', 3), ('a', 1)), ordered=True)
        assert m != OrderedDict((('a', 1), ('b', 3)))
        check_repr(m, expected='''
            <MappingComparison(ordered=True, partial=False)(failed)>
            wrong key order:
            
            same:
            []
            
            expected:
            ['b', 'a']
            
            actual:
            ['a', 'b']
            </MappingComparison(ordered=True, partial=False)>
        ''')

    def test_unequal_order_recursive(self):
        m = MappingComparison(((('b', 'x'), 3), (('b', 'y'), 1)), ordered=True, recursive=True)
        assert m != OrderedDict(((('b', 'y'), 1), (('b', 'x'), 3)))
        check_repr(m, expected='''
            <MappingComparison(ordered=True, partial=False)(failed)>
            wrong key order:
            
            same:
            []
            
            expected:
            [('b', 'x'), ('b', 'y')]
            
            actual:
            [('b', 'y'), ('b', 'x')]
            
            While comparing [0]: sequence not as expected:
            
            same:
            ('b',)
            
            expected:
            ('x',)
            
            actual:
            ('y',)
            
            While comparing [0][1]: 'x' (expected) != 'y' (actual)
            </MappingComparison(ordered=True, partial=False)>
        ''')

    def test_unequal_order_wrong(self):
        m = MappingComparison(b=3, a=1, ordered=True)
        assert m != {'a': 1, 'b': 3}
        check_repr(m, expected='''
            <MappingComparison(ordered=True, partial=False)(failed)>
            wrong key order:
            
            same:
            []
            
            expected:
            ['b', 'a']
            
            actual:
            ['a', 'b']
            </MappingComparison(ordered=True, partial=False)>
        ''')

    def test_unequal_partial_keys_missing(self):
        m = MappingComparison({'a': 1, 'b': 2}, partial=True)
        assert m != {'a': 1}
        check_repr(m, expected='''
            <MappingComparison(ordered=False, partial=True)(failed)>
            same:
            ['a']
            
            in expected but not actual:
            'b': 2
            </MappingComparison(ordered=False, partial=True)>
        ''')

    def test_unequal_partial_values_wrong(self):
        m = MappingComparison({'a': 1, 'b': 2}, partial=True)
        assert m != {'a': 1, 'b': 3}
        check_repr(m, expected='''
            <MappingComparison(ordered=False, partial=True)(failed)>
            same:
            ['a']
            
            values differ:
            'b': 2 (expected) != 3 (actual)
            </MappingComparison(ordered=False, partial=True)>
        ''')

    def test_unequal_partial_ordered(self):
        m = MappingComparison((('b', 3), ('a', 1)), partial=True, ordered=True)
        assert m != OrderedDict((('a', 1), ('b', 3)))
        check_repr(m, expected='''
            <MappingComparison(ordered=True, partial=True)(failed)>
            wrong key order:
            
            same:
            []
            
            expected:
            ['b', 'a']
            
            actual:
            ['a', 'b']
            </MappingComparison(ordered=True, partial=True)>
        ''')

    def test_unequal_partial_ordered_some_ignored(self):
        m = MappingComparison((('b', 3), ('c', 1), ('a', 1)), partial=True, ordered=True)
        assert m != OrderedDict((('b', 3), ('d', 4), ('a', 1), ('c', 1), ))
        check_repr(m, expected='''
            <MappingComparison(ordered=True, partial=True)(failed)>
            ignored:
            ['d']
            
            wrong key order:
            
            same:
            ['b']
            
            expected:
            ['c', 'a']
            
            actual:
            ['a', 'c']
            </MappingComparison(ordered=True, partial=True)>
        ''')

    def test_unequal_recursive(self):
        m = MappingComparison({'a': 1, 'b': {'c': 2}}, recursive=True)
        assert m != {'a': 1, 'b': {'c': 3}}
        check_repr(m, expected='''
            <MappingComparison(ordered=False, partial=False)(failed)>
            same:
            ['a']
            
            values differ:
            'b': {'c': 2} (expected) != {'c': 3} (actual)
            
            While comparing ['b']: dict not as expected:
            
            values differ:
            'c': 2 (expected) != 3 (actual)
            </MappingComparison(ordered=False, partial=False)>
        ''')

    def test_everything_wrong(self):
        m = MappingComparison((('a', 1), ('b', 2), ('c', 3)),
                              ordered=True, partial=True, recursive=True)
        assert m != OrderedDict((('b', 2), ('a', 1), ('d', 4)))
        check_repr(m, expected='''
            <MappingComparison(ordered=True, partial=True)(failed)>
            ignored:
            ['d']
            
            same:
            ['a', 'b']
            
            in expected but not actual:
            'c': 3
            
            wrong key order:
            
            same:
            []
            
            expected:
            ['a', 'b', 'c']
            
            actual:
            ['b', 'a']
            
            While comparing [0]: 'a' (expected) != 'b' (actual)
            </MappingComparison(ordered=True, partial=True)>
        ''')

    def test_partial_nothing_specified(self):
        m = MappingComparison(partial=True)
        assert m == {}

    def test_partial_nothing_specified_wrong_type(self):
        m = MappingComparison(partial=True)
        assert m != []
        check_repr(m, '<MappingComparison(ordered=False, partial=True)(failed)>bad type</>')

    def test_boolean_return(self):
        m = MappingComparison({'k': 'v'})
        result = m != {'k': 'v'}
        assert isinstance(result, bool)
