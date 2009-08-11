from scrapy.newitem.exporters import BaseItemExporter
from scrapy.utils.serialization import serialize


class JSONItemExporter(BaseItemExporter):

    def __init__(self, file):
        super(BaseItemExporter, self).__init__()
        self.file = file

    def export(self, item):
        self.file.write(serialize(dict(item), 'json') + '\n')

