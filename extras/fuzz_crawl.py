# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
################################################################################

#import sys
#import atheris
#import scrapy
#from scrapy.crawler import CrawlerProcess

class test_spider(scrapy.Spider):
	start_urls = ['http://google.com', 'http://youtube.com/']

	def parse(self, response):
		pass

def TestOneInput(data):
	fdp = atheris.FuzzedDataProvider(data)
	test = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 4096))

	try:
		process = CrawlerProcess(settings={
        	test
    	})
		process.crawl(test_spider)
		process.start()
	except:
		pass


def main():
	atheris.instrument_all()
	atheris.Setup(sys.argv, TestOneInput)
	atheris.Fuzz()


if __name__ == "__main__":
	main()
