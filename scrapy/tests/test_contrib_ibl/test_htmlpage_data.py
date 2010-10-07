PAGE = u"""
<style id="scrapy-style" type="text/css">@import url(http://localhost:8000/as/site_media/clean.css);                           
</style>
<body>
<div class="scrapy-selected" id="header">
<img src="company_logo.jpg" style="margin-left: 68px; padding-top:5px;" alt="Logo" width="530" height="105">
<div id="vertrule">
<h1>COMPANY - <ins data-scrapy-annotate="{&quot;variant&quot;: &quot;0&quot;, &quot;generated&quot;: true, &quot;annotations&quot;: {&quot;content&quot;: &quot;title&quot;}}">Item Title</ins></h1>
<p>introduction</p>
<div>
<img src="/upload/img.jpg" classid=""
    data-scrapy-annotate="{&quot;variant&quot;: &quot;0&quot;, &quot;annotations&quot;: {&quot;image_url&quot;: &quot;src&quot;}}"
>
<p classid="" data-scrapy-annotate="{&quot;variant&quot;: &quot;0&quot;, &quot;annotations&quot;: {&quot;content&quot;: &quot;description&quot;}}"
>
This is such a nice item<br/> Everybody likes it.
</p>
<br></br>
</div>
<p data-scrapy-annotate="{&quot;variant&quot;: &quot;0&quot;, &quot;annotations&quot;: {&quot;content&quot;: &quot;features&quot;}}"
class="" >Power: 50W</p>
<!-- A comment --!>
<ul data-scrapy-replacement='select' class='product'>
<li data-scrapy-replacement='option'>Small</li>
<li data-scrapy-replacement='option'>Big</li>
</ul>
<p>click here for other items</p>
<h3>Louis Chair</h3>
<table class="rulet" width="420" cellpadding="0" cellspacing="0"><tbody>
<tr><td>Height</td>
<td><ins data-scrapy-annotate="{&quot;variant&quot;: &quot;0&quot;, &quot;generated&quot;: true, &quot;annotations&quot;: {&quot;content&quot;: &quot;price&quot;}}">32.00</ins></td>
</tr><tbody></table>
<p onmouseover='xxx' class= style="my style">
"""

