# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import absolute_import, division

from twisted.trial import unittest
from twisted.python import roots

class RootsTests(unittest.TestCase):

    def testExceptions(self):
        request = roots.Request()
        try:
            request.write(b"blah")
        except NotImplementedError:
            pass
        else:
            self.fail()
        try:
            request.finish()
        except NotImplementedError:
            pass
        else:
            self.fail()

    def testCollection(self):
        collection = roots.Collection()
        collection.putEntity("x", 'test')
        self.assertEqual(collection.getStaticEntity("x"),
                             'test')
        collection.delEntity("x")
        self.assertEqual(collection.getStaticEntity('x'),
                             None)
        try:
            collection.storeEntity("x", None)
        except NotImplementedError:
            pass
        else:
            self.fail()
        try:
            collection.removeEntity("x", None)
        except NotImplementedError:
            pass
        else:
            self.fail()

    def testConstrained(self):
        class const(roots.Constrained):
            def nameConstraint(self, name):
                return (name == 'x')
        c = const()
        self.assertIsNone(c.putEntity('x', 'test'))
        self.assertRaises(roots.ConstraintViolation,
                              c.putEntity, 'y', 'test')


    def testHomogenous(self):
        h = roots.Homogenous()
        h.entityType = int
        h.putEntity('a', 1)
        self.assertEqual(h.getStaticEntity('a'),1 )
        self.assertRaises(roots.ConstraintViolation,
                              h.putEntity, 'x', 'y')
