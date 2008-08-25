"""
SimpageMiddleware is a middleware for detecting similar page layouts
"""

import sys
import datetime
import pprint

from pydispatch import dispatcher

from scrapy.core import signals
from scrapy.http import Response
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings

from .metrics import tagdepth

class SimpagesMiddleware(object):
    
    metric = tagdepth
    threshold = 0.8

    def __init__(self):
        if not settings.getbool('SIMPAGES_ENABLED'):
            raise NotConfigured
        repfilename = settings.get('SIMPAGES_REPORT_FILE')
        self.reportfile = open(repfilename, "a") if repfilename else None
        self.sim_groups = {}
        self.last_group = 0
        dispatcher.connect(self.engine_stopped, signal=signals.engine_stopped)

    def process_response(self, request, response, spider):
        if isinstance(response, Response):
            group, simrate = self.get_similarity_group(response)
            if group:
                self.sim_groups[group]['similar_urls'].append((response.url, simrate))
            else:
                self.create_similarity_group(response)
        return response

    def get_similarity_group(self, response):
        sh = self.metric.simhash(response)
        for group, data in self.sim_groups.iteritems():
            simrate = self.metric.compare(sh, data['simhash'])
            if simrate > self.threshold:
                return (group, simrate)
        return (None, 0)

    def create_similarity_group(self, response):
        self.last_group += 1
        data = {}
        data['simhash'] = self.metric.simhash(response)
        data['first_url'] = response.url
        data['similar_urls'] = []
        self.sim_groups[self.last_group] = data

    def get_report(self):
        r =  "Page similarity results\n"
        r += "=======================\n\n"
        r += "Datetime : %s\n" % datetime.datetime.now()
        r += "Metric   : %s\n" % self.metric.__name__
        r += "Threshold: %s\n" % self.threshold
        r += "Results  :\n"
        r += pprint.pformat(self.sim_groups)
        r += "\n\n"
        return r

    def engine_stopped(self):
        rep = self.get_report()
        if self.reportfile:
            self.reportfile.write(rep)
        else:
            print rep
