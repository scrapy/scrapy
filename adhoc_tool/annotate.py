""" Annotate an entire source file with flags used by code coverage tool.
    The flags indicate whether a branch was taken or not.

    NOTE: This script DOES NOT handle ternary operators and list comprehensions
    Info about token types: https://www.asmeurer.com/brown-water-python/tokens.html
"""
__author__ = "Felix Liljefors"

import sys
import tokenize
import token
import strip_comments
import os
from token import NAME, INDENT, DEDENT
from adhoc_cov_config import BRANCH_COUNT, BRANCH_LIST_NAME

# Keep track of which lines contain conditional statements
conditional_line_nums = []


def annotate(fname):
    global BRANCH_COUNT
    global conditional_line_nums

    # Strip source file from comments and docstrings
    strip_comments.do_file(fname)

    src = open('stripped_' + fname)
    annotated_src = open('annotated_' + fname, 'w')
    annotated_src.write('from adhoc_cov_config import BRANCHES\n\n')

    indent_lvl = 0
    prev_logical_line = ''
    prev_logical_line_num = -1
    last_condition_type = None

    token_gen = tokenize.generate_tokens(src.readline)
    for type, string, (srow, _), (_, _), logical_line in token_gen:
        # Keep track of indentation. One indent = 4 spaces
        if type == INDENT:
            indent_lvl += 4
        elif type == DEDENT:
            indent_lvl -= 4

        if logical_line != prev_logical_line:
            # Write previous logical line
            annotated_src.write(prev_logical_line)

            # Check if previous logical line contained a conditional
            # If so, a boolean flag should be inserted on between previous and current logical line
            if last_condition_type != None:
                # Match indentation to current logical line and add branch flag variable
                annotated_src.write(
                    ' ' * indent_lvl + f'{BRANCH_LIST_NAME}[{BRANCH_COUNT}] = True\n')
                BRANCH_COUNT += 1

                # Keep track of which lines contain conditional statements
                conditional_line_nums += [prev_logical_line_num]

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

            # Record conditional type (boolean flag will be inserted on logical line below)
            last_condition_type = string

            # Record line number where current logical line started
            prev_logical_line_num = srow

    # Clean up
    try:
        annotated_src.close()
        src.close()
        os.remove('stripped_' + fname)
    except OSError:
        pass


if __name__ == "__main__":
    # Pass filename provided as cmd line arg
    annotate(sys.argv[1])

    # Print some details of the annotation
    print(f'Summary:\n \
    Branches detected: {BRANCH_COUNT} \n \
    On lines: {conditional_line_nums}'
          )
