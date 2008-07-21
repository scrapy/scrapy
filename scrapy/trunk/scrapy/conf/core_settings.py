import scrapy
# Scrapy core settings

BOT_NAME = 'scrapy'
BOT_VERSION = scrapy.__version__

ENGINE_DEBUG = False

# Download configuration options
USER_AGENT = '%s/%s' % (BOT_NAME, BOT_VERSION)
DOWNLOAD_TIMEOUT = 180      # 3mins
CONCURRENT_DOMAINS = 8    # number of domains to scrape in parallel
REQUESTS_PER_DOMAIN = 8     # max simultaneous requests per domain
CACHE2_EXPIRATION_SECS = 48 * 60 * 60 # seconds while cached response is still valid

LOG_ENABLED = True  #
LOGLEVEL = 'DEBUG'   # default loglevel
LOGFILE = None      # None means sys.stderr by default
LOG_STDOUT = False   #

DEFAULT_ITEM_CLASS = 'scrapy.item.ScrapedItem'
SCHEDULER = 'scrapy.core.scheduler.Scheduler'
MEMORYSTORE = 'scrapy.core.scheduler.MemoryStore'
PRIORITIZER = 'scrapy.core.prioritizers.RandomPrioritizer'

EXTENSIONS = []

# contrib.middleware.retry.RetryMiddleware default settings
RETRY_TIMES = 3
RETRY_HTTP_CODES = ['500', '503', '504', '400', '408', '200']
