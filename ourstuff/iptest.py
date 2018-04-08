import scrapy

def main():

    request = scrapy.Request('http://whatismyv6.com/', meta={'bindaddress': ('1234:5678:111::0a', 0)})
    print(request);

if __name__=="__main__":
    main()
