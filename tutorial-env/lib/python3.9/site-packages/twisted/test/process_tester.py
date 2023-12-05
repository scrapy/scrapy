"""Test program for processes."""

import os
import sys

test_file_match = "process_test.log.*"
test_file = "process_test.log.%d" % os.getpid()


def main():
    f = open(test_file, "wb")

    stdin = sys.stdin.buffer
    stderr = sys.stderr.buffer
    stdout = sys.stdout.buffer

    # stage 1
    b = stdin.read(4)
    f.write(b"one: " + b + b"\n")

    # stage 2
    stdout.write(b)
    stdout.flush()
    os.close(sys.stdout.fileno())

    # and a one, and a two, and a...
    b = stdin.read(4)
    f.write(b"two: " + b + b"\n")

    # stage 3
    stderr.write(b)
    stderr.flush()
    os.close(stderr.fileno())

    # stage 4
    b = stdin.read(4)
    f.write(b"three: " + b + b"\n")

    # exit with status code 23
    sys.exit(23)


if __name__ == "__main__":
    main()
