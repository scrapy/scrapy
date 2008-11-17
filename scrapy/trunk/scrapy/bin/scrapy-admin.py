#!/usr/bin/env python
"""Scrapy admin script is used to create new scrapy projects and similar
tasks"""
from __future__ import with_statement

import os
import shutil
import string
from optparse import OptionParser

import scrapy

usage = """
scrapy-admin.py [options] [command]
 
Available commands:
     
    startproject <project_name>
      Starts a new project with name 'project_name'
"""

TEMPLATES = (
        'scrapy_settings.py',
        )

def render_templatefile(path, **kwargs):
    with open(path, 'rb') as file:
        raw = file.read()

    content = string.Template(raw).substitute(**kwargs)

    with open(path, 'wb') as file:
        file.write(content)


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
