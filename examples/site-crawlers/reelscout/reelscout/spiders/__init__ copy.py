# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html

from scrapy.spider import BaseSpider
from scrapy.selector import HtmlXPathSelector

from reelscout.items import ReelscoutItem
class ReelscoutSpider(BaseSpider):
	name = 'reelscout'
	allowed_domains = ['ca.reel-scout.com']
	start_urls = ['http://ca.reel-scout.com/jur_browse_content.aspx?cn=&jur=a&type=all&view=all']
	rules = [Rule(SgmlLinkExtractor(allow=['/jur_detail.aspx?id']), 'parse_torrent')]
	
	def parse_torrent(self,response):
		x = HtmlXPathSelector(response)
		
		torrent['url'] = response.url
		torrent['description'] = x.select("//span[@id='lblDescription']/text()").extract()
		torrent['jurisdictiontype'] = x.select("//span[@id='lblJurisdictionType']").extract()
		torrent['agency'] = x.select("//span[@id='lblUmbrellaAgency']/text()").extract()
		torrent['contactinfo'] = x.select("//span[@id='lblContact']/p/text()").extract()
		torrent['links'] = x.select("//span[@id='lblContacts']/p/a/@href").extract()
		return torrent
	