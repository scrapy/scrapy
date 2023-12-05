from textwrap import dedent
from unittest import TestCase

from testfixtures.mock import Mock
from sybil.document import Document

from testfixtures import compare, Comparison as C, TempDirectory
from testfixtures.sybil import FileParser, FileBlock


class TestFileParser(TestCase):

    def check_document(self, text, expected):
        d = Document(dedent(text), path='/dev/null')
        compare(
            list(r.parsed for r in FileParser('td')(d)),
            expected=expected
        )

    def test_multiple_files(self):
        self.check_document(
            text="""
            
            .. topic:: file.txt
             :class: write-file
            
              line 1
            
              line 2
              line 3
            
            .. topic:: file2.txt
             :class: read-file
            
            
              line 4
            
              line 5
              line 6
            
            """,
            expected = [
                C(FileBlock,
                  path='file.txt',
                  content="line 1\n\nline 2\nline 3\n",
                  action='write'),
                C(FileBlock,
                  path='file2.txt',
                  content='line 4\n\nline 5\nline 6\n',
                  action='read'),
            ])

    def test_ignore_literal_blocking(self):
        self.check_document(
            text="""
            .. topic:: file.txt
             :class: write-file
            
              ::
            
                line 1
            
                line 2
                line 3
            """,
            expected=[
                C(FileBlock,
                  path='file.txt',
                  content="line 1\n\nline 2\nline 3\n",
                  action='write'),
            ])

    def test_file_followed_by_text(self):
        self.check_document(
            text="""
            
            .. topic:: file.txt
             :class: write-file
            
              print("hello")
              out = 'there'
            
              foo = 'bar'
            
            This is just some normal text!
            """,
            expected=[
                C(FileBlock,
                  path='file.txt',
                  content='print("hello")'
                          '\nout = \'there\'\n\nfoo = \'bar\'\n',
                  action='write'),
            ])

    def test_red_herring(self):
        self.check_document(
            text="""
            .. topic:: file.txt
             :class: not-a-file
            
              print "hello"
              out = 'there'
            
            """,
            expected=[]
        )

    def test_no_class(self):
        self.check_document(
            text="""
            .. topic:: file.txt
            
              print "hello"
              out = 'there'
            
                        """,
            expected=[]
        )

    def check_evaluate(self, dir, block, expected):
        parser = FileParser('td')
        compare(expected, actual=parser.evaluate(Mock(
            parsed=block,
            namespace={'td': dir},
            path='/the/file',
            line=42,
        )))

    def test_evaluate_read_same(self):
        with TempDirectory() as dir:
            dir.write('foo', b'content')
            self.check_evaluate(
                dir,
                FileBlock('foo', 'content', 'read'),
                expected=None
            )

    def test_evaluate_read_difference(self):
        with TempDirectory() as dir:
            dir.write('foo', b'actual')
            self.check_evaluate(
                dir,
                FileBlock('foo', 'expected', 'read'),
                expected=(
                    "--- File '/the/file', line 42:\n"
                    "+++ Reading from \"{}/foo\":\n"
                    "@@ -1 +1 @@\n"
                    "-expected\n"
                    "+actual"
                ).format(dir.path)
            )

    def test_evaluate_write(self):
        with TempDirectory() as dir:
            self.check_evaluate(
                dir,
                FileBlock('foo', 'content', 'write'),
                expected=None
            )
            dir.compare(['foo'])
            compare(dir.read('foo', 'ascii'), 'content')
