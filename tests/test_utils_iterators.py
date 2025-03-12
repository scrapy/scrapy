import pytest

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Response, TextResponse, XmlResponse
from scrapy.utils.iterators import _body_or_str, csviter, xmliter, xmliter_lxml
from tests import get_testdata


class XmliterBase:
    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_xmliter(self):
        body = b"""
            <?xml version="1.0" encoding="UTF-8"?>
            <products xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                      xsi:noNamespaceSchemaLocation="someschmea.xsd">
              <product id="001">
                <type>Type 1</type>
                <name>Name 1</name>
              </product>
              <product id="002">
                <type>Type 2</type>
                <name>Name 2</name>
              </product>
            </products>
        """

        response = XmlResponse(url="http://example.com", body=body)
        attrs = [
            (
                x.attrib["id"],
                x.xpath("name/text()").getall(),
                x.xpath("./type/text()").getall(),
            )
            for x in self.xmliter(response, "product")
        ]

        assert attrs == [
            ("001", ["Name 1"], ["Type 1"]),
            ("002", ["Name 2"], ["Type 2"]),
        ]

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_xmliter_unusual_node(self):
        body = b"""<?xml version="1.0" encoding="UTF-8"?>
            <root>
                <matchme...></matchme...>
                <matchmenot></matchmenot>
            </root>
        """
        response = XmlResponse(url="http://example.com", body=body)
        nodenames = [
            e.xpath("name()").getall() for e in self.xmliter(response, "matchme...")
        ]
        assert nodenames == [["matchme..."]]

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_xmliter_unicode(self):
        # example taken from https://github.com/scrapy/scrapy/issues/1665
        body = """<?xml version="1.0" encoding="UTF-8"?>
            <þingflokkar>
               <þingflokkur id="26">
                  <heiti />
                  <skammstafanir>
                     <stuttskammstöfun>-</stuttskammstöfun>
                     <löngskammstöfun />
                  </skammstafanir>
                  <tímabil>
                     <fyrstaþing>80</fyrstaþing>
                  </tímabil>
               </þingflokkur>
               <þingflokkur id="21">
                  <heiti>Alþýðubandalag</heiti>
                  <skammstafanir>
                     <stuttskammstöfun>Ab</stuttskammstöfun>
                     <löngskammstöfun>Alþb.</löngskammstöfun>
                  </skammstafanir>
                  <tímabil>
                     <fyrstaþing>76</fyrstaþing>
                     <síðastaþing>123</síðastaþing>
                  </tímabil>
               </þingflokkur>
               <þingflokkur id="27">
                  <heiti>Alþýðuflokkur</heiti>
                  <skammstafanir>
                     <stuttskammstöfun>A</stuttskammstöfun>
                     <löngskammstöfun>Alþfl.</löngskammstöfun>
                  </skammstafanir>
                  <tímabil>
                     <fyrstaþing>27</fyrstaþing>
                     <síðastaþing>120</síðastaþing>
                  </tímabil>
               </þingflokkur>
            </þingflokkar>"""

        for r in (
            # with bytes
            XmlResponse(url="http://example.com", body=body.encode("utf-8")),
            # Unicode body needs encoding information
            XmlResponse(url="http://example.com", body=body, encoding="utf-8"),
        ):
            attrs = [
                (
                    x.attrib["id"],
                    x.xpath("./skammstafanir/stuttskammstöfun/text()").getall(),
                    x.xpath("./tímabil/fyrstaþing/text()").getall(),
                )
                for x in self.xmliter(r, "þingflokkur")
            ]

            assert attrs == [
                ("26", ["-"], ["80"]),
                ("21", ["Ab"], ["76"]),
                ("27", ["A"], ["27"]),
            ]

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_xmliter_text(self):
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<products><product>one</product><product>two</product></products>"
        )

        assert [x.xpath("text()").getall() for x in self.xmliter(body, "product")] == [
            ["one"],
            ["two"],
        ]

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_xmliter_namespaces(self):
        body = b"""
            <?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
                <channel>
                <title>My Dummy Company</title>
                <link>http://www.mydummycompany.com</link>
                <description>This is a dummy company. We do nothing.</description>
                <item>
                    <title>Item 1</title>
                    <description>This is item 1</description>
                    <link>http://www.mydummycompany.com/items/1</link>
                    <g:image_link>http://www.mydummycompany.com/images/item1.jpg</g:image_link>
                    <g:id>ITEM_1</g:id>
                    <g:price>400</g:price>
                </item>
                </channel>
            </rss>
        """
        response = XmlResponse(url="http://mydummycompany.com", body=body)
        my_iter = self.xmliter(response, "item")
        node = next(my_iter)
        node.register_namespace("g", "http://base.google.com/ns/1.0")
        assert node.xpath("title/text()").getall() == ["Item 1"]
        assert node.xpath("description/text()").getall() == ["This is item 1"]
        assert node.xpath("link/text()").getall() == [
            "http://www.mydummycompany.com/items/1"
        ]
        assert node.xpath("g:image_link/text()").getall() == [
            "http://www.mydummycompany.com/images/item1.jpg"
        ]
        assert node.xpath("g:id/text()").getall() == ["ITEM_1"]
        assert node.xpath("g:price/text()").getall() == ["400"]
        assert node.xpath("image_link/text()").getall() == []
        assert node.xpath("id/text()").getall() == []
        assert node.xpath("price/text()").getall() == []

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_xmliter_namespaced_nodename(self):
        body = b"""
            <?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
                <channel>
                <title>My Dummy Company</title>
                <link>http://www.mydummycompany.com</link>
                <description>This is a dummy company. We do nothing.</description>
                <item>
                    <title>Item 1</title>
                    <description>This is item 1</description>
                    <link>http://www.mydummycompany.com/items/1</link>
                    <g:image_link>http://www.mydummycompany.com/images/item1.jpg</g:image_link>
                    <g:id>ITEM_1</g:id>
                    <g:price>400</g:price>
                </item>
                </channel>
            </rss>
        """
        response = XmlResponse(url="http://mydummycompany.com", body=body)
        my_iter = self.xmliter(response, "g:image_link")
        node = next(my_iter)
        node.register_namespace("g", "http://base.google.com/ns/1.0")
        assert node.xpath("text()").extract() == [
            "http://www.mydummycompany.com/images/item1.jpg"
        ]

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_xmliter_namespaced_nodename_missing(self):
        body = b"""
            <?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
                <channel>
                <title>My Dummy Company</title>
                <link>http://www.mydummycompany.com</link>
                <description>This is a dummy company. We do nothing.</description>
                <item>
                    <title>Item 1</title>
                    <description>This is item 1</description>
                    <link>http://www.mydummycompany.com/items/1</link>
                    <g:image_link>http://www.mydummycompany.com/images/item1.jpg</g:image_link>
                    <g:id>ITEM_1</g:id>
                    <g:price>400</g:price>
                </item>
                </channel>
            </rss>
        """
        response = XmlResponse(url="http://mydummycompany.com", body=body)
        my_iter = self.xmliter(response, "g:link_image")
        with pytest.raises(StopIteration):
            next(my_iter)

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_xmliter_exception(self):
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<products><product>one</product><product>two</product></products>"
        )

        iter = self.xmliter(body, "product")
        next(iter)
        next(iter)
        with pytest.raises(StopIteration):
            next(iter)

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_xmliter_objtype_exception(self):
        i = self.xmliter(42, "product")
        with pytest.raises(TypeError):
            next(i)

    @pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
    def test_xmliter_encoding(self):
        body = (
            b'<?xml version="1.0" encoding="ISO-8859-9"?>\n'
            b"<xml>\n"
            b"    <item>Some Turkish Characters \xd6\xc7\xde\xdd\xd0\xdc \xfc\xf0\xfd\xfe\xe7\xf6</item>\n"
            b"</xml>\n\n"
        )
        response = XmlResponse("http://www.example.com", body=body)
        assert (
            next(self.xmliter(response, "item")).get()
            == "<item>Some Turkish Characters \xd6\xc7\u015e\u0130\u011e\xdc \xfc\u011f\u0131\u015f\xe7\xf6</item>"
        )


