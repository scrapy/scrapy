# -*- coding: utf8 -*-
from datetime import datetime
from pydispatch import dispatcher
from scrapy.core import signals

class Report(object):
    def __init__(self, dropped):
        self.domain = ''
        self.passed_file = None
        self.dropped_file = None
        self.dropped = dropped
        self.total = { 'passed': 0, 'dropped': 0 }

        dispatcher.connect(self.domain_open, signal=signals.domain_open)
        dispatcher.connect(self.item_passed, signal=signals.item_passed)
        dispatcher.connect(self.engine_stopped, signal=signals.engine_stopped)
        if self.dropped:
            dispatcher.connect(self.item_dropped, signal=signals.item_dropped)

    def get_product_text(self, product, dropped=False):
        product_text = ''
        for attrib, value in product.iteritems():
            product_text = '%s%s: %s\n' % (product_text, attrib, value)
        if dropped:
            product_text = '%sdropping reason: %s\n' % (product_text, dropped)
        product_text = product_text + '\n\n'
        return product_text

    def domain_open(self, domain, spider):
        self.domain = domain
        now = datetime.now()
        filename = '%s_%s_%s.report' % (self.domain, now.strftime('%Y%m%d'), now.strftime('%H%M'))
        self.passed_file = open(filename, 'w')
        self.passed_file.write('Scraping results for domain "%s"\n\n%s%s%s' % (self.domain, '##################################\n',
          '### Products scraped correctly ###\n', '##################################\n'))
        if self.dropped:
            self.dropped_file = open(filename + '.dropped', 'w')
            self.dropped_file.write('Scraping results for domain "%s"\n\n%s%s%s' % (self.domain,
              '########################\n', '### Dropped products ###\n', '########################\n'))

    def item_passed(self, item, spider):
        self.total['passed'] += 1
        self.passed_file.write(self.get_product_text(item))

    def item_dropped(self, item, spider, response, exception):
        self.total['dropped'] += 1
        self.dropped_file.write(self.get_product_text(item, exception))

    def engine_stopped(self):
        self.passed_file.write('\n--- Total scraped products: %d\n' % self.total['passed'])
        self.passed_file.close()
        if self.dropped:
            self.dropped_file.write('\n--- Total dropped products: %d\n' % self.total['dropped'])
            self.dropped_file.close()
