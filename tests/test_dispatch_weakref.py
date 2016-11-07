import unittest
import gc

from scrapy.dispatch.weakref_backports import WeakMethod


class HasMethod():
    def method(self):
        pass


class WeakrefBackportsTest(unittest.TestCase):

    def test_weakmethod_creation(self):
        has_method_inst = HasMethod()
        self.assertIsInstance(WeakMethod(has_method_inst.method), WeakMethod)
        with self.assertRaises(TypeError):
            WeakMethod({})

    def test_weakref_weakmethod_eq(self):
        has_method_inst = HasMethod()
        live_receiver = WeakMethod(has_method_inst.method)
        dead_receiver = WeakMethod(HasMethod().method)
        self.assertTrue(live_receiver == live_receiver)
        self.assertFalse(live_receiver == dead_receiver)
        self.assertFalse(live_receiver == HasMethod.method)

    def test_weakref_weakmethod_neq(self):
        has_method_inst = HasMethod()
        live_receiver = WeakMethod(has_method_inst.method)
        dead_receiver = WeakMethod(HasMethod().method)
        self.assertFalse(live_receiver != live_receiver)
        self.assertTrue(live_receiver != dead_receiver)
        self.assertTrue(live_receiver != HasMethod.method)
