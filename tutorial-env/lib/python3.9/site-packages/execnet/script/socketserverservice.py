"""
A windows service wrapper for the py.execnet socketserver.

To use, run:
 python socketserverservice.py register
 net start ExecNetSocketServer
"""
import socketserver
import sys
import threading

import servicemanager
import win32event
import win32evtlogutil
import win32service
import win32serviceutil


appname = "ExecNetSocketServer"


class SocketServerService(win32serviceutil.ServiceFramework):
    _svc_name_ = appname
    _svc_display_name_ = "%s" % appname
    _svc_deps_ = ["EventLog"]

    def __init__(self, args):
        # The exe-file has messages for the Event Log Viewer.
        # Register the exe-file as event source.
        #
        # Probably it would be better if this is done at installation time,
        # so that it also could be removed if the service is uninstalled.
        # Unfortunately it cannot be done in the 'if __name__ == "__main__"'
        # block below, because the 'frozen' exe-file does not run this code.
        #
        win32evtlogutil.AddSourceToRegistry(
            self._svc_display_name_, servicemanager.__file__, "Application"
        )
        super.__init__(args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.WAIT_TIME = 1000  # in milliseconds

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        # Redirect stdout and stderr to prevent "IOError: [Errno 9]
        # Bad file descriptor". Windows services don't have functional
        # output streams.
        sys.stdout = sys.stderr = open("nul", "w")

        # Write a 'started' event to the event log...
        win32evtlogutil.ReportEvent(
            self._svc_display_name_,
            servicemanager.PYS_SERVICE_STARTED,
            0,  # category
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            (self._svc_name_, ""),
        )
        print("Begin: %s" % self._svc_display_name_)

        hostport = ":8888"
        print("Starting py.execnet SocketServer on %s" % hostport)
        serversock = socketserver.bind_and_listen(hostport)
        thread = threading.Thread(
            target=socketserver.startserver, args=(serversock,), kwargs={"loop": True}
        )
        thread.setDaemon(True)
        thread.start()

        # wait to be stopped or self.WAIT_TIME to pass
        while True:
            result = win32event.WaitForSingleObject(self.hWaitStop, self.WAIT_TIME)
            if result == win32event.WAIT_OBJECT_0:
                break

        # write a 'stopped' event to the event log.
        win32evtlogutil.ReportEvent(
            self._svc_display_name_,
            servicemanager.PYS_SERVICE_STOPPED,
            0,  # category
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            (self._svc_name_, ""),
        )
        print("End: %s" % appname)


if __name__ == "__main__":
    # Note that this code will not be run in the 'frozen' exe-file!!!
    win32serviceutil.HandleCommandLine(SocketServerService)
