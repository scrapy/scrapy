from scrapy.xlib.pydispatch import dispatcher
from scrapy.utils import signal

class SignalManager(object):

    def __init__(self, sender=dispatcher.Anonymous):
        self.sender = sender

    def connect(self, *a, **kw):
        kw.setdefault('sender', self.sender)
        return dispatcher.connect(*a, **kw)

    def disconnect(self, *a, **kw):
        kw.setdefault('sender', self.sender)
        return dispatcher.disconnect(*a, **kw)

    def send_catch_log(self, *a, **kw):
        kw.setdefault('sender', self.sender)
        return signal.send_catch_log(*a, **kw)

    def send_catch_log_deferred(self, *a, **kw):
        kw.setdefault('sender', self.sender)
        return signal.send_catch_log_deferred(*a, **kw)

    def disconnect_all(self, *a, **kw):
        kw.setdefault('sender', self.sender)
        return signal.disconnect_all(*a, **kw)
