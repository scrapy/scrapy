from scrapy.core.queue import ExecutionQueue
from scrapy.utils.sqlite import JsonSqlitePriorityQueue
from scrapy.conf import settings

class SqliteExecutionQueue(ExecutionQueue):

    queue_class = JsonSqlitePriorityQueue

    def __init__(self, *a, **kw):
        super(SqliteExecutionQueue, self).__init__(*a, **kw)
        self.queue = JsonSqlitePriorityQueue(settings['SQLITE_DB'])

    def _append_next(self):
        msg = self.queue.pop()
        if msg:
            name = msg.pop('name')
            self.append_spider_name(name, **msg)

    def is_finished(self):
        return False
