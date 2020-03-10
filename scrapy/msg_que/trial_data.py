import redis
r= redis.Redis(host='localhost',
                port=6379,
                db=0,
                password=None,
                socket_timeout=None
                )
#r.flushdb()  //removed it because it could be dangerous to new user

def url_gen(n):
    base_url= 'http://quotes.toscrape.com/page/%s/'
    for i in range(1,n+1):
        yield base_url % i

def url_set_gen(name,n) :
    item_name=name+"%s"
    temp=dict()
    urls=url_gen(n)
    for idx,item in enumerate(urls):
        key = item_name % (idx+1)
        temp[key]=item
    return temp
        
urls={
    "url1":'http://quotes.toscrape.com/page/1/',
    "url2":'http://quotes.toscrape.com/page/2/', 
    }    

#r.hmset("Quotes", urls)
r.hmset("Quotes",url_set_gen("temp",10))


