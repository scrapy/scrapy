
import pytest
from twisted.python import log


class LogObservers:
    """Class for keeping track of log observers across test modules"""

    def __init__(self):
        self.observers = []

    def add(self, logfile='test.log'):
        fileobj = file(logfile, 'w')
        observer = log.FileLogObserver(fileobj)
        log.startLoggingWithObserver(observer.emit, 0)
        self.observers.append((fileobj, observer))

    def remove(self):
        fileobj, observer = self.observers.pop()
        log.removeObserver(observer.emit)
        fileobj.close()


@pytest.fixture(scope='module')
def log_observers():
    return LogObservers()


@pytest.fixture()
def setlog(request, log_observers):
    """Attach test.log file observer to twisted log, for trial compatibility"""
    log_observers.add()
    request.addfinalizer(log_observers.remove)


@pytest.fixture()
def chdir(tmpdir):
    """Change to pytest-provided temporary directory"""
    tmpdir.chdir()
