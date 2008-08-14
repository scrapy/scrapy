import os

from scrapy.command import ScrapyCommand
from scrapy.replay import Replay
from scrapy.utils import display
from scrapy.conf import settings

class Command(ScrapyCommand):
    def syntax(self):
        return "[options] <replay_file> [action]"

    def short_desc(self):
        return "Replay a session previously recorded with crawl --record"

    def help(self):
        s = "Replay a session previously recorded with crawl --record\n"
        s += "\n"
        s += "Available actions:\n"
        s += "  crawl: just replay the crawl (default if action omitted)\n"
        s += "  diff: replay the crawl and show differences in items scraped/passed\n"
        s += "  update: replay the crawl and update both scraped and passed items\n"
        s += "  showitems: show items stored\n"
        s += "  showpages: show all responses downloaded (not only HTML pages)\n"
        return s

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-v", "--verbose", dest="verbose", action="store_true", help="show verbose output (full items/responses)")
        parser.add_option("-t", "--item-type", dest="itype", help="item type (scraped, passed). default: scraped", metavar="TYPE")
        parser.add_option("--output", dest="outfile", help="write output to FILE. if omitted uses stdout", metavar="FILE")
        parser.add_option("--nocolour", dest="nocolour", action="store_true", help="disable colorized output (for console only)")
        parser.add_option("-i", "--ignore", dest="ignores", action="append", help="item attribute to ignore. can be passed multiple times", metavar="ATTR")
        parser.add_option("--target", dest="targets", action="append", help="crawl TARGET instead of recorded urls/domains. can be passed multiple times")

    def process_options(self, args, opts):
        ScrapyCommand.process_options(self, args, opts)
        self.opts = opts
        self.action = args[1] if len(args) > 1 else 'crawl'
        mode = 'update' if self.action == 'update' else 'play'
        usedir = args and os.path.isdir(args[0])
        self.replay = Replay(args[0], mode=mode, usedir=usedir)
        if self.action not in ['crawl', 'diff', 'update']:
            settings.overrides['LOG_ENABLED'] = False

    def run(self, args, opts):
        if not args:
            print "A <replay_dir> is required"
            return

        display.nocolour = opts.nocolour

        if opts.itype == 'passed':
            self.before_db = self.replay.passed_old
            self.now_db = self.replay.passed_new
        else: # default is 'scraped'
            opts.itype = 'scraped'
            self.before_db = self.replay.scraped_old
            self.now_db = self.replay.scraped_new

        actionfunc = getattr(self, 'action_%s' % self.action, None)
        if actionfunc:
            rep = actionfunc(opts)
            if rep:
                if opts.outfile:
                    f = open(opts.outfile, "w")
                    f.write(rep)
                    f.close()
                else:
                    print rep,
            self.replay.cleanup()
        else:
            print "Unknown replay action: %s" % self.action

    def action_crawl(self, opts):
        self.replay.play(args=opts.targets)

    def action_update(self, opts):
        self.action_crawl(opts)

    def action_showitems(self, opts):
        s = ""
        s += self._format_items(self.before_db.values())
        s += ">>> Total: %d items %s\n" % (len(self.before_db), opts.itype)
        return s

    def action_showpages(self, opts):
        s = ""
        if self.opts.verbose:
            for r in self.replay.responses_old.values():
                s += ">>> %s\n" % str(r)
                s += display.pformat(r)
        else:
            s += "\n".join([str(r) for r in self.replay.responses_old.values()]) + "\n"
        s += ">>> Total: %d responses received\n" % len(self.replay.responses_old)
        return s

    def action_diff(self, opts):
        self.action_crawl(opts)

        guids_before = set(self.before_db.keys())
        guids_now = set(map(str, self.now_db.keys()))

        guids_new = guids_now - guids_before
        guids_missing = guids_before - guids_now
        guids_both = guids_now & guids_before

        chcount, chreport = self._report_differences(self.before_db, self.now_db, guids_both)

        s = "CRAWLING DIFFERENCES REPORT\n\n"

        s += "Total items     : %d\n" % (len(guids_both) - chcount)
        s += "  Items OK      : %d\n" % (len(guids_both) - chcount)
        s += "  New items     : %d\n" % len(guids_new)
        s += "  Missing items : %d\n" % len(guids_missing)
        s += "  Changed items : %d\n" % chcount

        s += "\n"
        s += "- NEW ITEMS (%d) -----------------------------------------\n" % len(guids_new)
        s += self._format_items([self.now_db[g] for g in guids_new])

        s += "\n"
        s += "- MISSING ITEMS (%d) -------------------------------------\n" % len(guids_missing)
        s += self._format_items([self.before_db[g] for g in guids_missing])

        s += "\n"
        s += "- CHANGED ITEMS (%d) -------------------------------------\n" % chcount
        s += chreport

        return s

    def _report_differences(self, old_items, new_items, guids):
        items_old = [old_items[g] for g in guids]
        items_new = [new_items[g] for g in guids]

        c = 0
        s = ""
        for old, new in zip(items_old, items_new):
            d = self._item_diff(old, new)
            if d:
                c += 1
                s += d
        return c, s

    def _item_diff(self, old, new):
        olddic = old.__dict__
        newdic = new.__dict__
        ignored_attrs = set(self.opts.ignores or [])
        allattrs = [a for a in olddic.keys() + newdic.keys() if not a.startswith('_') and a not in ignored_attrs]

        diff = {}
        for attr in sorted(allattrs):
            oldval = olddic.get(attr, None)
            newval = newdic.get(attr, None)
            if oldval != newval:
                diff[attr] = {}
                diff[attr]['old'] = oldval
                diff[attr]['new'] = newval

        s = ""
        if diff:
            s += ">>> Item guid=%s name=%s\n" % (old.guid, old.name)
            s += display.pformat(diff) + "\n"
        return s

    def _format_items(self, items):
        if self.opts.verbose:
            s = display.pformat(items)
        else:
            s = ""
            for i in items:
                s += "%s\n" % str(i)
                s += "  <%s>\n" % i.url
        return s

