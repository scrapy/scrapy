from scrapy.contrib.exporter import BaseItemExporter
from scrapy.utils.serialization import serialize


class JSONItemExporter(BaseItemExporter):

    def __init__(self, file):
        super(JSONItemExporter, self).__init__()
        self.file = file

    def export(self, item):
        self.file.write(serialize(dict(item), 'json') + '\n')

