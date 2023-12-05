# -*- test-case-name: twisted.words.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""Exception definitions for Words
"""


class WordsError(Exception):
    def __str__(self) -> str:
        return self.__class__.__name__ + ": " + Exception.__str__(self)


class NoSuchUser(WordsError):
    pass


class DuplicateUser(WordsError):
    pass


class NoSuchGroup(WordsError):
    pass


class DuplicateGroup(WordsError):
    pass


class AlreadyLoggedIn(WordsError):
    pass


__all__ = [
    "WordsError",
    "NoSuchUser",
    "DuplicateUser",
    "NoSuchGroup",
    "DuplicateGroup",
    "AlreadyLoggedIn",
]
