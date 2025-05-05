import weakref

import parsel
import pytest
from packaging import version

from scrapy.http import HtmlResponse, TextResponse, XmlResponse
from scrapy.selector import Selector

PARSEL_VERSION = version.parse(getattr(parsel, "__version__", "0.0"))
PARSEL_18_PLUS = PARSEL_VERSION >= version.parse("1.8.0")


class TestSelector:
    def test_simple_selection(self):
        """Simple selector tests"""
        body = b"<p><input name='a'value='1'/><input name='b'value='2'/></p>"
        response = TextResponse(url="http://example.com", body=body, encoding="utf-8")
        sel = Selector(response)

        xl = sel.xpath("//input")
        assert len(xl) == 2
        for x in xl:
            assert isinstance(x, Selector)

        assert sel.xpath("//input").getall() == [x.get() for x in sel.xpath("//input")]
        assert [x.get() for x in sel.xpath("//input[@name='a']/@name")] == ["a"]
        assert [
            x.get()
            for x in sel.xpath(
                "number(concat(//input[@name='a']/@value, //input[@name='b']/@value))"
            )
        ] == ["12.0"]
        assert sel.xpath("concat('xpath', 'rules')").getall() == ["xpathrules"]
        assert [
            x.get()
            for x in sel.xpath(
                "concat(//input[@name='a']/@value, //input[@name='b']/@value)"
            )
        ] == ["12"]

    def test_root_base_url(self):
        body = b'<html><form action="/path"><input name="a" /></form></html>'
        url = "http://example.com"
        response = TextResponse(url=url, body=body, encoding="utf-8")
        sel = Selector(response)
        assert url == sel.root.base

    def test_flavor_detection(self):
        text = b'<div><img src="a.jpg"><p>Hello</div>'
        sel = Selector(XmlResponse("http://example.com", body=text, encoding="utf-8"))
        assert sel.type == "xml"
        assert sel.xpath("//div").getall() == [
            '<div><img src="a.jpg"><p>Hello</p></img></div>'
        ]

        sel = Selector(HtmlResponse("http://example.com", body=text, encoding="utf-8"))
        assert sel.type == "html"
        assert sel.xpath("//div").getall() == [
            '<div><img src="a.jpg"><p>Hello</p></div>'
        ]

    def test_http_header_encoding_precedence(self):
        # '\xa3'     = pound symbol in unicode
        # '\xc2\xa3' = pound symbol in utf-8
        # '\xa3'     = pound symbol in latin-1 (iso-8859-1)

        meta = (
            '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">'
        )
        head = f"<head>{meta}</head>"
        body_content = '<span id="blank">\xa3</span>'
        body = f"<body>{body_content}</body>"
        html = f"<html>{head}{body}</html>"
        encoding = "utf-8"
        html_utf8 = html.encode(encoding)

        headers = {"Content-Type": ["text/html; charset=utf-8"]}
        response = HtmlResponse(
            url="http://example.com", headers=headers, body=html_utf8
        )
        x = Selector(response)
        assert x.xpath("//span[@id='blank']/text()").getall() == ["\xa3"]

    def test_badly_encoded_body(self):
        # \xe9 alone isn't valid utf8 sequence
        r1 = TextResponse(
            "http://www.example.com",
            body=b"<html><p>an Jos\xe9 de</p><html>",
            encoding="utf-8",
        )
        Selector(r1).xpath("//text()").getall()

    def test_weakref_slots(self):
        """Check that classes are using slots and are weak-referenceable"""
        x = Selector(text="")
        weakref.ref(x)
        assert not hasattr(x, "__dict__"), (
            f"{x.__class__.__name__} does not use __slots__"
        )

    def test_selector_bad_args(self):
        with pytest.raises(ValueError, match="received both response and text"):
            Selector(TextResponse(url="http://example.com", body=b""), text="")


