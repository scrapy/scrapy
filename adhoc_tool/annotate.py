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
from token import NAME, INDENT, DEDENT, NEWLINE, NL, COMMENT
from adhoc_cov_config import BRANCH_COUNT, BRANCH_LIST_NAME

# Keep track of which lines contain conditional statements
conditional_line_nums = []
WHITESPACE_TOKENS = {INDENT, NEWLINE, NL, COMMENT}
CONDITIONALS = {
    'if',
    'else',
    'elif',
    'for',
    'while',
    'try',
    'catch',
    'finally',
    'except',
}


def annotate(file_name, func_name):
    global BRANCH_COUNT
    global conditional_line_nums

    # Strip source file from comments and docstrings
    strip_comments.do_file(file_name)

    src = open('stripped_' + file_name)
    annotated_src = open('annotated_' + file_name, 'w')
    annotated_src.write(
        'from adhoc_cov_config import BRANCHES, BRANCH_COUNT\n\n')

    indent_lvl = 0
    prev_logical_line = ''
    prev_logical_line_num = -1
    last_condition_type = None
    within_function = False
    fn_header_row_start = -1
    fn_header_row_end = -1
    fn_header_indent_lvl = -1

    token_gen = tokenize.generate_tokens(src.readline)
    func_def_header = f'def {func_name}('

    for t in token_gen:
        t_type, string, (srow, _), (erow, _), logical_line = t
        # Keep track of indentation. One indent = 4 spaces
        if t_type == INDENT:
            indent_lvl += 4
        elif t_type == DEDENT:
            indent_lvl -= 4

        # Stop annotating when reaching outside indentation of function
        # Set global var BRANCH_COUNT i.e total number of branch flags created on last line
        if within_function and \
                indent_lvl <= fn_header_indent_lvl and \
                srow > fn_header_row_start and \
                t_type not in WHITESPACE_TOKENS:

            annotated_src.write(
                ' ' * (fn_header_indent_lvl + 4) + f'BRANCH_COUNT = {BRANCH_COUNT}\n\n')
            within_function = False

        if logical_line != prev_logical_line:
            # Write previous logical line
            annotated_src.write(prev_logical_line)

            # Find the relevant function in source file before starting annotation
            if not within_function and func_def_header in logical_line:

                within_function = True
                fn_header_row_start = srow
                fn_header_row_end = erow
                fn_header_indent_lvl = indent_lvl

            elif srow == fn_header_row_end + 1:
                annotated_src.write(
                    ' ' * (fn_header_indent_lvl + 4) + f'global BRANCHES\n')
                annotated_src.write(
                    ' ' * (fn_header_indent_lvl + 4) + f'global BRANCH_COUNT\n')

            # Check if previous logical line contained a conditional
            # If so, a boolean flag should be inserted on between previous and current logical line
            elif within_function and last_condition_type != None:
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

        # Check if current logical line begins with conditional keyword
        if within_function and t_type == NAME and string in CONDITIONALS and string in logical_line.strip().split()[0]:
            # Record conditional type (boolean flag will be inserted on logical line below)
            last_condition_type = string

            # Record line number where current logical line started
            prev_logical_line_num = srow

    # Clean up
    try:
        annotated_src.close()
        src.close()
        os.remove('stripped_' + file_name)
    except OSError:
        pass


if __name__ == "__main__":
    # Pass filename and function name provided as cmd line args
    annotate(sys.argv[1], sys.argv[2])

    # Print some details of the annotation
    print(f'Summary:\n \
    Branches detected: {BRANCH_COUNT} \n \
    On lines: {conditional_line_nums}'
          )
