""" Annotate a source file with flags used by code coverage tool.
    The flags indicate whether a branch was taken or not.
    Note: This annotation doesn't handle ternary operators
    Info about token types: https://www.asmeurer.com/brown-water-python/tokens.html
"""
__author__ = "Felix Liljefors"

import sys
import token
from token import NAME, INDENT, DEDENT
import tokenize

DEBUG = False


def annotate(fname):
    src = open(fname)
    annotated_src = open("annotated_" + fname, "w")

    # prev_toktype = token.INDENT
    indent_lvl = 0
    prev_logical_line = ''
    last_condition_type = None

    token_gen = tokenize.generate_tokens(src.readline)
    for t in token_gen:
        type, string, (srow, scol), (erow, _), logical_line = t

        # Keep track of indentation. One indent = 4 spaces
        if type == INDENT:
            indent_lvl += 4
        elif type == DEDENT:
            indent_lvl -= 4

        debug(
            f'type: {type}\nexact type: {t.exact_type}\nstring: {string}\nlogical line: {logical_line}')

        if logical_line != prev_logical_line:
            # Write previous logical line
            annotated_src.write(prev_logical_line)

            # Check if previous logical line contained a conditional
            # If so, a boolean flag should be inserted on between previous and current logical line
            if last_condition_type != None:
                debug(f'INSERT FLAG ON LINE: {srow}')
                debug(f'TOKEN {type} OCCURS AT COL: {scol}')
                # Match indentation to current logical line
                annotated_src.write(' ' * indent_lvl + 'flag = False\n')
                # Only process a condition once, although a line can have many tokens
                last_condition_type = None

            # Update previous logical line
            prev_logical_line = logical_line

        # Check if current logical line contains conditional keyword
        if type == NAME and \
           string == 'if' or \
           string == 'else' or \
           string == 'elif' or \
           string == 'for' or \
           string == 'while' or \
           string == 'try' or \
           string == 'catch' or \
           string == 'finally':

            # Record where this logical line ends (next line will set boolean flag)
            last_condition_type = string
            debug(f'CONDITIONAL ENDS ON LINE: {erow}')


def debug(str):
    if DEBUG:
        print(str)


if __name__ == "__main__":
    annotate('test.py')
