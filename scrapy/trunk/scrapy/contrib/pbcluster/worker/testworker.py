#!/usr/bin/python2.5

from twisted.spread import pb
from twisted.internet import reactor
from twisted.python import util
import sys

factory = pb.PBClientFactory()
reactor.connectTCP("localhost", 8789, factory)
d = factory.getRootObject()

sys.argv.pop(0)

if not sys.argv:
    d.addCallback(lambda object: object.callRemote("status"))
elif sys.argv[0] == "-s":
    d.addCallback(lambda object: object.callRemote("stop", sys.argv[1]))
elif sys.argv[0] == "-r":
    d.addCallback(lambda object: object.callRemote("run", sys.argv[1]))

d.addCallbacks(callback = util.println, errback = lambda reason: 'error: '+str(reason.value))
d.addCallback(lambda _: reactor.stop())
reactor.run()
