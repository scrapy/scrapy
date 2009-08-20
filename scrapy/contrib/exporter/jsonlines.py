from scrapy.contrib.exporter import BaseItemExporter

try:
    import json
except ImportError:
    import simplejson as json

class JsonLinesItemExporter(BaseItemExporter):

    def __init__(self, file, *args, **kwargs):
        super(JsonLinesItemExporter, self).__init__()
        self.file = file
        self.encoder = json.JSONEncoder(*args, **kwargs)

    def export_item(self, item):
        itemdict = {}
        for field, value in self._get_fields_to_export(item):
            itemdict[field] = self.serialize(item.fields[field], field, value)
        self.file.write(self.encoder.encode(itemdict) + '\n')
