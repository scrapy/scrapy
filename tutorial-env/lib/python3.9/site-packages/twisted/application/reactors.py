# -*- test-case-name: twisted.test.test_application -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Plugin-based system for enumerating available reactors and installing one of
them.
"""
from typing import Iterable, cast

from zope.interface import Attribute, Interface, implementer

from twisted.internet.interfaces import IReactorCore
from twisted.plugin import IPlugin, getPlugins
from twisted.python.reflect import namedAny


class IReactorInstaller(Interface):
    """
    Definition of a reactor which can probably be installed.
    """

    shortName = Attribute(
        """
    A brief string giving the user-facing name of this reactor.
    """
    )

    description = Attribute(
        """
    A longer string giving a user-facing description of this reactor.
    """
    )

    def install() -> None:
        """
        Install this reactor.
        """

    # TODO - A method which provides a best-guess as to whether this reactor
    # can actually be used in the execution environment.


class NoSuchReactor(KeyError):
    """
    Raised when an attempt is made to install a reactor which cannot be found.
    """


@implementer(IPlugin, IReactorInstaller)
class Reactor:
    """
    @ivar moduleName: The fully-qualified Python name of the module of which
    the install callable is an attribute.
    """

    def __init__(self, shortName: str, moduleName: str, description: str):
        self.shortName = shortName
        self.moduleName = moduleName
        self.description = description

    def install(self) -> None:
        namedAny(self.moduleName).install()


def getReactorTypes() -> Iterable[IReactorInstaller]:
    """
    Return an iterator of L{IReactorInstaller} plugins.
    """
    return getPlugins(IReactorInstaller)


def installReactor(shortName: str) -> IReactorCore:
    """
    Install the reactor with the given C{shortName} attribute.

    @raise NoSuchReactor: If no reactor is found with a matching C{shortName}.

    @raise Exception: Anything that the specified reactor can raise when installed.
    """
    for installer in getReactorTypes():
        if installer.shortName == shortName:
            installer.install()
            from twisted.internet import reactor

            return cast(IReactorCore, reactor)
    raise NoSuchReactor(shortName)
