# TODO: remove this module for Scrapy 0.10
import warnings

from scrapy import cmdline

def execute():
    warnings.warn("scrapy.command.cmdline.execute() is deprecated, modify your " \
        "project-ctl.py script to use scrapy.cmdline.execute() instead", \
        DeprecationWarning, stacklevel=2)
    cmdline.execute()
