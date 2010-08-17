import warnings
warnings.warn("File export pipeline is deprecated and will be removed in Scrapy 0.11, use Feed exports instead", \
    DeprecationWarning, stacklevel=2)

from scrapy.xlib.pydispatch import dispatcher
from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.contrib import exporter
from scrapy.conf import settings

class FileExportPipeline(object):

    def __init__(self):
        self.exporter, self.file = self.get_exporter_and_file()
        self.exporter.start_exporting()
        dispatcher.connect(self.engine_stopped, signals.engine_stopped)

    def process_item(self, item, spider):
        self.exporter.export_item(item)
        return item

    def engine_stopped(self):
        self.exporter.finish_exporting()
        self.file.close()

    def get_exporter_and_file(self):
        format = settings['EXPORT_FORMAT']
        filename = settings['EXPORT_FILE']
        if not format or not filename:
            raise NotConfigured
        exp_kwargs = {
            'fields_to_export': settings.getlist('EXPORT_FIELDS') or None,
            'export_empty_fields': settings.getbool('EXPORT_EMPTY', False),
            'encoding': settings.get('EXPORT_ENCODING', 'utf-8'),
        }
        file = open(filename, 'wb')
        if format == 'xml':
            exp = exporter.XmlItemExporter(file, **exp_kwargs)
        elif format == 'csv':
            exp = exporter.CsvItemExporter(file, **exp_kwargs)
        elif format == 'csv_headers':
            exp = exporter.CsvItemExporter(file, include_headers_line=True, \
                **exp_kwargs)
        elif format == 'pprint':
            exp = exporter.PprintItemExporter(file, **exp_kwargs)
        elif format == 'pickle':
            exp = exporter.PickleItemExporter(file, **exp_kwargs)
        elif format == 'json':
            exp = exporter.JsonLinesItemExporter(file, **exp_kwargs)
        elif format == 'jsonlines':
            exp = exporter.JsonItemExporter(file, **exp_kwargs)
        else:
            raise NotConfigured("Unsupported export format: %s" % format)
        return exp, file
