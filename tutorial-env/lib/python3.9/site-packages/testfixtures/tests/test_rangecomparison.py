from decimal import Decimal
from testfixtures import RangeComparison as R, ShouldRaise, compare
from unittest import TestCase


class Tests(TestCase):

    def test_equal_yes_rhs(self):
        self.assertTrue(5 == R(2, 5))

    def test_equal_yes_lhs(self):
        self.assertTrue(R(2, 5) == 2)

    def test_equal_no_rhs(self):
        self.assertFalse(5 == R(2, 4))

    def test_equal_no_lhs(self):
        self.assertFalse(R(2, 3) == 5)

    def test_not_equal_yes_rhs(self):
        self.assertTrue(5 != R(2, 2))

    def test_not_equal_yes_lhs(self):
        self.assertTrue(R(2, 4) != 1)

    def test_not_equal_no_rhs(self):
        self.assertFalse(5 != R(-10, 10))

    def test_not_equal_no_lhs(self):
        self.assertFalse(R(2, 5) != 2)

    def test_equal_in_sequence_rhs(self):
        self.assertEqual((1, 2, 5),
                         (1, 2, R(2, 5)))

    def test_equal_in_sequence_lhs(self):
        self.assertEqual((1, 2, R(2, 5)),
                         (1, 2, 5))

    def test_not_equal_in_sequence_rhs(self):
        self.assertNotEqual((1, 2, 5),
                            (1, 2, R(2, 4)))

    def test_not_equal_in_sequence_lhs(self):
        self.assertNotEqual((1, 2, R(2, 4)),
                            (1, 2, 5))

    def test_not_numeric_rhs(self):
        with ShouldRaise(TypeError):
            'abc' == R(2, 5)
        with ShouldRaise(TypeError):
            {} == R(2, 5)
        with ShouldRaise(TypeError):
            [] == R(2, 5)

    def test_not_numeric_lhs(self):
        with ShouldRaise(TypeError):
            R(2, 5) == 'abc'
        with ShouldRaise(TypeError):
            R(2, 5) == {}
        with ShouldRaise(TypeError):
            R(2, 5) == []

    def test_repr(self):
        compare('<Range: [2, 5]>',
                repr(R(2, 5)))

    def test_str(self):
        compare('<Range: [2, 5]>',
                str(R(2, 5)))

    def test_str_negative(self):
        compare('<Range: [2, 5]>', repr(R(2, 5)))

    def test_equal_yes_decimal_lhs(self):
        self.assertTrue(R(2, 5) == Decimal(3))

    def test_equal_yes_decimal_rhs(self):
        self.assertTrue(Decimal(3) == R(2, 5))

    def test_equal_no_decimal_lhs(self):
        self.assertFalse(R(2, 5) == Decimal(1.0))

    def test_equal_no_decimal_rhs(self):
        self.assertFalse(Decimal(1.0) == R(2, 5))

    def test_equal_yes_float_lhs(self):
        self.assertTrue(R(2, 5) == 3.0)

    def test_equal_yes_float_rhs(self):
        self.assertTrue(3.0 == R(2, 5))

    def test_equal_no_float_lhs(self):
        self.assertFalse(R(2, 5) == 1.0)

    def test_equal_no_float_rhs(self):
        self.assertFalse(1.0 == R(2, 5))

    def test_equal_yes_decimal_in_range_lhs(self):
        self.assertTrue(R(Decimal(1), 5) == 3)
        self.assertTrue(R(1, Decimal(5)) == 3)
        self.assertTrue(R(Decimal(1), Decimal(5)) == 3)

    def test_equal_yes_decimal_in_range_rhs(self):
        self.assertTrue(3 == R(Decimal(1), 5))
        self.assertTrue(3 == R(1, Decimal(5)))
        self.assertTrue(3 == R(Decimal(1), Decimal(5)))

    def test_equal_no_decimal_in_range_lhs(self):
        self.assertFalse(R(Decimal(1), 5) == 6)
        self.assertFalse(R(1, Decimal(5)) == 6)
        self.assertFalse(R(Decimal(1), Decimal(5)) == 6)

    def test_equal_no_decimal_in_range_rhs(self):
        self.assertFalse(6 == R(Decimal(1), 5))
        self.assertFalse(6 == R(1, Decimal(5)))
        self.assertFalse(6 == R(Decimal(1), Decimal(5)))

    def test_equal_yes_float_in_range_lhs(self):
        self.assertTrue(R(1.0, 5) == 3)
        self.assertTrue(R(1, 5.0) == 3)
        self.assertTrue(R(1.0, 5.0) == 3)

    def test_equal_yes_float_in_range_rhs(self):
        self.assertTrue(3 == R(1.0, 5))
        self.assertTrue(3 == R(1, 5.0))
        self.assertTrue(3 == R(1.0, 5.0))

    def test_equal_no_float_in_range_lhs(self):
        self.assertFalse(R(1.0, 5) == 6)
        self.assertFalse(R(1, 5.0) == 6)
        self.assertFalse(R(1.0, 5.0) == 6)

    def test_equal_no_float_in_range_rhs(self):
        self.assertFalse(6 == R(1.0, 5))
        self.assertFalse(6 == R(1, 5.0))
        self.assertFalse(6 == R(1.0, 5.0))

    def test_equal_yes_negative_lhs(self):
        self.assertTrue(R(-5, 5) == -3)
        self.assertTrue(R(-10, -5) == -7)

    def test_equal_yes_negative_rhs(self):
        self.assertTrue(-2 == R(-5, 5))
        self.assertTrue(-7 == R(-10, -5))

    def test_equal_no_negative_lhs(self):
        self.assertFalse(R(-5, 5) == -10)
        self.assertFalse(R(-10, -5) == -3)

    def test_equal_no_negative_rhs(self):
        self.assertFalse(-10 == R(-5, 5))
        self.assertFalse(-30 == R(-10, -5))

    def test_equal_yes_no_range_lhs(self):
        self.assertTrue(R(0, 0) == 0)
        self.assertTrue(R(2, 2) == 2)
        self.assertTrue(R(-1, -1) == -1)

    def test_equal_yes_no_range_rhs(self):
        self.assertTrue(0 == R(0, 0))
        self.assertTrue(2 == R(2, 2))
        self.assertTrue(-1 == R(-1, -1))

    def test_equal_no_no_range_lhs(self):
        self.assertFalse(R(0, 0) == 1)
        self.assertFalse(R(2, 2) == 1)
        self.assertFalse(R(-1, -1) == 11)

    def test_equal_no_no_range_rhs(self):
        self.assertFalse(1 == R(0, 0))
        self.assertFalse(1 == R(2, 2))
        self.assertFalse(1 == R(-1, -1))