PARSED = [
{'start': 0, 'end': 1},
{'attributes': {'type': 'text/css', 'id': 'scrapy-style'}, 'tag': 'style', 'end': 42, 'start': 1, 'tag_type': 1},
{'start': 42, 'end': 129},
{'attributes': {}, 'tag': 'style', 'end': 137, 'start': 129, 'tag_type': 2},
{'start': 137, 'end': 138},
{'attributes': {}, 'tag': 'body', 'end': 144, 'start': 138, 'tag_type': 1},
{'start': 144, 'end': 145},
{'attributes': {'class': 'scrapy-selected', 'id': 'header'}, 'tag': 'div', 'end': 186, 'start': 145, 'tag_type': 1},
{'start': 186, 'end': 187},
{'attributes': {'src': 'company_logo.jpg', 'style': 'margin-left: 68px; padding-top:5px;', 'width': '530', 'alt': 'Logo', 'height': '105'}, 'tag': 'img', 'end': 295, 'start': 187, 'tag_type': 1},
{'start': 295, 'end': 296},
{'attributes': {'id': 'vertrule'}, 'tag': 'div', 'end': 315, 'start': 296, 'tag_type': 1},
{'start': 315, 'end': 316},
{'attributes': {}, 'tag': 'h1', 'end': 320, 'start': 316, 'tag_type': 1},
{'start': 320, 'end': 330},
{'attributes': {'data-scrapy-annotate': '{&quot;variant&quot;: &quot;0&quot;, &quot;generated&quot;: true, &quot;annotations&quot;: {&quot;content&quot;: &quot;title&quot;}}'}, 'tag': 'ins', 'end': 491, 'start': 330, 'tag_type': 1},
{'start': 491, 'end': 501},
{'attributes': {}, 'tag': 'ins', 'end': 507, 'start': 501, 'tag_type': 2},
{'attributes': {}, 'tag': 'h1', 'end': 512, 'start': 507, 'tag_type': 2},
{'start': 512, 'end': 513},
{'attributes': {}, 'tag': 'p', 'end': 516, 'start': 513, 'tag_type': 1},
{'start': 516, 'end': 528},
{'attributes': {}, 'tag': 'p', 'end': 532, 'start': 528, 'tag_type': 2},
{'start': 532, 'end': 533},
{'attributes': {}, 'tag': 'div', 'end': 538, 'start': 533, 'tag_type': 1},
{'start': 538, 'end': 539},
{'attributes': {'classid': None, 'src': '/upload/img.jpg', 'data-scrapy-annotate': '{&quot;variant&quot;: &quot;0&quot;, &quot;annotations&quot;: {&quot;image_url&quot;: &quot;src&quot;}}'}, 'tag': 'img', 'end': 709, 'start': 539, 'tag_type': 1},
{'start': 709, 'end': 710},
{'attributes': {'classid': None, 'data-scrapy-annotate': '{&quot;variant&quot;: &quot;0&quot;, &quot;annotations&quot;: {&quot;content&quot;: &quot;description&quot;}}'}, 'tag': 'p', 'end': 858, 'start': 710, 'tag_type': 1},
{'start': 858, 'end': 883},
{'attributes': {}, 'tag': 'br', 'end': 888, 'start': 883, 'tag_type': 3},
{'start': 888, 'end': 909},
{'attributes': {}, 'tag': 'p', 'end': 913, 'start': 909, 'tag_type': 2},
{'start': 913, 'end': 914},
{'attributes': {}, 'tag': 'br', 'end': 918, 'start': 914, 'tag_type': 1},
{'attributes': {}, 'tag': 'br', 'end': 923, 'start': 918, 'tag_type': 2},
{'start': 923, 'end': 924},
{'attributes': {}, 'tag': 'div', 'end': 930, 'start': 924, 'tag_type': 2},
{'start': 930, 'end': 931},
{'attributes': {'data-scrapy-annotate': '{&quot;variant&quot;: &quot;0&quot;, &quot;annotations&quot;: {&quot;content&quot;: &quot;features&quot;}}', 'class': None}, 'tag': 'p', 'end': 1074, 'start': 931, 'tag_type': 1},
{'start': 1074, 'end': 1084},
{'attributes': {}, 'tag': 'p', 'end': 1088, 'start': 1084, 'tag_type': 2},
{'start': 1088, 'end': 1109},
{'attributes': {'data-scrapy-replacement': 'select', 'class': 'product'}, 'tag': 'ul', 'end': 1162, 'start': 1109, 'tag_type': 1},
{'start': 1162, 'end': 1163},
{'attributes': {'data-scrapy-replacement': 'option'}, 'tag': 'li', 'end': 1200, 'start': 1163, 'tag_type': 1},
{'start': 1200, 'end': 1205},
{'attributes': {}, 'tag': 'li', 'end': 1210, 'start': 1205, 'tag_type': 2},
{'start': 1210, 'end': 1211},
{'attributes': {'data-scrapy-replacement': 'option'}, 'tag': 'li', 'end': 1248, 'start': 1211, 'tag_type': 1},
{'start': 1248, 'end': 1251},
{'attributes': {}, 'tag': 'li', 'end': 1256, 'start': 1251, 'tag_type': 2},
{'start': 1256, 'end': 1257},
{'attributes': {}, 'tag': 'ul', 'end': 1262, 'start': 1257, 'tag_type': 2},
{'start': 1262, 'end': 1263},
{'attributes': {}, 'tag': 'p', 'end': 1266, 'start': 1263, 'tag_type': 1},
{'start': 1266, 'end': 1292},
{'attributes': {}, 'tag': 'p', 'end': 1296, 'start': 1292, 'tag_type': 2},
{'start': 1296, 'end': 1297},
{'attributes': {}, 'tag': 'h3', 'end': 1301, 'start': 1297, 'tag_type': 1},
{'start': 1301, 'end': 1312},
{'attributes': {}, 'tag': 'h3', 'end': 1317, 'start': 1312, 'tag_type': 2},
{'start': 1317, 'end': 1318},
{'attributes': {'cellpadding': '0', 'width': '420', 'cellspacing': '0', 'class': 'rulet'}, 'tag': 'table', 'end': 1383, 'start': 1318, 'tag_type': 1},
{'attributes': {}, 'tag': 'tbody', 'end': 1390, 'start': 1383, 'tag_type': 1},
{'start': 1390, 'end': 1391},
{'attributes': {}, 'tag': 'tr', 'end': 1395, 'start': 1391, 'tag_type': 1},
{'attributes': {}, 'tag': 'td', 'end': 1399, 'start': 1395, 'tag_type': 1},
{'start': 1399, 'end': 1405},
{'attributes': {}, 'tag': 'td', 'end': 1410, 'start': 1405, 'tag_type': 2},
{'start': 1410, 'end': 1411},
{'attributes': {}, 'tag': 'td', 'end': 1415, 'start': 1411, 'tag_type': 1},
{'attributes': {'data-scrapy-annotate': '{&quot;variant&quot;: &quot;0&quot;, &quot;generated&quot;: true, &quot;annotations&quot;: {&quot;content&quot;: &quot;price&quot;}}'}, 'tag': 'ins', 'end': 1576, 'start': 1415, 'tag_type': 1},
{'start': 1576, 'end': 1581},
{'attributes': {}, 'tag': 'ins', 'end': 1587, 'start': 1581, 'tag_type': 2},
{'attributes': {}, 'tag': 'td', 'end': 1592, 'start': 1587, 'tag_type': 2},
{'start': 1592, 'end': 1593},
{'attributes': {}, 'tag': 'tr', 'end': 1598, 'start': 1593, 'tag_type': 2},
{'attributes': {}, 'tag': 'tbody', 'end': 1605, 'start': 1598, 'tag_type': 1},
{'attributes': {}, 'tag': 'table', 'end': 1613, 'start': 1605, 'tag_type': 2},
{'start': 1613, 'end': 1614},
{'attributes': {'style': 'my style', 'onmouseover': 'xxx', 'class': None}, 'tag': 'p', 'end': 1659, 'start': 1614, 'tag_type': 1},
{'start': 1659, 'end': 1660},
]

