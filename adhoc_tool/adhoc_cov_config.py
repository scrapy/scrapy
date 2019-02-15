"""
Configuration file holding a dynamic global variable for the ad-hoc code coverage tool.
Source: https://docs.python.org/3/faq/programming.html#how-do-i-share-global-variables-across-modules
"""
__author__ = "Felix Liljefors"

BRANCHES = [False] * 200
BRANCH_LIST_NAME = 'BRANCHES'
BRANCH_COUNT = 0
