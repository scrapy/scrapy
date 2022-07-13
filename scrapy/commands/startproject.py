import re
import os
import string
from importlib.util import find_spec
from os.path import join, exists, abspath
from shutil import ignore_patterns, move, copy2, copystat
from stat import S_IWUSR as OWNER_WRITE_PERMISSION

import scrapy
from scrapy.commands import ScrapyCommand
from scrapy.utils.template import render_templatefile, string_camelcase
from scrapy.exceptions import UsageError


TEMPLATES_TO_RENDER = (
    ('scrapy.cfg',),
    ('${project_name}', 'settings.py.tmpl'),
    ('${project_name}', 'items.py.tmpl'),
    ('${project_name}', 'pipelines.py.tmpl'),
    ('${project_name}', 'middlewares.py.tmpl'),
)

IGNORE = ignore_patterns('*.pyc', '__pycache__', '.svn')


def _make_writable(path):
    current_permissions = os.stat(path).st_mode
    os.chmod(path, current_permissions | OWNER_WRITE_PERMISSION)


class Command(ScrapyCommand):

    requires_project = False
    default_settings = {'LOG_ENABLED': False,
                        'SPIDER_LOADER_WARN_ONLY': True}

    def syntax(self):
        return "<project_name> [project_dir]"

    def short_desc(self):
        return "Create new project"

    def _is_valid_name(self, project_name):
        def _module_exists(module_name):
            spec = find_spec(module_name)
            return spec is not None and spec.loader is not None

        if not re.search(r'^[_a-zA-Z]\w*$', project_name):
            print('Error: Project names must begin with a letter and contain'
                  ' only\nletters, numbers and underscores')
        elif _module_exists(project_name):
            print(f'Error: Module {project_name!r} already exists')
        else:
            return True
        return False

    def _copytree(self, src, dst):
        """
        Since the original function always creates the directory, to resolve
        the issue a new function had to be created. It's a simple copy and
        was reduced for this case.

        More info at:
        https://github.com/scrapy/scrapy/pull/2005
        """
        ignore = IGNORE
        names = os.listdir(src)
        ignored_names = ignore(src, names)

        if not os.path.exists(dst):
            os.makedirs(dst)

        for name in names:
            if name in ignored_names:
                continue

            srcname = os.path.join(src, name)
            dstname = os.path.join(dst, name)
            if os.path.isdir(srcname):
                self._copytree(srcname, dstname)
            else:
                copy2(srcname, dstname)
                _make_writable(dstname)

        copystat(src, dst)
        _make_writable(dst)

    def run(self, args, opts):
        if len(args) not in (1, 2):
            raise UsageError()

        project_name = args[0]
        project_dir = args[0]

        if len(args) == 2:
            project_dir = args[1]

        if exists(join(project_dir, 'scrapy.cfg')):
            self.exitcode = 1
            print(f'Error: scrapy.cfg already exists in {abspath(project_dir)}')
            return

        if not self._is_valid_name(project_name):
            self.exitcode = 1
            return

        self._copytree(self.templates_dir, abspath(project_dir))
        move(join(project_dir, 'module'), join(project_dir, project_name))
        for paths in TEMPLATES_TO_RENDER:
            path = join(*paths)
            tplfile = join(project_dir, string.Template(path).substitute(project_name=project_name))
            render_templatefile(tplfile, project_name=project_name, ProjectName=string_camelcase(project_name))
        print(f"New Scrapy project '{project_name}', using template directory "
              f"'{self.templates_dir}', created in:")
        print(f"    {abspath(project_dir)}\n")
        print("You can start your first spider with:")
        print(f"    cd {project_dir}")
        print("    scrapy genspider example example.com")

    @property
    def templates_dir(self):
        return join(
            self.settings['TEMPLATES_DIR'] or join(scrapy.__path__[0], 'templates'),
            'project'
        )
