import re
from typing import Optional, Tuple
import unittest

from bpython.line import (
    LinePart,
    current_word,
    current_dict_key,
    current_dict,
    current_string,
    current_object,
    current_object_attribute,
    current_from_import_from,
    current_from_import_import,
    current_import,
    current_method_definition_name,
    current_single_word,
    current_expression_attribute,
    current_dotted_attribute,
)


def cursor(s):
    """'ab|c' -> (2, 'abc')"""
    cursor_offset = s.index("|")
    line = s[:cursor_offset] + s[cursor_offset + 1 :]
    return cursor_offset, line


def decode(s: str) -> Tuple[Tuple[int, str], Optional[LinePart]]:
    """'a<bd|c>d' -> ((3, 'abcd'), (1, 3, 'bdc'))"""

    if not s.count("|") == 1:
        raise ValueError("match helper needs | to occur once")
    if s.count("<") != s.count(">") or s.count("<") not in (0, 1):
        raise ValueError("match helper needs <, and > to occur just once")
    matches = list(re.finditer(r"[<>|]", s))
    assert len(matches) in [1, 3], [m.group() for m in matches]
    d = {}
    for i, m in enumerate(matches):
        d[m.group(0)] = m.start() - i
        s = s[: m.start() - i] + s[m.end() - i :]
    assert len(d) in [1, 3], "need all the parts just once! %r" % d

    if "<" in d:
        return (d["|"], s), LinePart(d["<"], d[">"], s[d["<"] : d[">"]])
    else:
        return (d["|"], s), None


def line_with_cursor(cursor_offset: int, line: str) -> str:
    return line[:cursor_offset] + "|" + line[cursor_offset:]


def encode(cursor_offset: int, line: str, result: Optional[LinePart]) -> str:
    """encode(3, 'abdcd', (1, 3, 'bdc')) -> a<bd|c>d'

    Written for prettier assert error messages
    """
    encoded_line = line_with_cursor(cursor_offset, line)
    if result is None:
        return encoded_line
    start = result.start
    end = result.stop
    value = result.word
    assert line[start:end] == value
    if start < cursor_offset:
        encoded_line = encoded_line[:start] + "<" + encoded_line[start:]
    else:
        encoded_line = (
            encoded_line[: start + 1] + "<" + encoded_line[start + 1 :]
        )
    if end < cursor_offset:
        encoded_line = encoded_line[: end + 1] + ">" + encoded_line[end + 1 :]
    else:
        encoded_line = encoded_line[: end + 2] + ">" + encoded_line[end + 2 :]
    return encoded_line


class LineTestCase(unittest.TestCase):
    def assertAccess(self, s):
        r"""Asserts that self.func matches as described
        by s, which uses a little language to describe matches:

        abcd<efg>hijklmnopqrstuvwx|yz
           /|\ /|\               /|\
            |   |                 |
         the function should   the current cursor position
         match this "efg"      is between the x and y
        """
        (cursor_offset, line), match = decode(s)
        result = self.func(cursor_offset, line)

        self.assertEqual(
            result,
            match,
            "%s(%r) result\n%r (%r) doesn't match expected\n%r (%r)"
            % (
                self.func.__name__,
                line_with_cursor(cursor_offset, line),
                encode(cursor_offset, line, result),
                result,
                s,
                match,
            ),
        )


class TestHelpers(LineTestCase):
    def test_I(self):
        self.assertEqual(cursor("asd|fgh"), (3, "asdfgh"))

    def test_decode(self):
        self.assertEqual(
            decode("a<bd|c>d"), ((3, "abdcd"), LinePart(1, 4, "bdc"))
        )
        self.assertEqual(
            decode("a|<bdc>d"), ((1, "abdcd"), LinePart(1, 4, "bdc"))
        )
        self.assertEqual(
            decode("a<bdc>d|"), ((5, "abdcd"), LinePart(1, 4, "bdc"))
        )

    def test_encode(self):
        self.assertEqual(encode(3, "abdcd", LinePart(1, 4, "bdc")), "a<bd|c>d")
        self.assertEqual(encode(1, "abdcd", LinePart(1, 4, "bdc")), "a|<bdc>d")
        self.assertEqual(encode(4, "abdcd", LinePart(1, 4, "bdc")), "a<bdc|>d")
        self.assertEqual(encode(5, "abdcd", LinePart(1, 4, "bdc")), "a<bdc>d|")

    def test_assert_access(self):
        def dumb_func(cursor_offset, line):
            return LinePart(0, 2, "ab")

        self.func = dumb_func
        self.assertAccess("<a|b>d")