# for testing parsing of some invalid html code (but still managed by browsers)
PAGE2 = u"""
<html>
<body>
<p class=&#34;MsoNormal&#34; style=&#34;margin: 0cm 0cm 0pt&#34;><span lang=&#34;EN-GB&#34;>
Hello world!
</span>
</p>
</body>
</html>
"""

PARSED2 = [
 {'end': 1, 'start': 0},
 {'attributes': {}, 'end': 7, 'start': 1, 'tag': u'html', 'tag_type': 1},
 {'end': 8, 'start': 7},
 {'attributes': {}, 'end': 14, 'start': 8, 'tag': u'body', 'tag_type': 1},
 {'end': 15, 'start': 14},
 {'attributes': {u'style': u'&#34;margin:', u'0pt&#34;': None, u'class': u'&#34;MsoNormal&#34;', u'0cm': None}, 'end': 80, 'start': 15, 'tag': u'p', 'tag_type': 1},
 {'attributes': {u'lang': u'&#34;EN-GB&#34;'}, 'end': 107, 'start': 80, 'tag': u'span', 'tag_type': 1},
 {'end': 121, 'start': 107},
 {'attributes': {}, 'end': 128, 'start': 121, 'tag': u'span', 'tag_type': 2},
 {'end': 129, 'start': 128},
 {'attributes': {}, 'end': 133, 'start': 129, 'tag': u'p', 'tag_type': 2},
 {'end': 134, 'start': 133},
 {'attributes': {}, 'end': 141, 'start': 134, 'tag': u'body', 'tag_type': 2},
 {'end': 142, 'start': 141},
 {'attributes': {}, 'end': 149, 'start': 142, 'tag': u'html', 'tag_type': 2},
 {'end': 150, 'start': 149},
]

# for testing tags inside comments
PAGE3 = u"""<html><body><h1>Helloooo!!</h1><p>Did i say hello??</p><!--<p>
</p>--><script type="text/javascript">bla<!--comment-->blabla</script></body></html>"""

PARSED3 = [
 {'attributes': {}, 'end': 6, 'start': 0, 'tag': u'html', 'tag_type': 1},
 {'attributes': {}, 'end': 12, 'start': 6, 'tag': u'body', 'tag_type': 1},
 {'attributes': {}, 'end': 16, 'start': 12, 'tag': u'h1', 'tag_type': 1},
 {'end': 26, 'start': 16},
 {'attributes': {}, 'end': 31, 'start': 26, 'tag': u'h1', 'tag_type': 2},
 {'attributes': {}, 'end': 34, 'start': 31, 'tag': u'p', 'tag_type': 1},
 {'end': 51, 'start': 34},
 {'attributes': {}, 'end': 55, 'start': 51, 'tag': u'p', 'tag_type': 2},
 {'end': 70, 'start': 55},
 {'attributes': {u'type': u'text/javascript'}, 'end': 101, 'start': 70, 'tag': u'script', 'tag_type': 1},
 {'end': 124, 'start': 101},
 {'attributes': {}, 'end': 133, 'start': 124, 'tag': u'script', 'tag_type': 2},
 {'attributes': {}, 'end': 140, 'start': 133, 'tag': u'body', 'tag_type': 2},
 {'attributes': {}, 'end': 147, 'start': 140, 'tag': u'html', 'tag_type': 2}
]