class TestXmliter(XmliterBase):
    xmliter = staticmethod(xmliter)

    def test_deprecation(self):
        body = b"""
            <?xml version="1.0" encoding="UTF-8"?>
            <products>
              <product></product>
            </products>
        """
        with pytest.warns(
            ScrapyDeprecationWarning,
            match="xmliter",
        ):
            next(self.xmliter(body, "product"))


class TestLxmlXmliter(XmliterBase):
    xmliter = staticmethod(xmliter_lxml)

    def test_xmliter_iterate_namespace(self):
        body = b"""
            <?xml version="1.0" encoding="UTF-8"?>
            <rss version="2.0" xmlns="http://base.google.com/ns/1.0">
                <channel>
                <title>My Dummy Company</title>
                <link>http://www.mydummycompany.com</link>
                <description>This is a dummy company. We do nothing.</description>
                <item>
                    <title>Item 1</title>
                    <description>This is item 1</description>
                    <link>http://www.mydummycompany.com/items/1</link>
                    <image_link>http://www.mydummycompany.com/images/item1.jpg</image_link>
                    <image_link>http://www.mydummycompany.com/images/item2.jpg</image_link>
                </item>
                </channel>
            </rss>
        """
        response = XmlResponse(url="http://mydummycompany.com", body=body)

        no_namespace_iter = self.xmliter(response, "image_link")
        assert len(list(no_namespace_iter)) == 0

        namespace_iter = self.xmliter(
            response, "image_link", "http://base.google.com/ns/1.0"
        )
        node = next(namespace_iter)
        assert node.xpath("text()").getall() == [
            "http://www.mydummycompany.com/images/item1.jpg"
        ]
        node = next(namespace_iter)
        assert node.xpath("text()").getall() == [
            "http://www.mydummycompany.com/images/item2.jpg"
        ]

    def test_xmliter_namespaces_prefix(self):
        body = b"""
        <?xml version="1.0" encoding="UTF-8"?>
        <root>
            <h:table xmlns:h="http://www.w3.org/TR/html4/">
              <h:tr>
                <h:td>Apples</h:td>
                <h:td>Bananas</h:td>
              </h:tr>
            </h:table>

            <f:table xmlns:f="http://www.w3schools.com/furniture">
              <f:name>African Coffee Table</f:name>
              <f:width>80</f:width>
              <f:length>120</f:length>
            </f:table>

        </root>
        """
        response = XmlResponse(url="http://mydummycompany.com", body=body)
        my_iter = self.xmliter(response, "table", "http://www.w3.org/TR/html4/", "h")

        node = next(my_iter)
        assert len(node.xpath("h:tr/h:td").getall()) == 2
        assert node.xpath("h:tr/h:td[1]/text()").getall() == ["Apples"]
        assert node.xpath("h:tr/h:td[2]/text()").getall() == ["Bananas"]

        my_iter = self.xmliter(
            response, "table", "http://www.w3schools.com/furniture", "f"
        )

        node = next(my_iter)
        assert node.xpath("f:name/text()").getall() == ["African Coffee Table"]

    def test_xmliter_objtype_exception(self):
        i = self.xmliter(42, "product")
        with pytest.raises(TypeError):
            next(i)


