r"""
This is based on SmartyPants.py by `Chad Miller`_ <smartypantspy@chad.org>,
version 1.5_1.6.

Copyright and License
=====================

SmartyPants_ license::

    Copyright (c) 2003 John Gruber
    (http://daringfireball.net/)
    All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are
    met:

    *   Redistributions of source code must retain the above copyright
        notice, this list of conditions and the following disclaimer.

    *   Redistributions in binary form must reproduce the above copyright
        notice, this list of conditions and the following disclaimer in
        the documentation and/or other materials provided with the
        distribution.

    *   Neither the name "SmartyPants" nor the names of its contributors
        may be used to endorse or promote products derived from this
        software without specific prior written permission.

    This software is provided by the copyright holders and contributors "as
    is" and any express or implied warranties, including, but not limited
    to, the implied warranties of merchantability and fitness for a
    particular purpose are disclaimed. In no event shall the copyright
    owner or contributors be liable for any direct, indirect, incidental,
    special, exemplary, or consequential damages (including, but not
    limited to, procurement of substitute goods or services; loss of use,
    data, or profits; or business interruption) however caused and on any
    theory of liability, whether in contract, strict liability, or tort
    (including negligence or otherwise) arising in any way out of the use
    of this software, even if advised of the possibility of such damage.


smartypants.py license::

    smartypants.py is a derivative work of SmartyPants.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are
    met:

    *   Redistributions of source code must retain the above copyright
        notice, this list of conditions and the following disclaimer.

    *   Redistributions in binary form must reproduce the above copyright
        notice, this list of conditions and the following disclaimer in
        the documentation and/or other materials provided with the
        distribution.

    This software is provided by the copyright holders and contributors "as
    is" and any express or implied warranties, including, but not limited
    to, the implied warranties of merchantability and fitness for a
    particular purpose are disclaimed. In no event shall the copyright
    owner or contributors be liable for any direct, indirect, incidental,
    special, exemplary, or consequential damages (including, but not
    limited to, procurement of substitute goods or services; loss of use,
    data, or profits; or business interruption) however caused and on any
    theory of liability, whether in contract, strict liability, or tort
    (including negligence or otherwise) arising in any way out of the use
    of this software, even if advised of the possibility of such damage.

.. _Chad Miller: http://web.chad.org/
"""

import re


def sphinx_smarty_pants(t):
    t = t.replace('&quot;', '"')
    t = educate_dashes_oldschool(t)
    t = educate_quotes(t)
    t = t.replace('"', '&quot;')
    return t

# Constants for quote education.

punct_class = r"""[!"#\$\%'()*+,-.\/:;<=>?\@\[\\\]\^_`{|}~]"""
end_of_word_class = r"""[\s.,;:!?)]"""
close_class = r"""[^\ \t\r\n\[\{\(\-]"""
dec_dashes = r"""&#8211;|&#8212;"""

# Special case if the very first character is a quote
# followed by punctuation at a non-word-break. Close the quotes by brute force:
single_quote_start_re = re.compile(r"""^'(?=%s\\B)""" % (punct_class,))
double_quote_start_re = re.compile(r"""^"(?=%s\\B)""" % (punct_class,))

# Special case for double sets of quotes, e.g.:
#   <p>He said, "'Quoted' words in a larger quote."</p>
double_quote_sets_re = re.compile(r""""'(?=\w)""")
single_quote_sets_re = re.compile(r"""'"(?=\w)""")

# Special case for decade abbreviations (the '80s):
decade_abbr_re = re.compile(r"""\b'(?=\d{2}s)""")

# Get most opening double quotes:
opening_double_quotes_regex = re.compile(r"""
                (
                        \s          |   # a whitespace char, or
                        &#160;      |   # a non-breaking space entity, or
                        --          |   # dashes, or
                        &[mn]dash;  |   # named dash entities
                        %s          |   # or decimal entities
                        &\#x201[34];    # or hex
                )
                "                 # the quote
                (?=\w)            # followed by a word character
                """ % (dec_dashes,), re.VERBOSE)

# Double closing quotes:
closing_double_quotes_regex = re.compile(r"""
                #(%s)?   # character that indicates the quote should be closing
                "
                (?=%s)
                """ % (close_class, end_of_word_class), re.VERBOSE)

closing_double_quotes_regex_2 = re.compile(r"""
                (%s)   # character that indicates the quote should be closing
                "
                """ % (close_class,), re.VERBOSE)

# Get most opening single quotes:
opening_single_quotes_regex = re.compile(r"""
                (
                        \s          |   # a whitespace char, or
                        &#160;      |   # a non-breaking space entity, or
                        --          |   # dashes, or
                        &[mn]dash;  |   # named dash entities
                        %s          |   # or decimal entities
                        &\#x201[34];    # or hex
                )
                '                 # the quote
                (?=\w)            # followed by a word character
                """ % (dec_dashes,), re.VERBOSE)

closing_single_quotes_regex = re.compile(r"""
                (%s)
                '
                (?!\s | s\b | \d)
                """ % (close_class,), re.VERBOSE)

closing_single_quotes_regex_2 = re.compile(r"""
                (%s)
                '
                (\s | s\b)
                """ % (close_class,), re.VERBOSE)


