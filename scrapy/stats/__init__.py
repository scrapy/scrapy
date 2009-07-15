from scrapy.stats.collector import DummyStatsCollector
from scrapy.conf import settings
from scrapy.utils.misc import load_object

# if stats are disabled use a DummyStatsCollector to improve performance
if settings.getbool('STATS_ENABLED'):
    stats = load_object(settings['STATS_CLASS'])()
else:
    stats = DummyStatsCollector()
