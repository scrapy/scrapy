import logging
from scrapy.utils.log import configure_logging
from scrapy.settings import Settings

# Create Scrapy-style settings
settings = Settings()
settings.set('LOG_FORMAT', '%(levelname)s: %(message)s')
settings.set('LOG_LEVEL', 'DEBUG')
settings.set('LOG_STDOUT', False)

# Configure logging
configure_logging(settings)

logger = logging.getLogger(__name__)

# Test messages
logger.debug("Debug message - developer info.")
logger.info("Info message - system running fine.")
logger.warning("Warning message - possible issue.")
logger.error("Error message - something failed.")
logger.critical("Critical message - major failure.")
