import scrapy

class ExampleSpider(scrapy.Spider):
    name = "example"
    allowed_domains = ["example.com"]
    start_urls = ["https://example.com"]

    def parse(self, response):
        title = response.xpath('//title/text()').get()
        heading = response.xpath('//h1/text()').get()
        paragraphs = response.xpath('//p/text()').getall()
        image_urls = response.css('img::attr(src)').getall()
        meta_description = response.xpath('//meta[@name="description"]/@content').get()
        all_links = response.css('a::attr(href)').getall()
        all_headings = response.css('h1, h2, h3::text').getall()
        list_items = response.css('ul li::text').getall()
        table_rows = response.xpath('//table//tr').getall()
        yield {
            'title': title,
            'heading': heading,
            'paragraphs': paragraphs,
            'images': image_urls,
            'meta_description': meta_description,
            'all_links': all_links,
            'all_headings': all_headings,
            'list_items': list_items,
            'table_rows': table_rows,
        }

        for href in response.css('a::attr(href)').getall():
            if href and href.startswith('https://example.com/articles'):
                yield response.follow(href, callback=self.parse)

        next_page = response.css('a.next::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)