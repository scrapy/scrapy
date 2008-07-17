#!/usr/bin/env python
"""
Cluster control script
"""

from optparse import OptionParser
import urllib

def main():
    parser = OptionParser(usage="Usage: scrapy-cluster-ctl.py [domain [domain [...]]] [options]" )
    parser.add_option("--disablenode", dest="disable_node", help="Disable given node (by name) so it will no accept more run requests.")
    parser.add_option("--enablenode", dest="enable_node", help="Enable given node (by name) so it will accept again run requests")
    parser.add_option("--format", dest="format", help="Output format. Default: pprint.", default="pprint")
    parser.add_option("--list", metavar="FILE", dest="list", help="Specify a file from where to read domains, one per line.")
    parser.add_option("--now", action="store_true", dest="now", help="Schedule domains to run with priority now.")
    parser.add_option("--output", metavar="FILE", dest="output", help="Output file. If not given, output to stdout.")
    parser.add_option("--port", dest="port", type="int", help="Cluster master port. Default: 8080.", default=8080)
    parser.add_option("--remove", dest="remove", action="store_true", help="Remove from schedule domains given as args.")
    parser.add_option("--schedule", dest="schedule", action="store_true", help="Schedule domains given as args.")
    parser.add_option("--server", dest="server", help="Cluster master server name. Default: localhost.", default="localhost")
    parser.add_option("--status", dest="status", action="store_true", help="Print cluster master status and quit.")
    parser.add_option("--stop", dest="stop", action="store_true", help="Stops a running domain.")
    parser.add_option("--verbosity", dest="verbosity", type="int", help="Sets the report status verbosity.", default=0)
    (opts, args) = parser.parse_args()
    
    output = ""
    domains = []
    urlstring = "http://%s:%s/cluster_master/ws/" % (opts.server, opts.port)
    post = {"format":opts.format, "verbosity":opts.verbosity}
    
    if args:
        domains = ",".join(args)
    elif opts.list:
        try:
            domainlist = []
            for d in open(opts.list, "r").readlines():
                domainlist.append(d.strip())
            domains = ",".join(domainlist)
        except IOError:
            print "Can't open file %s" % opts.list
    
    if opts.status:
        pass
    elif opts.schedule and domains:
        post["schedule"] = domains
        if opts.now:
            post["priority"] = "PRIORITY_NOW"
            post["settings"] = "UNAVAILABLES_NOTIFY=2"
    elif opts.remove and domains:
        post["remove"] = domains
    elif opts.stop and domains:
        post["stop"] = domains
    elif opts.disable_node:
        post["disable_node"] = opts.disable_node
    elif opts.enable_node:
        post["enable_node"] = opts.enable_node
    else:
        parser.print_help()
        return
    
    f = urllib.urlopen(urlstring, urllib.urlencode(post))
    output=f.read()

    if not opts.output:
        print output
    else:
        try:
            open(opts.output, "w").write(output)
        except IOError:
            open("/tmp/decobot-schedule.tmp", "w").write(output)
            print "Could not open file %s for writing. Output dumped to /tmp/decobot-schedule.tmp instead." % opts.output

if __name__ == '__main__':
    main()