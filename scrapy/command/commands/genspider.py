from __future__ import with_statement

import os
import string
import shutil

from scrapy.spider import spiders
from scrapy.command import ScrapyCommand
from scrapy.conf import settings
from scrapy.utils.misc import render_templatefile, string_camelcase


class Command(ScrapyCommand):
    """ Childs can define custom tvars """
    custom_tvars = {}

    def syntax(self):
        return "<spider_name> <spider_domain_name> [--template=template_name]"

    def short_desc(self):
        return "Generate new spider based on a predefined template"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("--template", dest="template", help="Uses a custom template.", default="crawl")
        parser.add_option("--force", dest="force", help="If the spider already exists, overwrite it with the template", action="store_true")

    def run(self, args, opts):
        if len(args) < 2:
            return False

        template_file = os.path.join(settings['TEMPLATES_DIR'], 'spider_%s.tmpl' % opts.template)
        if not os.path.exists(template_file):
            print "Template named %s.tmpl does not exist" % opts.template
            return

        name = self.normalize_name(args[0])
        site = args[1]
        spiders_dict = spiders.asdict()
        if site in spiders_dict.keys():
            if opts.force:
                print "Spider '%s' already exists. Overwriting it..." % name
            else:
                print "Spider '%s' already exists" % name
                return
        self._genspider(name, site, template_file)

    def normalize_name(self, name):
        name = name.replace('-', '_') # - are replaced by _, for valid python modules
        if name[0] not in string.letters: # name must start with a letter, for valid python modules
            name = "a" + name
            print "Spider names must start with a letter; converted to %s." % name
        return name
        
    def _genspider(self, name, site, template_file):
        """ Generate spider """
        tvars = {
            'project_name': settings.get('PROJECT_NAME'),
            'ProjectName': string_camelcase(settings.get('PROJECT_NAME')),
            'name': name,
            'site': site,
            'classname': '%sSpider' % ''.join([s.capitalize() for s in name.split('_')])
        }
        tvars.update(self.custom_tvars)

        spiders_module = __import__(settings['NEWSPIDER_MODULE'], {}, {}, [''])
        spiders_dir = os.path.abspath(os.path.dirname(spiders_module.__file__))
        spider_file = '%s/%s.py' % (spiders_dir, name)

        shutil.copyfile(template_file, spider_file)
        render_templatefile(spider_file, **tvars)

