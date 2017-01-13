# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

# 

"""
Parsing for the moduli file, which contains Diffie-Hellman prime groups.

Maintainer: Paul Swartz
"""

from twisted.python.compat import long


def parseModuliFile(filename):
    with open(filename) as f:
        lines = f.readlines()
    primes = {}
    for l in lines:
        l = l.strip()
        if  not l or l[0]=='#':
            continue
        tim, typ, tst, tri, size, gen, mod = l.split()
        size = int(size) + 1
        gen = long(gen)
        mod = long(mod, 16)
        if size not in primes:
            primes[size] = []
        primes[size].append((gen, mod))
    return primes
