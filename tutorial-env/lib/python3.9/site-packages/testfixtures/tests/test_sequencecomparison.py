from testfixtures import SequenceComparison, generator, compare, Subset, Permutation


class TestSequenceComparison(object):

    def test_repr(self):
        compare(repr(SequenceComparison(1, 2, 3)),
                expected='<SequenceComparison(ordered=True, partial=False)>1, 2, 3</>')

    def test_repr_long(self):
        actual = repr(SequenceComparison('a', 'b', 'c'*1000))[:60]
        compare(actual,
                expected='\n'
                         "<SequenceComparison(ordered=True, partial=False)>\n'a',\n 'b'")

    def test_repr_after_equal(self):
        s = SequenceComparison(1, 2, 3)
        assert s == (1, 2, 3)
        compare(repr(s), expected='<SequenceComparison(ordered=True, partial=False)>1, 2, 3</>')

    def test_equal_list(self):
        s = SequenceComparison(1, 2, 3)
        assert s == [1, 2, 3]

    def test_equal_tuple(self):
        s = SequenceComparison(1, 2, 3)
        assert s == (1, 2, 3)

    def test_equal_nested_unhashable_unordered(self):
        s = SequenceComparison({1}, {2}, {2}, ordered=False)
        assert s == ({2}, {1}, {2})

    def test_equal_nested_unhashable_unordered_partial(self):
        s = SequenceComparison({1}, {2}, {2}, ordered=False, partial=True)
        assert s == ({2}, {1}, {2}, {3})

    def test_equal_generator(self):
        s = SequenceComparison(1, 2, 3)
        assert s == generator(1, 2, 3)

    def test_equal_unordered(self):
        s = SequenceComparison(1, 2, 3, ordered=False)
        assert s == (1, 3, 2)

    def test_equal_partial_unordered(self):
        s = SequenceComparison(1, 2, ordered=False, partial=True)
        assert s == (2, 1, 4)

    def test_equal_partial_ordered(self):
        s = SequenceComparison(1, 2, 1, ordered=True, partial=True)
        assert s == (1, 1, 2, 1)

    def test_equal_ordered_duplicates(self):
        s = SequenceComparison(1, 2, 2, ordered=True, partial=True)
        assert s == (1, 2, 2, 3)

    def test_unequal_bad_type(self):
        s = SequenceComparison(1, 3)
        assert s != object()
        compare(repr(s),
                expected="<SequenceComparison(ordered=True, partial=False)(failed)>bad type</>")

    def test_unequal_list(self):
        s = SequenceComparison(1, 2, 3)
        assert s != (1, 2, 4)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=False)(failed)>\n'
            'same:\n'
            '[1, 2]\n\n'
            'expected:\n'
            '[3]\n\n'
            'actual:\n'
            '[4]\n'
            '</SequenceComparison(ordered=True, partial=False)>'
        ))

    def test_unequal_same_but_all_wrong_order(self):
        s = SequenceComparison(1, 2, 3)
        assert s != (3, 1, 2)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=False)(failed)>\n'
            'same:\n'
            '[]\n\n'
            'expected:\n'
            '[1, 2, 3]\n\n'
            'actual:\n'
            '[3, 1, 2]\n'
            '</SequenceComparison(ordered=True, partial=False)>'
        ))

    def test_unequal_prefix_match_but_partial_false(self):
        s = SequenceComparison(1, 2, partial=False)
        assert s != (1, 2, 4)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=False)(failed)>\n'
            'same:\n'
            '[1, 2]\n\n'
            'expected:\n'
            '[]\n\n'
            'actual:\n'
            '[4]\n'
            '</SequenceComparison(ordered=True, partial=False)>'
        ))

    def test_unequal_partial_ordered(self):
        s = SequenceComparison(1, 3, 5, ordered=True, partial=True, recursive=False)
        assert s != (1, 2, 3, 4, 0)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=True)(failed)>\n'
            'ignored:\n'
            '[2, 4, 0]\n\n'
            'same:\n'
            '[1, 3]\n\n'
            'expected:\n'
            '[5]\n\n'
            'actual:\n'
            '[]\n'
            '</SequenceComparison(ordered=True, partial=True)>'
        ))

    def test_unequal_partial_ordered_recursive(self):
        s = SequenceComparison(1, 3, 5, ordered=True, partial=True, recursive=True)
        assert s != (1, 2, 3, 4, 0)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=True)(failed)>\n'
            'ignored:\n'
            '[4, 0]\n\n'
            'same:\n'
            '[1]\n\n'
            'expected:\n'
            '[3, 5]\n\n'
            'actual:\n'
            '[2, 3]\n'
            '</SequenceComparison(ordered=True, partial=True)>'
        ))

    def test_unequal_partial_ordered_only_one_ignored_recursive(self):
        s = SequenceComparison(1, 2, ordered=True, partial=True, recursive=True)
        assert s != (2, 1, 4)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=True)(failed)>\n'
            'ignored:\n'
            '[4]\n\n'
            'same:\n'
            '[]\n\n'
            'expected:\n'
            '[1, 2]\n\n'
            'actual:\n'
            '[2, 1]\n'
            '</SequenceComparison(ordered=True, partial=True)>'
        ))

    def test_unequal_full_ordered(self):
        s = SequenceComparison(1, 3, 5, ordered=True, partial=False)
        assert s != (0, 1, 2, 3, 4)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=False)(failed)>\n'
            'same:\n'
            '[]\n\n'
            'expected:\n'
            '[1, 3, 5]\n\n'
            'actual:\n'
            '[0, 1, 2, 3, 4]\n'
            '</SequenceComparison(ordered=True, partial=False)>'
        ))

    def test_unequal_partial_ordered_with_prefix(self):
        s = SequenceComparison('a', 'b', 1, 2, ordered=True, partial=True)
        assert s != ('a', 'b', 2, 1, 4)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=True)(failed)>\n'
            'ignored:\n'
            '[2, 4]\n\n'
            'same:\n'
            "['a', 'b', 1]\n\n"
            'expected:\n'
            '[2]\n\n'
            'actual:\n'
            '[]\n'
            '</SequenceComparison(ordered=True, partial=True)>'
        ))

    def test_unequal_partial_unordered(self):
        s = SequenceComparison(1, 3, ordered=False, partial=True)
        assert s != (2, 1, 4)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=False, partial=True)(failed)>\n'
            'ignored:\n'
            '[2, 4]\n\n'
            'same:\n'
            "[1]\n\n"
            'in expected but not actual:\n'
            "[3]\n"
            '</SequenceComparison(ordered=False, partial=True)>'
        ))

    def test_unequal_unordered_duplicates(self):
        s = SequenceComparison(2, 1, 2, ordered=False, partial=False)
        assert s != (1, 2)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=False, partial=False)(failed)>\n'
            'same:\n'
            "[2, 1]\n\n"
            'in expected but not actual:\n'
            "[2]\n"
            '</SequenceComparison(ordered=False, partial=False)>'
        ))

    def test_unequal_partial_unordered_duplicates(self):
        s = SequenceComparison(1, 2, 2, ordered=False, partial=True)
        assert s != (1, 2)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=False, partial=True)(failed)>\n'
            'same:\n'
            "[1, 2]\n\n"
            'in expected but not actual:\n'
            "[2]\n"
            '</SequenceComparison(ordered=False, partial=True)>'
        ))

    def test_unequal_partial_ordered_duplicates(self):
        s = SequenceComparison(1, 2, 2, partial=True)
        assert s != (1, 2)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=True)(failed)>\n'
            'same:\n'
            "[1, 2]\n\n"
            'expected:\n'
            '[2]\n\n'
            'actual:\n'
            '[]\n'
            '</SequenceComparison(ordered=True, partial=True)>'
        ))

    def test_unequal_generator(self):
        s = SequenceComparison(1, 3)
        assert s != generator(1, 2)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=False)(failed)>\n'
            'same:\n'
            "[1]\n\n"
            'expected:\n'
            '[3]\n\n'
            'actual:\n'
            '[2]\n'
            '</SequenceComparison(ordered=True, partial=False)>'
        ))

    def test_unequal_nested(self):
        s = SequenceComparison({1: 'a', 2: 'b'}, [1, 2], recursive=False)
        assert s != ({2: 'b', 3: 'c'}, [1, 3])
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=False)(failed)>\n'
            'same:\n'
            "[]\n\n"
            'expected:\n'
            "[{1: 'a', 2: 'b'}, [1, 2]]\n\n"
            'actual:\n'
            "[{2: 'b', 3: 'c'}, [1, 3]]\n"
            '</SequenceComparison(ordered=True, partial=False)>'
        ))

    def test_unequal_nested_recursive(self):
        s = SequenceComparison({1: 'a', 2: 'b'}, [1, 2], recursive=True)
        assert s != ({2: 'b', 3: 'c'}, [1, 3])
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=False)(failed)>\n'
            'same:\n'
            "[]\n\n"
            'expected:\n'
            "[{1: 'a', 2: 'b'}, [1, 2]]\n\n"
            'actual:\n'
            "[{2: 'b', 3: 'c'}, [1, 3]]\n\n"
            "While comparing [0]: dict not as expected:\n\n"
            "same:\n"
            "[2]\n\n"
            "in expected but not actual:\n"
            "1: 'a'\n\n"
            "in actual but not expected:\n"
            "3: 'c'\n"
            '</SequenceComparison(ordered=True, partial=False)>'
        ))

    def test_unequal_nested_unhashable_unordered(self):
        s = SequenceComparison({2: True}, {1: True}, {2: True}, {3: True}, ordered=False)
        assert s != ({1: True}, {2: True}, {4: True})
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=False, partial=False)(failed)>\n'
            'same:\n'
            "[{2: True}, {1: True}]\n\n"
            'in expected but not actual:\n'
            "[{2: True}, {3: True}]\n\n"
            'in actual but not expected:\n'
            "[{4: True}]\n"
            '</SequenceComparison(ordered=False, partial=False)>'
        ))

    def test_unequal_nested_unhashable_unordered_partial(self):
        s = SequenceComparison({2: True}, {1: True}, {2: True}, {3: True},
                               ordered=False, partial=True)
        assert s != ({1: True}, {2: True}, {4: True})
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=False, partial=True)(failed)>\n'
            'ignored:\n'
            "[{4: True}]\n\n"
            'same:\n'
            "[{2: True}, {1: True}]\n\n"
            'in expected but not actual:\n'
            "[{2: True}, {3: True}]\n"
            '</SequenceComparison(ordered=False, partial=True)>'
        ))

    def test_unequal_wrong_order(self):
        s = SequenceComparison(1, 2, 3)
        assert s != (1, 3, 2)
        compare(repr(s), expected=(
            '\n'
            '<SequenceComparison(ordered=True, partial=False)(failed)>\n'
            'same:\n'
            "[1]\n\n"
            'expected:\n'
            '[2, 3]\n\n'
            'actual:\n'
            '[3, 2]\n'
            '</SequenceComparison(ordered=True, partial=False)>'
        ))

    def test_partial_nothing_specified(self):
        s = SequenceComparison(partial=True)
        assert s == {}

    def test_partial_wrong_type(self):
        s = SequenceComparison(partial=True)
        assert s != object()


class TestSubset(object):

    def test_equal(self):
        assert Subset({1}, {2}) == [{1}, {2}, {3}]

    def test_unequal(self):
        assert Subset({1}, {2}) != [{1}]


class TestPermutation(object):

    def test_equal(self):
        assert Permutation({1}, {2}) == [{2}, {1}]

    def test_unequal(self):
        assert Permutation({1}) != [{2}, {1}]