class TestUtilsCsv:
    def test_csviter_defaults(self):
        body = get_testdata("feeds", "feed-sample3.csv")
        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response)

        result = list(csv)
        assert result == [
            {"id": "1", "name": "alpha", "value": "foobar"},
            {"id": "2", "name": "unicode", "value": "\xfan\xedc\xf3d\xe9\u203d"},
            {"id": "3", "name": "multi", "value": "foo\nbar"},
            {"id": "4", "name": "empty", "value": ""},
        ]

        # explicit type check cuz' we no like stinkin' autocasting! yarrr
        for result_row in result:
            assert all(isinstance(k, str) for k in result_row)
            assert all(isinstance(v, str) for v in result_row.values())

    def test_csviter_delimiter(self):
        body = get_testdata("feeds", "feed-sample3.csv").replace(b",", b"\t")
        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response, delimiter="\t")

        assert list(csv) == [
            {"id": "1", "name": "alpha", "value": "foobar"},
            {"id": "2", "name": "unicode", "value": "\xfan\xedc\xf3d\xe9\u203d"},
            {"id": "3", "name": "multi", "value": "foo\nbar"},
            {"id": "4", "name": "empty", "value": ""},
        ]

    def test_csviter_quotechar(self):
        body1 = get_testdata("feeds", "feed-sample6.csv")
        body2 = get_testdata("feeds", "feed-sample6.csv").replace(b",", b"|")

        response1 = TextResponse(url="http://example.com/", body=body1)
        csv1 = csviter(response1, quotechar="'")

        assert list(csv1) == [
            {"id": "1", "name": "alpha", "value": "foobar"},
            {"id": "2", "name": "unicode", "value": "\xfan\xedc\xf3d\xe9\u203d"},
            {"id": "3", "name": "multi", "value": "foo\nbar"},
            {"id": "4", "name": "empty", "value": ""},
        ]

        response2 = TextResponse(url="http://example.com/", body=body2)
        csv2 = csviter(response2, delimiter="|", quotechar="'")

        assert list(csv2) == [
            {"id": "1", "name": "alpha", "value": "foobar"},
            {"id": "2", "name": "unicode", "value": "\xfan\xedc\xf3d\xe9\u203d"},
            {"id": "3", "name": "multi", "value": "foo\nbar"},
            {"id": "4", "name": "empty", "value": ""},
        ]

    def test_csviter_wrong_quotechar(self):
        body = get_testdata("feeds", "feed-sample6.csv")
        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response)

        assert list(csv) == [
            {"'id'": "1", "'name'": "'alpha'", "'value'": "'foobar'"},
            {
                "'id'": "2",
                "'name'": "'unicode'",
                "'value'": "'\xfan\xedc\xf3d\xe9\u203d'",
            },
            {"'id'": "'3'", "'name'": "'multi'", "'value'": "'foo"},
            {"'id'": "4", "'name'": "'empty'", "'value'": ""},
        ]

    def test_csviter_delimiter_binary_response_assume_utf8_encoding(self):
        body = get_testdata("feeds", "feed-sample3.csv").replace(b",", b"\t")
        response = Response(url="http://example.com/", body=body)
        csv = csviter(response, delimiter="\t")

        assert list(csv) == [
            {"id": "1", "name": "alpha", "value": "foobar"},
            {"id": "2", "name": "unicode", "value": "\xfan\xedc\xf3d\xe9\u203d"},
            {"id": "3", "name": "multi", "value": "foo\nbar"},
            {"id": "4", "name": "empty", "value": ""},
        ]

    def test_csviter_headers(self):
        sample = get_testdata("feeds", "feed-sample3.csv").splitlines()
        headers, body = sample[0].split(b","), b"\n".join(sample[1:])

        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response, headers=[h.decode("utf-8") for h in headers])

        assert list(csv) == [
            {"id": "1", "name": "alpha", "value": "foobar"},
            {"id": "2", "name": "unicode", "value": "\xfan\xedc\xf3d\xe9\u203d"},
            {"id": "3", "name": "multi", "value": "foo\nbar"},
            {"id": "4", "name": "empty", "value": ""},
        ]

    def test_csviter_falserow(self):
        body = get_testdata("feeds", "feed-sample3.csv")
        body = b"\n".join((body, b"a,b", b"a,b,c,d"))

        response = TextResponse(url="http://example.com/", body=body)
        csv = csviter(response)

        assert list(csv) == [
            {"id": "1", "name": "alpha", "value": "foobar"},
            {"id": "2", "name": "unicode", "value": "\xfan\xedc\xf3d\xe9\u203d"},
            {"id": "3", "name": "multi", "value": "foo\nbar"},
            {"id": "4", "name": "empty", "value": ""},
        ]

    def test_csviter_exception(self):
        body = get_testdata("feeds", "feed-sample3.csv")

        response = TextResponse(url="http://example.com/", body=body)
        iter = csviter(response)
        next(iter)
        next(iter)
        next(iter)
        next(iter)
        with pytest.raises(StopIteration):
            next(iter)

    def test_csviter_encoding(self):
        body1 = get_testdata("feeds", "feed-sample4.csv")
        body2 = get_testdata("feeds", "feed-sample5.csv")

        response = TextResponse(
            url="http://example.com/", body=body1, encoding="latin1"
        )
        csv = csviter(response)
        assert list(csv) == [
            {"id": "1", "name": "latin1", "value": "test"},
            {"id": "2", "name": "something", "value": "\xf1\xe1\xe9\xf3"},
        ]

        response = TextResponse(url="http://example.com/", body=body2, encoding="cp852")
        csv = csviter(response)
        assert list(csv) == [
            {"id": "1", "name": "cp852", "value": "test"},
            {
                "id": "2",
                "name": "something",
                "value": "\u255a\u2569\u2569\u2569\u2550\u2550\u2557",
            },
        ]


class TestHelper:
    bbody = b"utf8-body"
    ubody = bbody.decode("utf8")
    txtresponse = TextResponse(url="http://example.org/", body=bbody, encoding="utf-8")
    response = Response(url="http://example.org/", body=bbody)

    def test_body_or_str(self):
        for obj in (self.bbody, self.ubody, self.txtresponse, self.response):
            r1 = _body_or_str(obj)
            self._assert_type_and_value(r1, self.ubody, obj)
            r2 = _body_or_str(obj, unicode=True)
            self._assert_type_and_value(r2, self.ubody, obj)
            r3 = _body_or_str(obj, unicode=False)
            self._assert_type_and_value(r3, self.bbody, obj)
            assert type(r1) is type(r2)
            assert type(r1) is not type(r3)

    def _assert_type_and_value(self, a, b, obj):
        assert type(a) is type(b), f"Got {type(a)}, expected {type(b)} for {obj!r}"
        assert a == b
