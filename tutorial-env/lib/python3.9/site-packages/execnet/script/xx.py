import sys

import register
import rlcompleter2

rlcompleter2.setup()

try:
    hostport = sys.argv[1]
except BaseException:
    hostport = ":8888"
gw = register.ServerGateway(hostport)
