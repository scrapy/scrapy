#!/usr/bin/env python
"""Scrapy admin script is used to create new scrapy projects and similar
tasks"""
import os
import string
from optparse import OptionParser

import scrapy
from scrapy.utils.misc import render_templatefile, string_camelcase
from scrapy.utils.misc import ignore_patterns, copytree

usage = """
scrapy-admin.py [options] [command]
 
Available commands:
     
    startproject <project_name>
      Starts a new project with name 'project_name'
"""

PROJECT_TEMPLATES_PATH = os.path.join(scrapy.__path__[0], 'templates/project')

# This is the list of templatefile's path that are rendered *after copying* to
# project directory.
TEMPLATES = (
        'scrapy-ctl.py',
        '${project_name}/settings.py',
        '${project_name}/items.py',
        '${project_name}/pipelines.py',
        )

IGNORE = ignore_patterns('*.pyc', '.svn')

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
            project_root_path = project_name
            project_module_path = '%s/%s' % (project_name, project_name)

            roottpl = os.path.join(PROJECT_TEMPLATES_PATH, 'root')
            copytree(roottpl, project_name, ignore=IGNORE)

            moduletpl = os.path.join(PROJECT_TEMPLATES_PATH, 'module')
            copytree(moduletpl, '%s/%s' % (project_name, project_name),
                     ignore=IGNORE)

            for path in TEMPLATES:
                tplfile = os.path.join(project_root_path,
                        string.Template(path).substitute(project_name=project_name))
                render_templatefile(tplfile, project_name=project_name,
                        ProjectName=string_camelcase(project_name))
        else:
            print "scrapy-admin.py: missing project name"
    else:
        print "scrapy-admin.py: unknown command: %s" % cmd

if __name__ == '__main__':
    main()
