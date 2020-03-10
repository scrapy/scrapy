import scrapy
import redis
import random


class redis_spider(scrapy.Spider):
    
    def __init__ (self,*args, **kwargs):
        super().__init__(name=None, **kwargs)
        self.redis_conn=self.connect_redis(
            self.host, 
            self.port, 
            self.db, 
            self.password,
            self.socket_timeout
        )
        self.state=-1 # -1 for uninitiated, 1 for in run , 0 for end
   
    def connect_redis(self, host, port, db, password,socket_timeout):
        #creates connection with the redis in-memory database
        r =redis.Redis(host, port, db, password,socket_timeout)
        return r 
    
    def push(self, request):
        #it inserts request url into the quque of redis database
        key= random.getrandbits(32)
        self.redis_conn.hset(name=self.name,
                             key=key,
                             value=request.url)        
        return key

    def pop(self):
        #Releases item in the top of the queue (since fifo)  
        #or else returns 0 if nothing is left in que
        key_cur=self.redis_conn.hkeys(self.name)
        if key_cur:
            yield self.redis_conn.hget(self.name,key_cur[0]).decode()
            self.redis_conn.hdel(self.name,key_cur[0])
        else :
            self.state=0
            return 0

    def run(self):
        #it initates the retrieving of requests from redis
        if self.state== -1:
            self.state = 1
            while self.state==1:
                yield from self.pop()
        else :
            "Queue has already been processed or being processed"
    

#Following initation code is kept for temporary testing,
# later it will removed from here

try :
    from scrapy.msg_que import trial_data #change_2
except : 
    import trial_data

