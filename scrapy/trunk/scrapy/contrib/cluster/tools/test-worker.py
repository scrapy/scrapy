#!/usr/bin/python2.5

import sys
import pprint

from twisted.spread import pb
from twisted.internet import reactor

factory = pb.PBClientFactory()
reactor.connectTCP("localhost", 8789, factory)
d = factory.getRootObject()

sys.argv.pop(0)

if not sys.argv or sys.argv[0] == '--status':
    d.addCallback(lambda object: object.callRemote("status"))
elif sys.argv[0] == "--stop":
    d.addCallback(lambda object: object.callRemote("stop", sys.argv[1]))
elif sys.argv[0] == "--run":
    d.addCallback(lambda object: object.callRemote("run", sys.argv[1]))

d.addCallbacks(callback=pprint.pprint, errback=lambda reason:'error: ' + str(reason.value))
d.addCallback(lambda _: reactor.stop())
reactor.run()