class TestCurrentWord(LineTestCase):
    def setUp(self):
        self.func = current_word

    def test_simple(self):
        self.assertAccess("|")
        self.assertAccess("|asdf")
        self.assertAccess("<a|sdf>")
        self.assertAccess("<asdf|>")
        self.assertAccess("<asdfg|>")
        self.assertAccess("asdf + <asdfg|>")
        self.assertAccess("<asdfg|> + asdf")

    def test_inside(self):
        self.assertAccess("<asd|>")
        self.assertAccess("<asd|fg>")

    def test_dots(self):
        self.assertAccess("<Object.attr1|>")
        self.assertAccess("<Object.attr1.attr2|>")
        self.assertAccess("<Object.att|r1.attr2>")
        self.assertAccess("stuff[stuff] + {123: 456} + <Object.attr1.attr2|>")
        self.assertAccess("stuff[<asd|fg>]")
        self.assertAccess("stuff[asdf[<asd|fg>]")

    def test_non_dots(self):
        self.assertAccess("].asdf|")
        self.assertAccess(").asdf|")
        self.assertAccess("foo[0].asdf|")
        self.assertAccess("foo().asdf|")
        self.assertAccess("foo().|")
        self.assertAccess("foo().asdf.|")
        self.assertAccess("foo[0].asdf.|")

    def test_open_paren(self):
        self.assertAccess("<foo(|>")
        # documenting current behavior - TODO is this intended?


class TestCurrentDictKey(LineTestCase):
    def setUp(self):
        self.func = current_dict_key

    def test_simple(self):
        self.assertAccess("asdf|")
        self.assertAccess("asdf|")
        self.assertAccess("asdf[<>|")
        self.assertAccess("asdf[<>|]")
        self.assertAccess("object.dict[<abc|>")
        self.assertAccess("asdf|")
        self.assertAccess("asdf[<(>|]")
        self.assertAccess("asdf[<(1>|]")
        self.assertAccess("asdf[<(1,>|]")
        self.assertAccess("asdf[<(1,)>|]")
        self.assertAccess("asdf[<(1, >|]")
        self.assertAccess("asdf[<(1, 2)>|]")
        # TODO self.assertAccess('d[d[<12|>')
        self.assertAccess("d[<'a>|")
        self.assertAccess("object.dict['a'bcd'], object.dict[<'abc>|")
        self.assertAccess("object.dict[<'a'bcd'>|], object.dict['abc")
        self.assertAccess(r"object.dict[<'a\'\\\"\n\\'>|")
        self.assertAccess("object.dict[<\"abc'>|")
        self.assertAccess("object.dict[<(1, 'apple', 2.134>|]")
        self.assertAccess("object.dict[<(1, 'apple', 2.134)>|]")
        self.assertAccess("object.dict[<-1000>|")
        self.assertAccess("object.dict[<-0.23948>|")
        self.assertAccess("object.dict[<'\U0001ffff>|")
        self.assertAccess(r"object.dict[<'a\'\\\"\n\\'>|]")
        self.assertAccess(r"object.dict[<'a\'\\\"\n\\|[[]'>")
        self.assertAccess('object.dict[<"a]bc[|]">]')
        self.assertAccess("object.dict[<'abcd[]>|")


class TestCurrentDict(LineTestCase):
    def setUp(self):
        self.func = current_dict

    def test_simple(self):
        self.assertAccess("asdf|")
        self.assertAccess("asdf|")
        self.assertAccess("<asdf>[|")
        self.assertAccess("<asdf>[|]")
        self.assertAccess("<object.dict>[abc|")
        self.assertAccess("asdf|")


class TestCurrentString(LineTestCase):
    def setUp(self):
        self.func = current_string

    def test_closed(self):
        self.assertAccess('"<as|df>"')
        self.assertAccess('"<asdf|>"')
        self.assertAccess('"<|asdf>"')
        self.assertAccess("'<asdf|>'")
        self.assertAccess("'<|asdf>'")
        self.assertAccess("'''<asdf|>'''")
        self.assertAccess('"""<asdf|>"""')
        self.assertAccess('asdf.afd("a") + "<asdf|>"')

    def test_open(self):
        self.assertAccess('"<as|df>')
        self.assertAccess('"<asdf|>')
        self.assertAccess('"<|asdf>')
        self.assertAccess("'<asdf|>")
        self.assertAccess("'<|asdf>")
        self.assertAccess("'''<asdf|>")
        self.assertAccess('"""<asdf|>')
        self.assertAccess('asdf.afd("a") + "<asdf|>')


class TestCurrentObject(LineTestCase):
    def setUp(self):
        self.func = current_object

    def test_simple(self):
        self.assertAccess("<Object>.attr1|")
        self.assertAccess("<Object>.|")
        self.assertAccess("Object|")
        self.assertAccess("Object|.")
        self.assertAccess("<Object>.|")
        self.assertAccess("<Object.attr1>.attr2|")
        self.assertAccess("<Object>.att|r1.attr2")
        self.assertAccess("stuff[stuff] + {123: 456} + <Object.attr1>.attr2|")
        self.assertAccess("stuff[asd|fg]")
        self.assertAccess("stuff[asdf[asd|fg]")


