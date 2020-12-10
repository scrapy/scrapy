import scrapy


arrNum =[]
class FfcountrySpider(scrapy.Spider):
    name = 'ffcountry'
    allowed_domains = ['fairfaxcountry.gov']
    start_urls = ['https://www.fairfaxcounty.gov/FIDO/complaints/comp_display.aspx?type=addr&addrkey=1601938&cnt=2&stno=2933&stname=GRAHAM']

    def parse(self, response):
        #first column of gvtTable
        #for each row
        # element 'a'
        rows = response.css('table.gvTable tr')
        for row in rows[1:-2]:
            arrNum.append(row.css('td').css('a::text').extract_first())
            print(row.css('td').css('a::text').extract_first())
        with open('numbers.txt','w') as f:
            for item in arrNum:
                f.write("%s\n" % item)

        print ("below is the list:\n")
        print (arrNum)
