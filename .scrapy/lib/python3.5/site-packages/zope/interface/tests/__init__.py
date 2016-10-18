import os
import unittest

def additional_tests():
    suites = unittest.TestSuite()
    for file in os.listdir(os.path.dirname(__file__)):
        if file.endswith('.py') and file!='__init__.py':
            name = os.path.splitext(file)[0]
            module = __import__('.'.join((__name__, name)), globals(), 
                                locals(), [name])
            if hasattr(module, 'test_suite'):
                suites.addTests(module.test_suite())
    return suites
