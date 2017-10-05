import logging
import sickle
from datetime import datetime

from sickle import Sickle
from sickle.models import Record

from scrapy.http import Request
from scrapy.spiders import Spider

logger = logging.getLogger(__name__)

class OAIPMHSpider(Spider):
    """
    Implements a spider for the OAI-PMH protocol by using the Python sickle library.

    In case of successful harvest (OAI-PMH crawling) the spider will remember the initial starting
    date and will use it as `from_date` argument on the next harvest.
    """
    name = 'OAI-PMH'
    state = {}

    def __init__(self, url, metadata_prefix='oai_dc', set=None, alias=None, from_date=None, until_date=None, granularity='YYYY-MM-DD', record_class=Record, *args, **kwargs):
        super(OAIPMHSpider, self).__init__(*args, **kwargs)
        self.url = url
        self.metadata_prefix = metadata_prefix
        self.set = set
        self.granularity = granularity
        self.alias = alias or self._make_alias()
        self.from_date = from_date or self.state.get(self.alias)
        self.until_date = until_date
        self.record_class = record_class

    def start_requests(self):
        logger.info("Starting harvesting of {url} with set={set} and metadataPrefix={metadata_prefix}, from={from_date}, until={until_date}".format(
            url=self.url,
            set=self.set,
            metadata_prefix=self.metadata_prefix,
            from_date=self.from_date,
            until_date=self.until_date
        ))
        now = datetime.utcnow()
        request = Request('oaipmh+{}'.format(self.url), self.parse)
        yield request
        self.state[self.alias] = self._format_date(now)
        logger.info("Harvesting completed. Next harvesting will resume from {}".format(self.state[self.alias]))

    def parse_record(self, record):
        """
        This method need to be reimplemented in order to provide special parsing.
        """
        return record.metadata

    def parse(self, response):
        sickle = Sickle(self.url, class_mapping={
            'ListRecords': self.record_class,
            'GetRecord': self.record_class,
        })
        records = sickle.ListRecords(**{
            'metadataPrefix': self.metadata_prefix,
            'set': self.set,
            'from': self.from_date,
            'until': self.until_date,
        })
        for record in records:
            yield self.parse_record(record)

    def _format_date(self, datetime_object):
        if self.granularity == 'YYYY-MM-DD':
            return datetime_object.strftime('%Y-%m-%d')
        elif self.granularity == 'YYYY-MM-DDThh:mm:ssZ':
            return datetime_object.strftime('%Y-%m-%dT%H:%M:%SZ')
        else:
            raise RuntimeError("Invalid granularity: %s" % self.granularity)

    def _make_alias(self):
        return '{url}-{metadata_prefix}-{set}'.format(
            url=self.url,
            metadata_prefix=self.metadata_prefix,
            set=self.set
        )
