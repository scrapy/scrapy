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
CONDITIONALS = {
    'if',
    'else',
    'elif',
    'for',
    'while',
    'try',
    'catch',
    'finally',
}


def annotate(file_name, func_name):
    global BRANCH_COUNT
    global conditional_line_nums

    # Strip source file from comments and docstrings
    strip_comments.do_file(file_name)

    src = open('stripped_' + file_name)
    annotated_src = open('annotated_' + file_name, 'w')
    annotated_src.write('from adhoc_cov_config import BRANCHES\n\n')

    indent_lvl = 0
    prev_logical_line = ''
    prev_logical_line_num = -1
    last_condition_type = None
    function_found = False

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

            # Find the relevant function in source file before starting annotation
            if not function_found and 'def' in logical_line and func_name in logical_line:
                function_found = True

            # Check if previous logical line contained a conditional
            # If so, a boolean flag should be inserted on between previous and current logical line
            elif function_found and last_condition_type != None:
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
        if function_found and type == NAME and string in CONDITIONALS and logical_line.strip().split()[0] == string:
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
