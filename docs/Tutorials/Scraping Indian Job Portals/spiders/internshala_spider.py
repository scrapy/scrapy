# -*- coding: utf-8 -*-
#-Code - github.com/officialsiddharthchauhan
import scrapy
from ..items import InternshalaItem
#creating the spiderclass
class InternshalaSpider(scrapy.Spider):
    name = 'internshalaspider'
    page_number = 1
    start_urls=[
    'https://internshala.com/internships'
    ]
    
    def parse(self, response):
        items = InternshalaItem()
        
        internship_type=response.css('h4:nth-child(1) a').css('::text').extract()
        company_name = response.css('.link_display_like_text').css('::text').extract()
        stipend = response.css('.stipend_container_table_cell').css('::text').extract()
        location = response.css('.location_link').css('::text').extract()
        time_frame = response.css('td:nth-child(2)').css('::text').extract()
        items['internship_type'] = internship_type
        items['company_name'] = company_name
        items['stipend'] = stipend
        items['location'] = location
        items['time_frame'] = time_frame
        yield items

        next_page = 'https://internshala.com/internships/page-'+str(InternshalaSpider.page_number)

        if InternshalaSpider.page_number<=200:
            yield response.follow(next_page, callback = self.parse)
