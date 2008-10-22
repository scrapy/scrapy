"""
Extensions to override scrapy settings with per-group settings according to the
group the spider belongs to. It only overrides the settings when running the
crawl command with *only one domain as argument*.
"""

from scrapy.conf import settings
from scrapy.core.exceptions import NotConfigured
from scrapy.command.cmdline import command_executed

class GroupSettings(object):

    def __init__(self):
        if not settings.getbool("GROUPSETTINGS_ENABLED"):
            raise NotConfigured

        if command_executed and command_executed['name'] == 'crawl':
            mod = __import__(settings['GROUPSETTINGS_MODULE'], {}, {}, [''])
            args = command_executed['args']
            if len(args) == 1 and not args[0].startswith('http://'):
                domain = args[0]
                settings.overrides.update(mod.default_settings)
                for group, domains in mod.group_spiders.iteritems():
                    if domain in domains:
                        settings.overrides.update(mod.group_settings.get(group, {}))
        