# for testing tags inside scripts
PAGE4 = u"""<html><body><h1>Konnichiwa!!</h1>hello<script type="text/javascript">\
doc.write("<img src=" + base + "product/" + productid + ">");\
</script>hello again</body></html>"""

PARSED4 = [
 {'attributes': {}, 'end': 6, 'start': 0, 'tag': u'html', 'tag_type': 1},
 {'attributes': {}, 'end': 12, 'start': 6, 'tag': u'body', 'tag_type': 1},
 {'attributes': {}, 'end': 16, 'start': 12, 'tag': u'h1', 'tag_type': 1},
 {'end': 28,'start': 16},
 {'attributes': {}, 'end': 33, 'start': 28, 'tag': u'h1', 'tag_type': 2},
 {'end': 38, 'start': 33},
 {'attributes': {u'type': u'text/javascript'}, 'end': 69, 'start': 38, 'tag': u'script', 'tag_type': 1},
 {'end': 130, 'start': 69},
 {'attributes': {}, 'end': 139, 'start': 130, 'tag': u'script', 'tag_type': 2},
 {'end': 150, 'start': 139},
 {'attributes': {}, 'end': 157, 'start': 150, 'tag': u'body', 'tag_type': 2},
 {'attributes': {}, 'end': 164, 'start': 157, 'tag': u'html', 'tag_type': 2},
]

# Test sucessive cleaning elements
PAGE5 = u"""<html><body><script>hello</script><script>brb</script></body><!--commentA--><!--commentB--></html>"""

PARSED5 = [
 {'attributes': {}, 'end': 6, 'start': 0, 'tag': u'html', 'tag_type': 1},
 {'attributes': {}, 'end': 12, 'start': 6, 'tag': u'body', 'tag_type': 1},
 {'attributes': {}, 'end': 20, 'start': 12, 'tag': u'script', 'tag_type': 1},
 {'end': 25, 'start': 20},
 {'attributes': {}, 'end': 34, 'start': 25, 'tag': u'script', 'tag_type': 2},
 {'attributes': {}, 'end': 42, 'start': 34, 'tag': u'script', 'tag_type': 1},
 {'end': 45, 'start': 42},
 {'attributes': {}, 'end': 54, 'start': 45, 'tag': u'script', 'tag_type': 2},
 {'attributes': {}, 'end': 61, 'start': 54, 'tag': u'body', 'tag_type': 2},
 {'end': 91, 'start': 61},
 {'attributes': {}, 'end': 98, 'start': 91, 'tag': u'html', 'tag_type': 2},
]
 
# Test sucessive cleaning elements variant 2
PAGE6 = u"""<html><body><script>pss<!--comment-->pss</script>all<script>brb</script>\n\n</body></html>"""

PARSED6 = [
 {'attributes': {}, 'end': 6, 'start': 0, 'tag': u'html', 'tag_type': 1},
 {'attributes': {}, 'end': 12, 'start': 6, 'tag': u'body', 'tag_type': 1},
 {'attributes': {}, 'end': 20, 'start': 12, 'tag': u'script', 'tag_type': 1},
 {'end': 40, 'start': 20},
 {'attributes': {}, 'end': 49, 'start': 40, 'tag': u'script', 'tag_type': 2},
 {'end': 52, 'start': 49},
 {'attributes': {}, 'end': 60, 'start': 52, 'tag': u'script', 'tag_type': 1},
 {'end': 63, 'start': 60},
 {'attributes': {}, 'end': 72, 'start': 63, 'tag': u'script', 'tag_type': 2},
 {'end': 74, 'start': 72},
 {'attributes': {}, 'end': 81, 'start': 74, 'tag': u'body', 'tag_type': 2},
 {'attributes': {}, 'end': 88, 'start': 81, 'tag': u'html', 'tag_type': 2},
]
