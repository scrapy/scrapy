#!/usr/bin/env python
"""Scrapy admin script is used to create new scrapy projects and similar
tasks"""
import os
import shutil
from optparse import OptionParser

import scrapy
from scrapy.utils.misc import render_templatefile

usage = """
scrapy-admin.py [options] [command]
 
Available commands:
     
    startproject <project_name>
      Starts a new project with name 'project_name'
"""

TEMPLATES = (
        'scrapy_settings.py',
        )

def main():
    parser = OptionParser(usage=usage)
    opts, args = parser.parse_args()
    
    if not args:
        parser.print_help()
        return

    cmd = args[0]
    if cmd == "startproject":
        if len(args) >= 2:
            project_name = args[1]
            project_tplpath = os.path.join(scrapy.__path__[0], "conf", "project_template")
            shutil.copytree(project_tplpath, project_name)
            for path in TEMPLATES:
                render_templatefile(os.path.join(project_name, path), project_name=project_name)
        else:
            print "scrapy-admin.py: missing project name"
    else:
        print "scrapy-admin.py: unknown command: %s" % cmd

if __name__ == '__main__':
    main()
