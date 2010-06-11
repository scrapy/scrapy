#!/usr/bin/env python

import sys

from boto.sqs.connection import SQSConnection
from boto.sqs.message import Message

from scrapy.utils.py26 import json
from scrapy.conf import settings

qname = settings['SQS_QUEUE']

if len(sys.argv) <= 1:
    print "usage: %s <command> [args]" % sys.argv[0]
    print
    print "available commands:"
    print "  put <spider_name> - append spider to queue"
    print
    print "SQS queue: %s" % qname
    print
    sys.exit()

cmd, args = sys.argv[1], sys.argv[2:]

if cmd == 'put':
    conn = SQSConnection(settings['AWS_ACCESS_KEY_ID'], \
        settings['AWS_SECRET_ACCESS_KEY'])
    q = conn.create_queue(qname)
    msg = Message(body=json.dumps({'name': args[0]}))
    q.write(msg)
