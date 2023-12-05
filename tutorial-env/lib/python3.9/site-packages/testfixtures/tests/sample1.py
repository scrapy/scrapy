# NB: This file is used in the documentation, if you make changes, ensure
#     you update the line numbers in popen.txt!
"""
A sample module containing the kind of code that
testfixtures helps with testing
"""

from datetime import datetime, date


def str_now_1():
    return str(datetime.now())

now = datetime.now


def str_now_2():
    return str(now())


def str_today_1():
    return str(date.today())

today = date.today


def str_today_2():
    return str(today())

from time import time


def str_time():
    return str(time())


class X:

    def y(self):
        return "original y"

    @classmethod
    def aMethod(cls):
        return cls

    @staticmethod
    def bMethod():
        return 2


def z():
    return "original z"


class SampleClassA:
    def __init__(self, *args):
        self.args = args


class SampleClassB(SampleClassA):
    pass


def a_function():
    return (SampleClassA(1), SampleClassB(2), SampleClassA(3))

some_dict = dict(
    key='value',
    complex_key=[1, 2, 3],
)


class Slotted(object):

    __slots__ = ['x', 'y']

    def __init__(self, x, y):
        self.x = x
        self.y = y
