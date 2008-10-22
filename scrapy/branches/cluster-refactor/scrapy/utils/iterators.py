import csv

from scrapy.http import Response
from scrapy import log

def csv_iter(response, delimiter=None, headers=None):
    if delimiter:
        csv_r = csv.reader(response.body.to_unicode().split('\n'), delimiter=delimiter)
    else:
        csv_r = csv.reader(response.body.to_unicode().split('\n'))

    if not headers:
        headers = csv_r.next()

    while True:
        node = csv_r.next()

        if len(node) != len(headers):
            log.msg("ignoring node %d (length: %d, should be: %d)" % (csv_r.line_num, len(node), len(headers)), log.WARNING)
            continue

        yield dict(zip(headers, node))

