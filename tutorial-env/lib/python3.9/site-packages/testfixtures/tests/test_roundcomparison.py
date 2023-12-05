from decimal import Decimal
from testfixtures import RoundComparison as R, compare, ShouldRaise
from unittest import TestCase


class Tests(TestCase):

    def test_equal_yes_rhs(self):
        self.assertTrue(0.123457 == R(0.123456, 5))

    def test_equal_yes_lhs(self):
        self.assertTrue(R(0.123456, 5) == 0.123457)

    def test_equal_no_rhs(self):
        self.assertFalse(0.123453 == R(0.123456, 5))

    def test_equal_no_lhs(self):
        self.assertFalse(R(0.123456, 5) == 0.123453)

    def test_not_equal_yes_rhs(self):
        self.assertFalse(0.123457 != R(0.123456, 5))

    def test_not_equal_yes_lhs(self):
        self.assertFalse(R(0.123456, 5) != 0.123457)

    def test_not_equal_no_rhs(self):
        self.assertTrue(0.123453 != R(0.123456, 5))

    def test_not_equal_no_lhs(self):
        self.assertTrue(R(0.123456, 5) != 0.123453)

    def test_equal_in_sequence_rhs(self):
        self.assertEqual((1, 2, 0.123457),
                         (1, 2, R(0.123456, 5)))

    def test_equal_in_sequence_lhs(self):
        self.assertEqual((1, 2, R(0.123456, 5)),
                         (1, 2, 0.123457))

    def test_not_equal_in_sequence_rhs(self):
        self.assertNotEqual((1, 2, 0.1236),
                            (1, 2, R(0.123456, 5)))

    def test_not_equal_in_sequence_lhs(self):
        self.assertNotEqual((1, 2, R(0.123456, 5)),
                            (1, 2, 0.1236))

    def test_not_numeric_rhs(self):
        with ShouldRaise(TypeError):
            'abc' == R(0.123456, 5)

    def test_not_numeric_lhs(self):
        with ShouldRaise(TypeError):
            R(0.123456, 5) == 'abc'

    def test_repr(self):
        compare('<R:0.12346 to 5 digits>',
                repr(R(0.123456, 5)))

    def test_str(self):
        compare('<R:0.12346 to 5 digits>',
                repr(R(0.123456, 5)))

    def test_str_negative(self):
        compare('<R:123500 to -2 digits>', repr(R(123456, -2)))

    TYPE_ERROR_DECIMAL = TypeError(
        "Cannot compare <R:0.12346 to 5 digits> with <class 'decimal.Decimal'>"
        )

    def test_equal_yes_decimal_to_float_rhs(self):
        with ShouldRaise(self.TYPE_ERROR_DECIMAL):
            self.assertTrue(Decimal("0.123457") == R(0.123456, 5))

    def test_equal_yes_decimal_to_float_lhs(self):
        with ShouldRaise(self.TYPE_ERROR_DECIMAL):
            self.assertTrue(R(0.123456, 5) == Decimal("0.123457"))

    def test_equal_no_decimal_to_float_rhs(self):
        with ShouldRaise(self.TYPE_ERROR_DECIMAL):
            self.assertFalse(Decimal("0.123453") == R(0.123456, 5))

    def test_equal_no_decimal_to_float_lhs(self):
        with ShouldRaise(self.TYPE_ERROR_DECIMAL):
            self.assertFalse(R(0.123456, 5) == Decimal("0.123453"))

    TYPE_ERROR_FLOAT = TypeError(
        "Cannot compare <R:0.12346 to 5 digits> with <class 'float'>"
        )

    def test_equal_yes_float_to_decimal_rhs(self):
        with ShouldRaise(self.TYPE_ERROR_FLOAT):
            self.assertTrue(0.123457 == R(Decimal("0.123456"), 5))

    def test_equal_yes_float_to_decimal_lhs(self):
        with ShouldRaise(self.TYPE_ERROR_FLOAT):
            self.assertTrue(R(Decimal("0.123456"), 5) == 0.123457)

    def test_equal_no_float_to_decimal_rhs(self):
        with ShouldRaise(self.TYPE_ERROR_FLOAT):
            self.assertFalse(0.123453 == R(Decimal("0.123456"), 5))

    def test_equal_no_float_to_decimal_lhs(self):
        with ShouldRaise(self.TYPE_ERROR_FLOAT):
            self.assertFalse(R(Decimal("0.123456"), 5) == 0.123453)

    def test_integer_float(self):
        with ShouldRaise(TypeError):
            1 == R(1.000001, 5)

    def test_float_integer(self):
        with ShouldRaise(TypeError):
            R(1.000001, 5) == 1

    def test_equal_yes_integer_other_rhs(self):
        self.assertTrue(10 == R(11, -1))

    def test_equal_yes_integer_lhs(self):
        self.assertTrue(R(11, -1) == 10)

    def test_equal_no_integer_rhs(self):
        self.assertFalse(10 == R(16, -1))

    def test_equal_no_integer_lhs(self):
        self.assertFalse(R(16, -1) == 10)

    def test_equal_integer_zero_precision(self):
        self.assertTrue(1 == R(1, 0))

    def test_equal_yes_negative_precision(self):
        self.assertTrue(149.123 == R(101.123, -2))

    def test_equal_no_negative_precision(self):
        self.assertFalse(149.123 == R(150.001, -2))

    def test_decimal_yes_rhs(self):
        self.assertTrue(Decimal('0.123457') == R(Decimal('0.123456'), 5))

    def test_decimal_yes_lhs(self):
        self.assertTrue(R(Decimal('0.123456'), 5) == Decimal('0.123457'))

    def test_decimal_no_rhs(self):
        self.assertFalse(Decimal('0.123453') == R(Decimal('0.123456'), 5))

    def test_decimal_no_lhs(self):
        self.assertFalse(R(Decimal('0.123456'), 5) == Decimal('0.123453'))
