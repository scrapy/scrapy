# -*- test-case-name: twisted.test.test_twistd -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import print_function

from twisted.python import log
from twisted.application import app, service, internet
from twisted import copyright
import sys, os



class ServerOptions(app.ServerOptions):
    synopsis = "Usage: twistd [options]"

    optFlags = [['nodaemon','n',  "(for backwards compatibility)."],
                ]

    def opt_version(self):
        """Print version information and exit.
        """
        print('twistd (the Twisted Windows runner) %s' % copyright.version)
        print(copyright.copyright)
        sys.exit()



class WindowsApplicationRunner(app.ApplicationRunner):
    """
    An ApplicationRunner which avoids unix-specific things. No
    forking, no PID files, no privileges.
    """

    def preApplication(self):
        """
        Do pre-application-creation setup.
        """
        self.oldstdout = sys.stdout
        self.oldstderr = sys.stderr
        os.chdir(self.config['rundir'])


    def postApplication(self):
        """
        Start the application and run the reactor.
        """
        service.IService(self.application).privilegedStartService()
        app.startApplication(self.application, not self.config['no_save'])
        app.startApplication(internet.TimerService(0.1, lambda:None), 0)
        self.startReactor(None, self.oldstdout, self.oldstderr)
        log.msg("Server Shut Down.")
