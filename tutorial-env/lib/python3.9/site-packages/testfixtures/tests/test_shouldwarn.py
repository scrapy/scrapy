from unittest import TestCase

import warnings

from testfixtures import (
    ShouldWarn, compare, ShouldRaise, ShouldNotWarn,
    Comparison as C
)
from testfixtures.compat import PY_37_PLUS
from testfixtures.shouldraise import ShouldAssert

if PY_37_PLUS:
    comma = ''
else:
    comma = ','


class ShouldWarnTests(TestCase):

    def test_warn_expected(self):
        with warnings.catch_warnings(record=True) as backstop:
            with ShouldWarn(UserWarning('foo')):
                warnings.warn('foo')
        compare(len(backstop), expected=0)

    def test_warn_not_expected(self):
        with ShouldAssert(
            "\n<SequenceComparison(ordered=True, partial=False)(failed)>\n"
            "same:\n[]\n\n"
            "expected:\n[]\n\n"
            "actual:\n[UserWarning('foo'"+comma+")]\n"
            "</SequenceComparison(ordered=True, partial=False)> (expected) "
            "!= [UserWarning('foo'"+comma+")] (actual)"
        ):
            with warnings.catch_warnings(record=True) as backstop:
                with ShouldNotWarn():
                    warnings.warn('foo')
        compare(len(backstop), expected=0)

    def test_no_warn_expected(self):
        with ShouldNotWarn():
            pass

    def test_no_warn_not_expected(self):
        with ShouldAssert(
            "\n<SequenceComparison(ordered=True, partial=False)(failed)>\n"
            "same:\n[]\n\n"
            "expected:\n[<C:builtins.UserWarning>args: ('foo',)</>]"
            "\n\nactual:\n[]\n"
            "</SequenceComparison(ordered=True, partial=False)> (expected) != [] (actual)"
        ):
            with ShouldWarn(UserWarning('foo')):
                pass

    def test_filters_removed(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with ShouldWarn(UserWarning("foo")):
                warnings.warn('foo')

    def test_multiple_warnings(self):
        with ShouldRaise(AssertionError) as s:
            with ShouldWarn(UserWarning('foo')):
                warnings.warn('foo')
                warnings.warn('bar')
        content = str(s.raised)
        self.assertTrue('foo' in content)
        self.assertTrue('bar' in content)

    def test_multiple_warnings_ordered(self):
        with warnings.catch_warnings(record=True) as backstop:
            with ShouldWarn(UserWarning('foo'), UserWarning('bar')):
                warnings.warn('foo')
                warnings.warn('bar')
        compare(len(backstop), expected=0)

    def test_multiple_warnings_wrong_order(self):
        with ShouldRaise(AssertionError) as s:
            with ShouldWarn(UserWarning('foo'), UserWarning('bar')):
                warnings.warn('bar')
                warnings.warn('foo')
        content = str(s.raised)
        self.assertTrue('foo' in content)
        self.assertTrue('bar' in content)

    def test_multiple_warnings_ignore_order(self):
        with warnings.catch_warnings(record=True) as backstop:
            with ShouldWarn(UserWarning('foo'), UserWarning('bar'), order_matters=False):
                warnings.warn('bar')
                warnings.warn('foo')
        compare(len(backstop), expected=0)

    def test_minimal_ok(self):
        with ShouldWarn(UserWarning):
            warnings.warn('foo')

    def test_minimal_bad(self):
        with ShouldAssert(
            "\n<SequenceComparison(ordered=True, partial=False)(failed)>\n"
            "same:\n[]\n\n"
            "expected:\n"
            "[<C:builtins.DeprecationWarning(failed)>wrong type</>]\n\n"
            "actual:\n[UserWarning('foo'"+comma+")]\n"
            "</SequenceComparison(ordered=True, partial=False)> (expected) "
            "!= [UserWarning('foo'"+comma+")] (actual)"
        ):
            with ShouldWarn(DeprecationWarning):
                warnings.warn('foo')

    def test_maximal_ok(self):
        with ShouldWarn(DeprecationWarning('foo')):
            warnings.warn_explicit(
                'foo', DeprecationWarning, 'bar.py', 42, 'bar_module'
            )

    def test_maximal_bad(self):
        with ShouldAssert(
            "\n<SequenceComparison(ordered=True, partial=False)(failed)>\n"
            "same:\n[]\n\n"
            "expected:\n[\n"
            "<C:builtins.DeprecationWarning(failed)>\n"
            "attributes differ:\n"
            "'args': ('bar',) (Comparison) != ('foo',) (actual)\n"
            "</C:builtins.DeprecationWarning>]\n\n"
            "actual:\n[DeprecationWarning('foo'"+comma+")]\n"
            "</SequenceComparison(ordered=True, partial=False)> (expected) "
            "!= [DeprecationWarning('foo'"+comma+")] (actual)"
        ):
            with ShouldWarn(DeprecationWarning('bar')):
                warnings.warn_explicit(
                    'foo', DeprecationWarning, 'bar.py', 42, 'bar_module'
                )

    def test_maximal_explore(self):
        with ShouldWarn() as recorded:
            warnings.warn_explicit(
                'foo', DeprecationWarning, 'bar.py', 42, 'bar_module'
            )
        compare(len(recorded), expected=1)

        expected_attrs = dict(
            _category_name='DeprecationWarning',
            category=DeprecationWarning,
            file=None,
            filename='bar.py',
            line=None,
            lineno=42,
            message=C(DeprecationWarning('foo')),
            source=None
        )

        compare(expected=C(warnings.WarningMessage, **expected_attrs),
            actual=recorded[0])

    def test_filter_present(self):
        with ShouldWarn(DeprecationWarning,
                        message="This function is deprecated."):
            warnings.warn("This utility is deprecated.", DeprecationWarning)
            warnings.warn("This function is deprecated.", DeprecationWarning)

    def test_filter_missing(self):
        with ShouldAssert(
            "\n<SequenceComparison(ordered=True, partial=False)(failed)>\n"
            "same:\n[]\n\n"
            "expected:\n[<C:builtins.DeprecationWarning>]\n\n"
            "actual:\n[]\n"
            "</SequenceComparison(ordered=True, partial=False)> (expected) != [] (actual)"
        ):
            with ShouldWarn(DeprecationWarning,
                            message="This function is deprecated."):
                warnings.warn("This utility is deprecated.", DeprecationWarning)
