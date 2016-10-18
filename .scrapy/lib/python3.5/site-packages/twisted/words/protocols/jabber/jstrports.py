# -*- test-case-name: twisted.words.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


""" A temporary placeholder for client-capable strports, until we
sufficient use cases get identified """

from __future__ import absolute_import, division

from twisted.internet.endpoints import _parse

def _parseTCPSSL(factory, domain, port):
    """ For the moment, parse TCP or SSL connections the same """
    return (domain, int(port), factory), {}

def _parseUNIX(factory, address):
    return (address, factory), {}


_funcs = { "tcp"  : _parseTCPSSL,
           "unix" : _parseUNIX,
           "ssl"  : _parseTCPSSL }


def parse(description, factory):
    args, kw = _parse(description)
    return (args[0].upper(),) + _funcs[args[0]](factory, *args[1:], **kw)

def client(description, factory):
    from twisted.application import internet
    name, args, kw = parse(description, factory)
    return getattr(internet, name + 'Client')(*args, **kw)
