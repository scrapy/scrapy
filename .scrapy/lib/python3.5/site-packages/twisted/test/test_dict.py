
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


from twisted.trial import unittest
from twisted.protocols import dict

paramString = b"\"This is a dqstring \\w\\i\\t\\h boring stuff like: \\\"\" and t\\hes\\\"e are a\\to\\ms"
goodparams = [b"This is a dqstring with boring stuff like: \"", b"and", b"thes\"e", b"are", b"atoms"]

class ParamTests(unittest.TestCase):
    def testParseParam(self):
        """Testing command response handling"""
        params = []
        rest = paramString
        while 1:
            (param, rest) = dict.parseParam(rest)
            if param == None:
                break
            params.append(param)
        self.assertEqual(params, goodparams)#, "DictClient.parseParam returns unexpected results")
