from unittest import TestCase

from types import GeneratorType

from testfixtures import generator


class TestG(TestCase):

    def test_example(self):
        g = generator(1, 2, 3)
        self.assertTrue(isinstance(g, GeneratorType))
        self.assertEqual(tuple(g), (1, 2, 3))

    def test_from_sequence(self):
        s = (1, 2, 3)
        g = generator(*s)
        self.assertTrue(isinstance(g, GeneratorType))
        self.assertEqual(tuple(g), (1, 2, 3))