class TestCurrentAttribute(LineTestCase):
    def setUp(self):
        self.func = current_object_attribute

    def test_simple(self):
        self.assertAccess("Object.<attr1|>")
        self.assertAccess("Object.attr1.<attr2|>")
        self.assertAccess("Object.<att|r1>.attr2")
        self.assertAccess("stuff[stuff] + {123: 456} + Object.attr1.<attr2|>")
        self.assertAccess("stuff[asd|fg]")
        self.assertAccess("stuff[asdf[asd|fg]")
        self.assertAccess("Object.attr1.<|attr2>")
        self.assertAccess("Object.<attr1|>.attr2")


class TestCurrentFromImportFrom(LineTestCase):
    def setUp(self):
        self.func = current_from_import_from

    def test_simple(self):
        self.assertAccess("from <sys|> import path")
        self.assertAccess("from <sys> import path|")
        self.assertAccess("if True|: from sys import path")
        self.assertAccess("if True: |from sys import path")
        self.assertAccess("if True: from <sys> import p|ath")
        self.assertAccess("if True: from sys imp|ort path")
        self.assertAccess("if True: from sys import |path")
        self.assertAccess("if True: from sys import path.stu|ff")
        self.assertAccess("if True: from <sys.path> import sep|")
        self.assertAccess("from <os.p|>")


class TestCurrentFromImportImport(LineTestCase):
    def setUp(self):
        self.func = current_from_import_import

    def test_simple(self):
        self.assertAccess("from sys import <path|>")
        self.assertAccess("from sys import <p|ath>")
        self.assertAccess("from sys import |path")
        self.assertAccess("from sys| import path")
        self.assertAccess("from s|ys import path")
        self.assertAccess("from |sys import path")
        self.assertAccess("from xml.dom import <N|ode>")
        # because syntax error
        self.assertAccess("from xml.dom import Node.as|d")


class TestCurrentImport(LineTestCase):
    def setUp(self):
        self.func = current_import

    def test_simple(self):
        self.assertAccess("import <path|>")
        self.assertAccess("import <p|ath>")
        self.assertAccess("import |path")
        self.assertAccess("import path, <another|>")
        self.assertAccess("import path another|")
        self.assertAccess("if True: import <path|>")
        self.assertAccess("if True: import <xml.dom.minidom|>")
        self.assertAccess("if True: import <xml.do|m.minidom>")
        self.assertAccess("if True: import <xml.do|m.minidom> as something")


class TestMethodDefinitionName(LineTestCase):
    def setUp(self):
        self.func = current_method_definition_name

    def test_simple(self):
        self.assertAccess("def <foo|>")
        self.assertAccess("    def bar(x, y)|:")
        self.assertAccess("    def <bar|>(x, y)")


class TestSingleWord(LineTestCase):
    def setUp(self):
        self.func = current_single_word

    def test_simple(self):
        self.assertAccess("foo.bar|")
        self.assertAccess(".foo|")
        self.assertAccess(" <foo|>")


class TestCurrentExpressionAttribute(LineTestCase):
    def setUp(self):
        self.func = current_expression_attribute

    def test_simple(self):
        self.assertAccess("Object.<attr1|>.")
        self.assertAccess("Object.<|attr1>.")
        self.assertAccess("Object.(|)")
        self.assertAccess("Object.another.(|)")
        self.assertAccess("asdf asdf asdf.(abc|)")

    def test_without_dot(self):
        self.assertAccess("Object|")
        self.assertAccess("Object|.")
        self.assertAccess("|Object.")

    def test_with_whitespace(self):
        self.assertAccess("Object. <attr|>")
        self.assertAccess("Object .<attr|>")
        self.assertAccess("Object . <attr|>")
        self.assertAccess("Object .asdf attr|")
        self.assertAccess("Object .<asdf|> attr")
        self.assertAccess("Object. asdf attr|")
        self.assertAccess("Object. <asdf|> attr")
        self.assertAccess("Object . asdf attr|")
        self.assertAccess("Object . <asdf|> attr")

    def test_indexing(self):
        self.assertAccess("abc[def].<ghi|>")
        self.assertAccess("abc[def].<|ghi>")
        self.assertAccess("abc[def].<gh|i>")
        self.assertAccess("abc[def].gh |i")
        self.assertAccess("abc[def]|")

    def test_strings(self):
        self.assertAccess('"hey".<a|>')
        self.assertAccess('"hey"|')
        self.assertAccess('"hey"|.a')
        self.assertAccess('"hey".<a|b>')
        self.assertAccess('"hey".asdf d|')
        self.assertAccess('"hey".<|>')


class TestCurrentDottedAttribute(LineTestCase):
    def setUp(self):
        self.func = current_dotted_attribute

    def test_simple(self):
        self.assertAccess("<obj.attr>|")
        self.assertAccess("(<obj.attr>|")
        self.assertAccess("[<obj.attr>|")
        self.assertAccess("m.body[0].value|")
        self.assertAccess("m.body[0].attr.value|")


if __name__ == "__main__":
    unittest.main()
