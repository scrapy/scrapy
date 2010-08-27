import threading

from twisted.internet import threads
from boto.sqs.connection import SQSConnection
from boto.sqs import regions

from scrapy.queue import ExecutionQueue
from scrapy.utils.py26 import json
from scrapy.conf import settings

class SQSExecutionQueue(ExecutionQueue):

    polling_delay = settings.getint('SQS_POLLING_DELAY')
    queue_name = settings['SQS_QUEUE']
    region_name = settings['SQS_REGION']
    visibility_timeout = settings.getint('SQS_VISIBILITY_TIMEOUT')
    aws_access_key_id = settings['AWS_ACCESS_KEY_ID']
    aws_secret_access_key = settings['AWS_SECRET_ACCESS_KEY']

    def __init__(self, *a, **kw):
        super(SQSExecutionQueue, self).__init__(*a, **kw)
        self.region = self._get_region()
        self._tls = threading.local()

    def _append_next(self):
        return threads.deferToThread(self._append_next_from_sqs)

    def _append_next_from_sqs(self):
        q = self._get_sqs_queue()
        msgs = q.get_messages(1, visibility_timeout=self.visibility_timeout)
        if msgs:
            msg = msgs[0]
            msg.delete()
            spargs = json.loads(msg.get_body())
            spname = spargs.pop('name')
            self.append_spider_name(spname, **spargs)

    def _get_sqs_queue(self):
        if not hasattr(self._tls, 'queue'):
            c = SQSConnection(self.aws_access_key_id, self.aws_secret_access_key, \
                region=self.region)
            self._tls.queue = c.create_queue(self.queue_name)
        return self._tls.queue

    def _get_region(self, name=region_name):
        return [r for r in regions() if r.name == name][0]

    def is_finished(self):
        return False
