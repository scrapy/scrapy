
from __future__ import absolute_import
import signal

import asyncio
'''
from twisted.internet import asyncioreactor
try:
    asyncioreactor.install(asyncio.get_event_loop())
except Exception:
    pass
'''
from twisted.internet import reactor


signal_names = {}
for signame in dir(signal):
    if signame.startswith('SIG') and not signame.startswith('SIG_'):
        signum = getattr(signal, signame)
        if isinstance(signum, int):
            signal_names[signum] = signame


def install_shutdown_handlers(function, override_sigint=True):
    """Install the given function as a signal handler for all common shutdown
    signals (such as SIGINT, SIGTERM, etc). If override_sigint is ``False`` the
    SIGINT handler won't be install if there is already a handler in place
    (e.g.  Pdb)
    """
    reactor._handleSignals()
    signal.signal(signal.SIGTERM, function)
    if signal.getsignal(signal.SIGINT) == signal.default_int_handler or \
            override_sigint:
        signal.signal(signal.SIGINT, function)
    # Catch Ctrl-Break in windows
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, function)
