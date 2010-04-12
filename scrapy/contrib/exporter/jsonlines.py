from scrapy.contrib.exporter import BaseItemExporter
from scrapy.utils.py26 import json

class JsonLinesItemExporter(BaseItemExporter):

    def __init__(self, file, **kwargs):
        self._configure(kwargs)
        self.file = file
        self.encoder = json.JSONEncoder(**kwargs)

    def export_item(self, item):
        itemdict = dict(self._get_serialized_fields(item))
        self.file.write(self.encoder.encode(itemdict) + '\n')
