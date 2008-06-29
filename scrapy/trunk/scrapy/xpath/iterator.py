import re
from xml.sax.saxutils import escape
from cStringIO import StringIO

import libxml2

from scrapy.xpath.constructors import xml_parser_options
from scrapy.xpath.selector import XmlXPathSelector

class XMLNodeIterator(object):
    """XMLNodeIterator provides a way to iterate over all nodes of the same
    name (passed in the constructor) in a XML Response without parsing the
    entire response in memory. The iterator returns XPathSelector objects.

    Usage example:

    for x in XMLNodeIterator(response, "product"):
        i = ScrapedItem()
        i.assign("id", x.x("@id"))
        i.assign("name", x.x("./name/text()")
    """

    def __init__(self, response, node, chunk_size=2048):
        self.response = response
        self.node = node
        self.chunk_size = 2048

    def __iter__(self):
        sax_parser = XMLNodeSAXParser(self.node, self.response)
        contents = self.response.body.to_string()
        ctxt = libxml2.createPushParser(sax_parser, '', 0, None)
        ctxt.ctxtUseOptions(xml_parser_options)
        for i in xrange(0, len(contents), self.chunk_size):
            chunk = contents[i:i + self.chunk_size]
            ctxt.parseChunk(chunk, len(chunk), 0)
            while sax_parser.selectors:
                yield sax_parser.selectors.pop(0)
        ctxt.parseChunk('', 0, 1)

class XMLNodeSAXParser():

    xmldeclr_re = re.compile(r'<\?xml.*?\?>')

    def __init__(self, requested_nodename, response):
        self.requested_nodename = requested_nodename
        self.inside_requested_node = False
        self.buffer = StringIO()
        self.xml_declaration = self._extract_xmldecl(response.body.to_string()[0:4096])
        self.selectors = []

    def startElement(self, name, attributes):
        if name == self.requested_nodename:
            self.inside_requested_node = True
            self.buffer.close()
            self.buffer = StringIO()
        attributes = attributes or {}
        attribute_strings = ["%s='%s'" % tuple(ka) for ka in attributes.items()]
        self.buffer.write('<' + ' '.join([name] + attribute_strings) + '>')

    def endElement(self, name):
        self.buffer.write('</%s>' % name)

        if name == self.requested_nodename:
            self.inside_requested_node = False
            string = ''.join([self.xml_declaration, self.buffer.getvalue()])
            selector = XmlXPathSelector(text=string).x('/' + self.requested_nodename)[0]
            self.selectors.append(selector)

    def characters(self, data):
        if self.inside_requested_node:
            self.buffer.write(escape(data))

    def cdataBlock(self, data):
        #self.characters('<![CDATA[' + data + ']]>')
        if self.inside_requested_node:
            self.buffer.write('<![CDATA[' + data + ']]>')

    def _extract_xmldecl(self, string):
        m = self.xmldeclr_re.search(string)
        return m.group() if m else ''


# TESTING #
from xml.parsers.expat import ParserCreate

class expat_XMLNodeIterator():
    def __init__(self, response, req_nodename, chunk_size=2048):
        self._response = response
        self._req_nodename = req_nodename
        self._chunk_size = chunk_size

        self._byte_offset_buffer = []

        self._parser = ParserCreate()
        self._parser.StartElementHandler = self._StartElementHandler
        self._parser.EndElementHandler = self._EndElementHandler

    def _StartElementHandler(self, name, attrs):
        if name == self._req_nodename and not self._inside_req_node:
            self._start_pos = self._parser.CurrentByteIndex
            self._inside_req_node = True

    def _EndElementHandler(self, name):
        if name == self._req_nodename and self._inside_req_node:
            self._byte_offset_buffer.append((self._start_pos, self._parser.CurrentByteIndex))
            self._inside_req_node = False

    def __iter__(self):
        response_body = self._response.body.to_string()
        self._inside_req_node = False
        for i in xrange(0, len(response_body), self._chunk_size):
            self._parser.Parse(response_body[i:i + self._chunk_size])
            while self._byte_offset_buffer:
                start, end = self._byte_offset_buffer.pop(0)
                yield response_body[start:end]
        self._parser.Parse('', 1)


# TESTING (pablo) #
# Yet another node iterator: this one is based entirely on regular expressions,
# which means it should be faster but needs some profiling to confirm.

class re_XMLNodeIterator():

    def __init__(self, response, node):
        self.response = response
        self.node = node
        self.re = re.compile(r"<%s[\s>].*?</%s>" % (node, node), re.DOTALL)

    def __iter__(self):
        for match in self.re.finditer(self.response.body.to_string()):
            yield XmlXPathSelector(text=match.group()).x('/' + self.node)[0]
