# Scrapy service configuration

# Directory where logs will be stored (one per crawler)
LOG_DIR = '/var/log/scrapy'

# A dict containing the Scrapy projects that will be run by this service
# * Keys are paths to project settings modules
# * Values are number of processes that should be started for each project, or
#   zero if you want to use the number of cores available.
PROJECTS = {
#    'mybot.settings': 0,
}

