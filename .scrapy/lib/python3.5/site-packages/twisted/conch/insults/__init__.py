"""
Insults: a replacement for Curses/S-Lang.

Very basic at the moment."""

from twisted.python import deprecate, versions

deprecate.deprecatedModuleAttribute(
    versions.Version("Twisted", 10, 1, 0),
    "Please use twisted.conch.insults.helper instead.",
    __name__, "colors")

deprecate.deprecatedModuleAttribute(
    versions.Version("Twisted", 10, 1, 0),
    "Please use twisted.conch.insults.insults instead.",
    __name__, "client")
