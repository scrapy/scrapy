from zope.interface import implements

from twisted.internet import threads
from boto.sqs.connection import SQSConnection
from boto.sqs.message import Message
from boto.sqs import regions

from scrapy.interfaces import ISpiderQueue
from scrapy.utils.py26 import json

class SQSSpiderQueue(object):

    implements(ISpiderQueue)

    def __init__(self, *a, **kw):
        self.queue_name = kw.pop('queue_name', 'scrapy')
        self.region_name = kw.pop('region_name', 'us-east-1')
        self.visibility_timeout = kw.pop('visibility_timeout', 7200)
        self.aws_access_key_id = kw.pop('aws_access_key_id', None)
        self.aws_secret_access_key = kw.pop('aws_secret_access_key', None)
        self.region = self._get_region(self.region_name)
        self.conn.create_queue(self.queue_name)
        super(SQSSpiderQueue, self).__init__(*a, **kw)

    @classmethod
    def from_settings(cls, settings):
        return cls(
            queue_name=settings['SQS_QUEUE'],
            region_name=settings['SQS_REGION'],
            visibility_timeout=settings.getint('SQS_VISIBILITY_TIMEOUT'),
            aws_access_key_id=settings['AWS_ACCESS_KEY_ID'],
            aws_secret_access_key=settings['AWS_SECRET_ACCESS_KEY']
        )
        
    def _get_region(self, name):
        return [r for r in regions() if r.name == name][0]

    @property
    def conn(self):
        return SQSConnection(self.aws_access_key_id, self.aws_secret_access_key, \
            region=self.region)

    @property
    def queue(self):
        return self.conn.get_queue(self.queue_name)

    def _queue_method(self, method, *a, **kw):
        return getattr(self.queue, method)(*a, **kw)

    def pop(self):
        return threads.deferToThread(self._pop)

    def _pop(self):
        msgs = self.queue.get_messages(1, visibility_timeout=self.visibility_timeout)
        if msgs:
            msg = msgs[0]
            msg.delete()
            return json.loads(msg.get_body())

    def add(self, name, **spider_args):
        d = spider_args.copy()
        d['name'] = name
        msg = Message(body=json.dumps(d))
        return threads.deferToThread(self._queue_method, 'write', msg)

    def count(self):
        return threads.deferToThread(self._queue_method, 'count')

    def list(self):
        return threads.deferToThread(self._list)

    def _list(self):
        msgs = []
        m = self.queue.read(visibility_timeout=100)
        while m:
            msgs.append(json.loads(m.get_body()))
            m = self.queue.read(visibility_timeout=100)
        return msgs

    def clear(self):
        return threads.deferToThread(self._queue_method, 'clear')
