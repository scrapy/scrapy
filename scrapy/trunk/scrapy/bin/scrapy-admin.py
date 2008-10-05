#!/usr/bin/env python
"""Scrapy admin script is used to create new scrapy projects and similar
tasks"""

import os
import shutil
from optparse import OptionParser

import scrapy

usage = """
scrapy-admin.py [options] [command]
 
Available commands:
     
    startproject <project_name>
      Starts a new project with name 'project_name'
"""

def main():
    parser = OptionParser(usage=usage)
    opts, args = parser.parse_args()
    
    if not args:
        parser.print_help()

    cmd = args[0]
    if cmd == "startproject":
        if len(args) >= 2:
            project_name = args[1]
            project_tplpath = os.path.join(scrapy.__path__[0], "conf", "project_template")
            shutil.copytree(project_tplpath, project_name)
        else:
            print "scrapy-admin.py: missing project name"
    else:
        print "scrapy-admin.py: unknown command: %s" % cmd

if __name__ == '__main__':
    main()
