import errno
import os
import pty
import re
import select
import subprocess
import sys
import tempfile
import unittest

from textwrap import dedent
from bpython import args
from bpython.config import getpreferredencoding
from bpython.test import FixLanguageTestCase as TestCase


def run_with_tty(command):
    # based on https://stackoverflow.com/questions/52954248/capture-output-as-a-tty-in-python
    master_stdout, slave_stdout = pty.openpty()
    master_stderr, slave_stderr = pty.openpty()
    master_stdin, slave_stdin = pty.openpty()

    p = subprocess.Popen(
        command,
        stdout=slave_stdout,
        stderr=slave_stderr,
        stdin=slave_stdin,
        close_fds=True,
    )
    for fd in (slave_stdout, slave_stderr, slave_stdin):
        os.close(fd)

    readable = [master_stdout, master_stderr]
    result = {master_stdout: b"", master_stderr: b""}
    try:
        while readable:
            ready, _, _ = select.select(readable, [], [], 1)
            for fd in ready:
                try:
                    data = os.read(fd, 512)
                except OSError as e:
                    if e.errno != errno.EIO:
                        raise
                    # EIO means EOF on some systems
                    readable.remove(fd)
                else:
                    if not data:  # EOF
                        readable.remove(fd)
                    result[fd] += data
    finally:
        for fd in (master_stdout, master_stderr, master_stdin):
            os.close(fd)
        if p.poll() is None:
            p.kill()
        p.wait()

    if p.returncode:
        raise RuntimeError(f"Subprocess exited with {p.returncode}")

    return (
        result[master_stdout].decode(getpreferredencoding()),
        result[master_stderr].decode(getpreferredencoding()),
    )


class TestExecArgs(unittest.TestCase):
    def test_exec_dunder_file(self):
        with tempfile.NamedTemporaryFile(mode="w") as f:
            f.write(
                dedent(
                    """\
                import sys
                sys.stderr.write(__file__)
                sys.stderr.flush()"""
                )
            )
            f.flush()
            _, stderr = run_with_tty(
                [sys.executable] + ["-m", "bpython.curtsies", f.name]
            )
            self.assertEqual(stderr.strip(), f.name)

    def test_exec_nonascii_file(self):
        with tempfile.NamedTemporaryFile(mode="w") as f:
            f.write(
                dedent(
                    """\
                # coding: utf-8
                "你好 # nonascii"
                """
                )
            )
            f.flush()
            _, stderr = run_with_tty(
                [sys.executable, "-m", "bpython.curtsies", f.name],
            )
            self.assertEqual(len(stderr), 0)

    def test_exec_nonascii_file_linenums(self):
        with tempfile.NamedTemporaryFile(mode="w") as f:
            f.write(
                dedent(
                    """\
                1/0
                """
                )
            )
            f.flush()
            _, stderr = run_with_tty(
                [sys.executable, "-m", "bpython.curtsies", f.name],
            )
            self.assertIn("line 1", clean_colors(stderr))


def clean_colors(s):
    return re.sub(r"\x1b[^m]*m", "", s)


class TestParse(TestCase):
    def test_version(self):
        with self.assertRaises(SystemExit):
            args.parse(["--version"])
