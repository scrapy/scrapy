#!/usr/bin/env python
"""Scrapy admin script"""

import os, stat
from optparse import OptionParser

import scrapy

usage = """
Usage: scrapy-admin.py [options] [command]
 
Available commands:
     
    startproject <project_name>
      Starts a new project with name 'project_name'
"""

def main():
    parser = OptionParser(usage = usage)
    opts, args = parser.parse_args()
    
    if args:
        if args[0] == "startproject":
            
            try:
                project_name = args[1]
            except IndexError:
                parser.print_help()
            else:
                os.mkdir(project_name)
                os.mknod(os.path.join(project_name, "__init__.py"))
                
                for subdir in ["spiders", "conf", os.path.join("conf", "sites"), "commands", "templates"]:
                    os.mkdir(os.path.join(project_name, subdir))
                    os.mknod(os.path.join(project_name, subdir, "__init__.py"))
                
                settings_template = open(os.path.join(scrapy.__path__[0], "templates", "settings.tmpl"), "r").read()
                settings = settings_template.replace("__project_name__", project_name)
                open(os.path.join(project_name, "conf", "scrapy_settings.py"), "w").write(settings)
                
                control_template = open(os.path.join(scrapy.__path__[0], "templates", "scrapy-ctl.tmpl"), "r").read()
                control = control_template.replace("__project_name__", project_name)
                open(os.path.join(project_name, "scrapy-ctl.py"), "w").write(control)
                os.chmod(os.path.join(project_name, "scrapy-ctl.py"), stat.S_IRWXU)
                
            return
    parser.print_help()

if __name__ == '__main__':
    main()