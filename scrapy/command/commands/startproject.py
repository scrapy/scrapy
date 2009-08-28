#!/usr/bin/env python

import sys
import os
import string
import re

import scrapy
from scrapy.command import ScrapyCommand
from scrapy.utils.template import render_templatefile, string_camelcase
from scrapy.utils.python import ignore_patterns, copytree

PROJECT_TEMPLATES_PATH = os.path.join(scrapy.__path__[0], 'templates/project')

# This is the list of templatefile's path that are rendered *after copying* to
# the new project directory.
TEMPLATES = (
    ('scrapy-ctl.py',),
    ('${project_name}', 'settings.py.tmpl'),
    ('${project_name}', 'items.py.tmpl'),
    ('${project_name}', 'pipelines.py.tmpl'),
)

IGNORE = ignore_patterns('*.pyc', '.svn')

class Command(ScrapyCommand):

    requires_project = False

    def syntax(self):
        return "<project_name>"

    def short_desc(self):
        return "Create new project with an initial project template"

    def run(self, args, opts):
        if len(args) != 1:
            return False

        project_name = args[0]
        if not re.search(r'^[_a-zA-Z]\w*$', project_name): # If it's not a valid directory name.
            # Provide a smart error message, depending on the error.
            if not re.search(r'^[a-zA-Z]', project_name):
                message = 'Project names must begin with a letter'
            else:
                message = 'Project names must contain only letters, numbers and underscores'
            print "Invalid project name: %s\n\n%s" % (project_name, message)
            sys.exit(1)
        else:
            if os.path.exists(project_name):
                print "%s dir already exists" % project_name
                sys.exit(1)

            project_root_path = project_name

            roottpl = os.path.join(PROJECT_TEMPLATES_PATH, 'root')
            copytree(roottpl, project_name, ignore=IGNORE)

            moduletpl = os.path.join(PROJECT_TEMPLATES_PATH, 'module')
            copytree(moduletpl, '%s/%s' % (project_name, project_name),
                ignore=IGNORE)

            for paths in TEMPLATES:
                path = os.path.join(*paths)
                tplfile = os.path.join(project_root_path,
                    string.Template(path).substitute(project_name=project_name))
                render_templatefile(tplfile, project_name=project_name,
                    ProjectName=string_camelcase(project_name))
