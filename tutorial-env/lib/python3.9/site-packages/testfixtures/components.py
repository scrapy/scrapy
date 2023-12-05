"""
Helpers for working with Zope and its components.
"""
import atexit
import warnings
from typing import Set

from zope.component import getSiteManager
from zope.interface.registry import Components


class TestComponents:
    """
    A helper for providing a sterile registry when testing
    with ``zope.component``.

    Instantiation will install an empty registry that will be returned
    by :func:`zope.component.getSiteManager`.
    """
    __test__: bool = False

    instances: Set['TestComponents'] = set()
    atexit_setup: bool = False

    def __init__(self):
        self.registry: Components = Components('Testing')
        self.old: Components = getSiteManager.sethook(lambda: self.registry)
        self.instances.add(self)
        if not self.__class__.atexit_setup:
            atexit.register(self.atexit)
            self.__class__.atexit_setup = True

    def uninstall(self):
        """
        Remove the sterile registry and replace it with the one that
        was in place before this :class:`TestComponents` was
        instantiated.
        """
        getSiteManager.sethook(self.old)
        self.instances.remove(self)

    @classmethod
    def atexit(cls):
        if cls.instances:
            warnings.warn(
                'TestComponents instances not uninstalled by shutdown!'
                )
