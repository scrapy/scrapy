# -*- test-case-name: twisted.test.test_twistd -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
The Twisted Daemon: platform-independent interface.

@author: Christopher Armstrong
"""


from twisted.application import app
from twisted.python.runtime import platformType

if platformType == "win32":
    from twisted.scripts._twistw import (
        ServerOptions,
        WindowsApplicationRunner as _SomeApplicationRunner,
    )
else:
    from twisted.scripts._twistd_unix import (  # type: ignore[misc]
        ServerOptions,
        UnixApplicationRunner as _SomeApplicationRunner,
    )


def runApp(config):
    runner = _SomeApplicationRunner(config)
    runner.run()
    if runner._exitSignal is not None:
        app._exitWithSignal(runner._exitSignal)


def run():
    app.run(runApp, ServerOptions)


__all__ = ["run", "runApp"]