class TestJMESPath:
    @pytest.mark.skipif(
        not PARSEL_18_PLUS, reason="parsel < 1.8 doesn't support jmespath"
    )
    def test_json_has_html(self) -> None:
        """Sometimes the information is returned in a json wrapper"""

        body = """
        {
            "content": [
                {
                    "name": "A",
                    "value": "a"
                },
                {
                    "name": {
                        "age": 18
                    },
                    "value": "b"
                },
                {
                    "name": "C",
                    "value": "c"
                },
                {
                    "name": "<a>D</a>",
                    "value": "<div>d</div>"
                }
            ],
            "html": "<div><a>a<br>b</a>c</div><div><a>d</a>e<b>f</b></div>"
        }
        """
        resp = TextResponse(url="http://example.com", body=body, encoding="utf-8")
        assert (
            resp.jmespath("html").get()
            == "<div><a>a<br>b</a>c</div><div><a>d</a>e<b>f</b></div>"
        )
        assert resp.jmespath("html").xpath("//div/a/text()").getall() == ["a", "b", "d"]
        assert resp.jmespath("html").css("div > b").getall() == ["<b>f</b>"]
        assert resp.jmespath("content").jmespath("name.age").get() == "18"

    @pytest.mark.skipif(
        not PARSEL_18_PLUS, reason="parsel < 1.8 doesn't support jmespath"
    )
    def test_html_has_json(self) -> None:
        body = """
        <div>
            <h1>Information</h1>
            <content>
            {
              "user": [
                        {
                                  "name": "A",
                                  "age": 18
                        },
                        {
                                  "name": "B",
                                  "age": 32
                        },
                        {
                                  "name": "C",
                                  "age": 22
                        },
                        {
                                  "name": "D",
                                  "age": 25
                        }
              ],
              "total": 4,
              "status": "ok"
            }
            </content>
        </div>
        """
        resp = TextResponse(url="http://example.com", body=body, encoding="utf-8")
        assert resp.xpath("//div/content/text()").jmespath("user[*].name").getall() == [
            "A",
            "B",
            "C",
            "D",
        ]
        assert resp.xpath("//div/content").jmespath("user[*].name").getall() == [
            "A",
            "B",
            "C",
            "D",
        ]
        assert resp.xpath("//div/content").jmespath("total").get() == "4"

    @pytest.mark.skipif(
        not PARSEL_18_PLUS, reason="parsel < 1.8 doesn't support jmespath"
    )
    def test_jmestpath_with_re(self) -> None:
        body = """
            <div>
                <h1>Information</h1>
                <content>
                {
                  "user": [
                            {
                                      "name": "A",
                                      "age": 18
                            },
                            {
                                      "name": "B",
                                      "age": 32
                            },
                            {
                                      "name": "C",
                                      "age": 22
                            },
                            {
                                      "name": "D",
                                      "age": 25
                            }
                  ],
                  "total": 4,
                  "status": "ok"
                }
                </content>
            </div>
            """
        resp = TextResponse(url="http://example.com", body=body, encoding="utf-8")
        assert resp.xpath("//div/content/text()").jmespath("user[*].name").re(
            r"(\w+)"
        ) == ["A", "B", "C", "D"]
        assert resp.xpath("//div/content").jmespath("user[*].name").re(r"(\w+)") == [
            "A",
            "B",
            "C",
            "D",
        ]

        assert resp.xpath("//div/content").jmespath("unavailable").re(r"(\d+)") == []

        assert (
            resp.xpath("//div/content").jmespath("unavailable").re_first(r"(\d+)")
            is None
        )

        assert resp.xpath("//div/content").jmespath("user[*].age.to_string(@)").re(
            r"(\d+)"
        ) == ["18", "32", "22", "25"]

    @pytest.mark.skipif(PARSEL_18_PLUS, reason="parsel >= 1.8 supports jmespath")
    def test_jmespath_not_available(self) -> None:
        body = """
        {
            "website": {"name": "Example"}
        }
        """
        resp = TextResponse(url="http://example.com", body=body, encoding="utf-8")
        with pytest.raises(AttributeError):
            resp.jmespath("website.name").get()
