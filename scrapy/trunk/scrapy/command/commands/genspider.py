import os
import string

from scrapy.spider import spiders
from scrapy.command import ScrapyCommand
from scrapy.conf import settings

class Command(ScrapyCommand):
    def syntax(self):
        return "<spider_name> <spider_domain_name>"

    def short_desc(self):
        return "Generate new spider based on predefined template"

    def run(self, args, opts):
        if len(args) != 2:
            return False

        name = args[0]
        site = args[1]
        spiders_dict = spiders.asdict()
        if not name in spiders_dict.keys():
            self._genspider(name, site)
        else:
            print "Spider '%s' exist" % name

    def _genspider(self, name, site):
        """ Generate spider """
        tvars = {
            'name': name,
            'site': site,
            'classname': '%sSpider' % ''.join([s.capitalize() for s in name.split('-')])
        }

        spiders_module = __import__(settings['NEWSPIDER_MODULE'], {}, {}, [''])
        spidersdir = os.path.abspath(os.path.dirname(spiders_module.__file__))
        if name[0] not in string.letters: # must start with a letter, for valid python modules
            name = "a" + name
        name = name.replace('-', '_') # - are replaced by _, for valid python modules
        self._genfiles('spider.tmpl', '%s/%s.py' % (spidersdir, name), tvars)

    def _genfiles(self, template_name, source_name, tvars):
        """ Generate source from template, substitute variables """
        template_file = os.path.join(settings['TEMPLATES_DIR'], template_name)
        tmpl = open(template_file)
        clines = []
        for l in tmpl.readlines():
            for key, val in tvars.items():
                l = l.replace('@%s@' % key, val)
            clines.append(l)
        tmpl.close()
        source = ''.join(clines)
        if not os.path.exists(source_name):
            sfile = open(source_name, "w")
            sfile.write(source)
            sfile.close()
