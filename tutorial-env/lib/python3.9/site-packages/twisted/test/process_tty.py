"""Test to make sure we can open /dev/tty"""

with open("/dev/tty", "rb+", buffering=0) as f:
    a = f.readline()
    f.write(a)