def educate_quotes(s):
    """
    Parameter:  String.

    Returns:    The string, with "educated" curly quote HTML entities.

    Example input:  "Isn't this fun?"
    Example output: &#8220;Isn&#8217;t this fun?&#8221;
    """

    # Special case if the very first character is a quote
    # followed by punctuation at a non-word-break. Close the quotes
    # by brute force:
    s = single_quote_start_re.sub("&#8217;", s)
    s = double_quote_start_re.sub("&#8221;", s)

    # Special case for double sets of quotes, e.g.:
    #   <p>He said, "'Quoted' words in a larger quote."</p>
    s = double_quote_sets_re.sub("&#8220;&#8216;", s)
    s = single_quote_sets_re.sub("&#8216;&#8220;", s)

    # Special case for decade abbreviations (the '80s):
    s = decade_abbr_re.sub("&#8217;", s)

    s = opening_single_quotes_regex.sub(r"\1&#8216;", s)
    s = closing_single_quotes_regex.sub(r"\1&#8217;", s)
    s = closing_single_quotes_regex_2.sub(r"\1&#8217;\2", s)

    # Any remaining single quotes should be opening ones:
    s = s.replace("'", "&#8216;")

    s = opening_double_quotes_regex.sub(r"\1&#8220;", s)
    s = closing_double_quotes_regex.sub(r"&#8221;", s)
    s = closing_double_quotes_regex_2.sub(r"\1&#8221;", s)

    # Any remaining quotes should be opening ones.
    return s.replace('"', "&#8220;")


def educate_quotes_latex(s, dquotes=("``", "''")):
    """
    Parameter:  String.

    Returns:    The string, with double quotes corrected to LaTeX quotes.

    Example input:  "Isn't this fun?"
    Example output: ``Isn't this fun?'';
    """

    # Special case if the very first character is a quote
    # followed by punctuation at a non-word-break. Close the quotes
    # by brute force:
    s = single_quote_start_re.sub("\x04", s)
    s = double_quote_start_re.sub("\x02", s)

    # Special case for double sets of quotes, e.g.:
    #   <p>He said, "'Quoted' words in a larger quote."</p>
    s = double_quote_sets_re.sub("\x01\x03", s)
    s = single_quote_sets_re.sub("\x03\x01", s)

    # Special case for decade abbreviations (the '80s):
    s = decade_abbr_re.sub("\x04", s)

    s = opening_single_quotes_regex.sub("\\1\x03", s)
    s = closing_single_quotes_regex.sub("\\1\x04", s)
    s = closing_single_quotes_regex_2.sub("\\1\x04\\2", s)

    # Any remaining single quotes should be opening ones:
    s = s.replace("'", "\x03")

    s = opening_double_quotes_regex.sub("\\1\x01", s)
    s = closing_double_quotes_regex.sub("\x02", s)
    s = closing_double_quotes_regex_2.sub("\\1\x02", s)

    # Any remaining quotes should be opening ones.
    s = s.replace('"', "\x01")

    # Finally, replace all helpers with quotes.
    return s.replace("\x01", dquotes[0]).replace("\x02", dquotes[1]).\
        replace("\x03", "`").replace("\x04", "'")


def educate_backticks(s):
    """
    Parameter:  String.
    Returns:    The string, with ``backticks'' -style double quotes
        translated into HTML curly quote entities.
    Example input:  ``Isn't this fun?''
    Example output: &#8220;Isn't this fun?&#8221;
    """
    return s.replace("``", "&#8220;").replace("''", "&#8221;")


def educate_single_backticks(s):
    """
    Parameter:  String.
    Returns:    The string, with `backticks' -style single quotes
        translated into HTML curly quote entities.

    Example input:  `Isn't this fun?'
    Example output: &#8216;Isn&#8217;t this fun?&#8217;
    """
    return s.replace('`', "&#8216;").replace("'", "&#8217;")


def educate_dashes_oldschool(s):
    """
    Parameter:  String.

    Returns:    The string, with each instance of "--" translated to
        an en-dash HTML entity, and each "---" translated to
        an em-dash HTML entity.
    """
    return s.replace('---', "&#8212;").replace('--', "&#8211;")


def educate_dashes_oldschool_inverted(s):
    """
    Parameter:  String.

    Returns:    The string, with each instance of "--" translated to
        an em-dash HTML entity, and each "---" translated to
        an en-dash HTML entity. Two reasons why: First, unlike the
        en- and em-dash syntax supported by
        educate_dashes_oldschool(), it's compatible with existing
        entries written before SmartyPants 1.1, back when "--" was
        only used for em-dashes.  Second, em-dashes are more
        common than en-dashes, and so it sort of makes sense that
        the shortcut should be shorter to type. (Thanks to Aaron
        Swartz for the idea.)
    """
    return s.replace('---', "&#8211;").replace('--', "&#8212;")


def educate_ellipses(s):
    """
    Parameter:  String.
    Returns:    The string, with each instance of "..." translated to
        an ellipsis HTML entity.

    Example input:  Huh...?
    Example output: Huh&#8230;?
    """
    return s.replace('...', "&#8230;").replace('. . .', "&#8230;")
